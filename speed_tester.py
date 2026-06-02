#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网络测速模块"""

import time
import ssl
import urllib.request
from typing import Callable, Optional


# 绕过系统代理：VPN 关闭后注册表常残留失效代理，
# urllib 默认会读取系统代理导致所有下载失败。测速应走直连。
_NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),                       # 空代理 = 直连
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
)


class SpeedTester:

    # 多源测速 URL（国内优先，HTTP+HTTPS 混合，避免 SSL 拦截导致全部失败）
    SPEED_TEST_URLS = [
        # 腾讯系列 —— 国内 CDN，极快
        ("http://dldir1.qq.com/qqfile/qq/PCQQ9.7.17/QQ9.7.17.29225.exe",
         5 * 1024 * 1024, "腾讯 CDN (HTTP)"),
        ("https://dldir1.qq.com/qqfile/qq/PCQQ9.7.17/QQ9.7.17.29225.exe",
         5 * 1024 * 1024, "腾讯 CDN (HTTPS)"),
        # jsDelivr —— 全球 CDN，国内通常可达
        ("https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js",
         512 * 1024, "jsDelivr CDN"),
        # 国内高校镜像 —— 稳定可靠
        ("https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ls-lR.gz",
         3 * 1024 * 1024, "清华镜像"),
        ("https://mirrors.ustc.edu.cn/ubuntu/ls-lR.gz",
         3 * 1024 * 1024, "中科大镜像"),
        # 国际测速端点（作为后备）
        ("http://speedtest.tele2.net/1MB.zip",
         1 * 1024 * 1024, "Tele2 测速"),
        ("http://cachefly.cachefly.net/10mb.test",
         2 * 1024 * 1024, "CacheFly CDN"),
    ]

    @staticmethod
    def test_speed_sample(
        url: str,
        timeout: int = 15,
        max_bytes: int = 5 * 1024 * 1024,
        progress_cb: Optional[Callable[[float], None]] = None,
    ):
        """
        单源测速采样。
        progress_cb(speed_mbps) 每 250ms 回调一次实时速度。
        返回 (ok, speed_mbps, downloaded_bytes, elapsed_sec, error)
        """
        try:
            start = time.time()
            req = urllib.request.Request(url, headers={
                "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Cache-Control": "no-cache, no-store",
                "Pragma":        "no-cache",
            })
            resp = _NO_PROXY_OPENER.open(req, timeout=timeout)
            chunk = 32768   # 32 KB
            downloaded = 0
            last_cb = start

            while downloaded < max_bytes:
                data = resp.read(chunk)
                if not data:
                    break
                downloaded += len(data)

                now = time.time()
                if progress_cb and now - last_cb >= 0.25 and downloaded > 0:
                    speed = (downloaded * 8) / (now - start) / (1024 * 1024)
                    progress_cb(round(speed, 1))
                    last_cb = now

            elapsed = time.time() - start
            if elapsed > 0 and downloaded > 0:
                speed = (downloaded * 8) / elapsed / (1024 * 1024)
                return True, round(speed, 2), downloaded, round(elapsed, 2), None
            return False, 0, 0, 0, "下载数据为空"
        except Exception as e:
            return False, 0, 0, 0, str(e)

    @staticmethod
    def test_speed(timeout: int = 15):
        """自动选源测速，返回 (ok, speed_mbps, elapsed_or_error)"""
        errors = []
        for url, expected, name in SpeedTester.SPEED_TEST_URLS:
            max_b = expected if expected > 0 else 1 * 1024 * 1024
            ok, speed, _, elapsed, err = SpeedTester.test_speed_sample(url, timeout, max_b)
            if ok and speed > 0:
                return True, speed, elapsed
            if err:
                errors.append(f"{name}: {err[:40]}")
        return False, 0, "；".join(errors) or "所有测速源不可达"
