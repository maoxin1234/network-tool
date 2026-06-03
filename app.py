#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络检测修复工具 — PyWebview 桌面版入口
界面使用 HTML/CSS/JS（Fluent Design），后端复用现有 Python 模块

重要：所有耗时操作（检测/Ping/测速/修复）均在后台线程执行，
通过 evaluate_js 推送结果，避免阻塞 GUI 主线程导致窗口“未响应”。
"""

import os
import sys
import json
import threading

# 精简 WebView2 后台行为以降低空闲资源占用（须在 webview 启动前设置）。
# 仅关闭翻译、SmartScreen 上报、组件更新与后台网络等非必要特性，
# 不禁用 GPU，避免界面渲染异常。
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-features=Translate,msSmartScreenProtection,OptimizationHints "
    "--disable-background-networking --disable-component-update "
    "--disable-breakpad")

import webview

import history as hist
from network_utils import NetworkUtils, is_admin
from speed_tester import SpeedTester
from vpn_detector import VPNDetector


_REPAIR_FUNCS = {
    "flush_dns":     NetworkUtils.flush_dns,
    "reset_proxy":   NetworkUtils.reset_proxy,
    "reset_winsock": NetworkUtils.reset_winsock,
    "reset_ip":      NetworkUtils.reset_ip,
    "reset_adapter": NetworkUtils.reset_network_adapter,
}


class Api:
    """暴露给前端 JS 的接口：window.pywebview.api.xxx()"""

    def __init__(self):
        self.window = None
        self._cancel_speed = False

    # ── 前端推送辅助 ─────────────────────────────────────
    def _emit(self, fn, *args):
        if not self.window:
            return
        payload = json.dumps(args, ensure_ascii=False)
        try:
            self.window.evaluate_js(
                f"window.{fn} && window.{fn}.apply(null, {payload})")
        except Exception:
            pass

    # ── 即时返回的轻量方法 ───────────────────────────────
    def get_admin(self):
        return {"admin": is_admin()}

    def speed_sources(self):
        return [name for _, _, name in SpeedTester.SPEED_TEST_URLS]

    def get_history(self):
        return hist.load_all()

    def clear_history(self):
        return {"ok": hist.clear()}

    # ── 一键检测（后台线程）─────────────────────────────
    def start_check(self):
        threading.Thread(target=self._run_check, daemon=True).start()
        return True

    def _run_check(self):
        steps = [
            ("internet", self._check_internet),
            ("dns",      self._check_dns),
            ("ping",     self._check_ping),
            ("vpn",      VPNDetector.detect),
        ]
        results = {}
        n = len(steps)
        for i, (sid, fn) in enumerate(steps):
            self._emit("onCheckProgress", int(i / n * 100), f"检测 {i+1} / {n}…")
            self._emit("onCheckRunning", sid)
            try:
                r = fn()
            except Exception as e:
                r = {"status": "fail", "summary": f"检测出错：{e}"}
            results[sid] = r
            self._emit("onCheckResult", sid, r)
        try:
            hist.append(results)
        except Exception:
            pass
        self._emit("onCheckProgress", 100, "检测完成")
        self._emit("onCheckDone", results)

    @staticmethod
    def _check_internet():
        ok, host, err = NetworkUtils.check_internet()
        return {"status": "ok" if ok else "fail",
                "summary": f"连接正常 ({host})" if ok else f"{err}"}

    @staticmethod
    def _check_dns():
        ok, ips, info = NetworkUtils.check_dns()
        if ok:
            return {"status": "ok", "summary": f"解析正常 {ips[0]} · {info} ms"}
        return {"status": "fail", "summary": f"解析失败：{info}"}

    @staticmethod
    def _check_ping():
        ok, avg, lost, jitter = NetworkUtils.ping_host()
        if ok:
            j = f" · 抖动 {jitter} ms" if jitter is not None else ""
            return {"status": "ok", "summary": f"延迟 {avg} ms · 丢包 {lost}%{j}"}
        return {"status": "fail", "summary": f"丢包率 {lost}%（网络不稳定）"}

    # ── 网络信息（后台线程）─────────────────────────────
    def start_info(self):
        def run():
            self._emit("onInfo", NetworkUtils.get_network_info())
        threading.Thread(target=run, daemon=True).start()
        return True

    # ── 修复（后台线程）─────────────────────────────────
    def start_repair(self, item_id, token=""):
        def run():
            fn = _REPAIR_FUNCS.get(item_id)
            ok, msg = fn() if fn else (False, "未知操作")
            self._emit("onRepairDone", item_id, ok, msg, token)
        threading.Thread(target=run, daemon=True).start()
        return True

    # ── 网速测试（后台线程 + 流式推送）─────────────────
    def start_speed_test(self):
        self._cancel_speed = False
        threading.Thread(target=self._run_speed, daemon=True).start()
        return True

    def stop_speed_test(self):
        self._cancel_speed = True
        return True

    # 测到 ENOUGH 个有效源即可算出最优/平均/峰值，余下源跳过以节省带宽与时间
    ENOUGH_SAMPLES = 2

    def _run_speed(self):
        urls = SpeedTester.SPEED_TEST_URLS
        n = len(urls)
        best_s = best_dl = best_el = 0
        best_n = ""
        peak = 0
        speeds = []

        for i, (url, expected, name) in enumerate(urls):
            if self._cancel_speed:
                break
            # 已取得足够样本，跳过剩余源（仅通知前端，不发起网络请求）
            if len(speeds) >= self.ENOUGH_SAMPLES:
                self._emit("onSpeedSkip", name)
                continue

            self._emit("onSpeedStatus", f"测试 {name}…", int(i / n * 100))
            max_b = expected if expected > 0 else 2 * 1024 * 1024

            def cb(spd, nm=name):
                if not self._cancel_speed:
                    self._emit("onSpeedLive", spd, nm)

            ok, spd, dl, el, err = SpeedTester.test_speed_sample(
                url, timeout=15, max_bytes=max_b, progress_cb=cb)

            if self._cancel_speed:
                break
            if ok and spd > 0:
                speeds.append(spd)
                peak = max(peak, spd)
                if spd > best_s:
                    best_s, best_dl, best_el, best_n = spd, dl, el, name
            self._emit("onSpeedSource", name, spd if ok else None, bool(ok))

        if self._cancel_speed:
            self._emit("onSpeedDone", None, True)
            return
        if not speeds:
            self._emit("onSpeedDone", None, False)
            return

        avg = round(sum(speeds) / len(speeds), 2)
        if   best_s >= 50: grade = "⚡ 极速"
        elif best_s >= 20: grade = "🌟 高速"
        elif best_s >= 5:  grade = "👍 标准"
        elif best_s >= 1:  grade = "📶 基础"
        else:              grade = "🐢 较慢"

        self._emit("onSpeedDone", {
            "best": best_s, "avg": avg, "peak": round(peak, 2),
            "dl_mb": round(best_dl / (1024 * 1024), 2),
            "el": best_el, "src": best_n, "grade": grade,
        }, False)


def _resource(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def main():
    api = Api()
    window = webview.create_window(
        "网络检测修复工具",
        _resource(os.path.join("web", "index.html")),
        js_api=api,
        width=980, height=720, min_size=(860, 600),
        background_color="#F3F3F3",
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
