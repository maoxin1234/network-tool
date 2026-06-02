#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网络检测与修复模块"""

import subprocess
import socket
import platform
import re
import time


def is_admin() -> bool:
    """检测当前进程是否拥有管理员权限（Windows）"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class NetworkUtils:

    @staticmethod
    def check_internet(timeout=3):
        """检测互联网连通性"""
        hosts = [
            ("www.baidu.com", 443),
            ("www.qq.com", 443),
            ("114.114.114.114", 53),
            ("223.5.5.5", 53),
        ]
        for host, port in hosts:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                s.close()
                return True, host, None
            except Exception:
                continue
        return False, None, "无法连接到任何已知服务器"

    @staticmethod
    def check_dns(domain="www.baidu.com"):
        """检测 DNS 解析"""
        try:
            start = time.time()
            ip_list = socket.getaddrinfo(domain, None, socket.AF_INET)
            elapsed = (time.time() - start) * 1000
            ips = list(set(item[4][0] for item in ip_list))
            return True, ips, round(elapsed, 1)
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    def ping_host(host=None, count=4, timeout=2):
        """Ping 测试，返回 (ok, avg_ms, loss_pct, jitter_ms)
        host 可传入单个或列表，默认按优先级尝试多个目标
        """
        # 多个目标按优先级回退（114.114.114.114 屏蔽 ICMP，不再作为首选）
        targets = host or [
            "www.baidu.com",
            "223.5.5.5",
            "8.8.8.8",
            "1.1.1.1",
        ]
        if isinstance(targets, str):
            targets = [targets]

        system = platform.system().lower()

        for target in targets:
            if system == "windows":
                cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), target]
            else:
                cmd = ["ping", "-c", str(count), "-W", str(timeout), target]

            try:
                proc = subprocess.run(cmd, capture_output=True,
                                      timeout=timeout * count + 5)

                # 兼容中文 Windows GBK 编码
                output = ""
                for enc in ("utf-8", "gbk", "gb2312"):
                    try:
                        output = proc.stdout.decode(enc) + proc.stderr.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue

                if system == "windows":
                    lost_m = re.search(r"(\d+)%\s*丢失", output) \
                          or re.search(r"(\d+)%\s*loss", output, re.I)
                    avg_m  = re.search(r"平均\s*=\s*(\d+)\s*ms", output) \
                          or re.search(r"Average\s*=\s*(\d+)\s*ms", output, re.I)
                    min_m  = re.search(r"最短\s*=\s*(\d+)\s*ms", output) \
                          or re.search(r"Minimum\s*=\s*(\d+)\s*ms", output, re.I)
                    max_m  = re.search(r"最长\s*=\s*(\d+)\s*ms", output) \
                          or re.search(r"Maximum\s*=\s*(\d+)\s*ms", output, re.I)
                else:
                    lost_m = re.search(r"(\d+)% packet loss", output)
                    avg_m  = re.search(r"min/avg/max.*?= [\d.]+/([\d.]+)/", output)
                    min_m  = re.search(r"min/avg/max.*?= ([\d.]+)/", output)
                    max_m  = re.search(r"min/avg/max.*?/[\d.]+/([\d.]+)", output)

                lost   = int(lost_m.group(1)) if lost_m else 100
                avg    = int(float(avg_m.group(1))) if avg_m else None
                mn     = int(float(min_m.group(1))) if min_m else None
                mx     = int(float(max_m.group(1))) if max_m else None
                jitter = (mx - mn) if (mn is not None and mx is not None) else None

                # 如果全部丢包，尝试下一个目标
                if lost == 100:
                    continue

                return lost < 100, avg, lost, jitter
            except Exception:
                continue

        # ICMP 全部失败（多数网络/路由器屏蔽 ICMP，或非管理员受限）
        # 改用 TCP 连接延迟兜底——只要能上网就能测出延迟
        return NetworkUtils._tcp_latency()

    @staticmethod
    def _tcp_latency(count=4, timeout=2):
        """TCP 连接延迟测量，ICMP 被屏蔽时的兜底方案
        返回 (ok, avg_ms, loss_pct, jitter_ms)
        """
        targets = [
            ("www.baidu.com", 443),
            ("www.qq.com", 443),
            ("223.5.5.5", 443),
        ]
        for host, port in targets:
            delays = []
            for _ in range(count):
                try:
                    start = time.time()
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    s.connect((host, port))
                    s.close()
                    delays.append((time.time() - start) * 1000)
                except Exception:
                    continue
            if delays:
                lost = round((count - len(delays)) / count * 100)
                avg = int(sum(delays) / len(delays))
                jitter = int(max(delays) - min(delays))
                return True, avg, lost, jitter
        return False, None, 100, None

    @staticmethod
    def get_network_info():
        """获取本机网络配置"""
        info = {
            "hostname":    socket.gethostname(),
            "ipv4":        [],
            "dns_servers": [],
            "gateway":     "",
            "mac":         "未知",
        }
        system = platform.system().lower()
        try:
            if system == "windows":
                proc = subprocess.run(
                    ["ipconfig", "/all"], capture_output=True, timeout=10)
                output = ""
                for enc in ("utf-8", "gbk"):
                    try:
                        output = proc.stdout.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue

                info["ipv4"] = [
                    ip for ip in re.findall(r"IPv4.*?:\s*([\d.]+)", output)
                    if not ip.startswith("127.")
                ]
                info["dns_servers"] = list(set(re.findall(r"DNS.*?:\s*([\d.]+)", output)))
                gw = re.search(r"(?:默认网关|Default Gateway).*?:\s*([\d.]+)", output)
                if gw:
                    info["gateway"] = gw.group(1)
                mac = re.findall(r"(?:物理地址|Physical Address).*?:\s*([\w-]+)", output)
                if mac:
                    info["mac"] = mac[0]
            else:
                r = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5)
                info["ipv4"] = [ip for ip in r.stdout.split() if not ip.startswith("127.")]
                r2 = subprocess.run(["cat", "/etc/resolv.conf"], capture_output=True, text=True, timeout=5)
                info["dns_servers"] = re.findall(r"nameserver\s+([\d.]+)", r2.stdout)
        except Exception:
            pass

        if not info["ipv4"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                info["ipv4"] = [s.getsockname()[0]]
                s.close()
            except Exception:
                info["ipv4"] = ["无法获取"]

        return info

    # ── 修复操作 ────────────────────────────────────────────

    @staticmethod
    def flush_dns():
        system = platform.system().lower()
        try:
            if system == "windows":
                subprocess.run(["ipconfig", "/flushdns"],
                               capture_output=True, check=True, timeout=10)
            else:
                subprocess.run(["sudo", "dscacheutil", "-flushcache"],
                               capture_output=True, timeout=10)
            return True, "DNS 缓存已成功清除"
        except Exception as e:
            return False, f"刷新失败：{e}"

    @staticmethod
    def reset_proxy():
        if platform.system().lower() != "windows":
            return False, "仅支持 Windows"
        try:
            subprocess.run(
                ['reg', 'add',
                 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings',
                 '/v', 'ProxyEnable', '/t', 'REG_DWORD', '/d', '0', '/f'],
                capture_output=True, check=True, timeout=10)
            subprocess.run(['netsh', 'winhttp', 'reset', 'proxy'],
                           capture_output=True, check=True, timeout=10)
            return True, "代理设置已清除"
        except Exception as e:
            return False, f"清除失败：{e}"

    @staticmethod
    def reset_winsock():
        if platform.system().lower() != "windows":
            return False, "仅支持 Windows"
        try:
            subprocess.run(["netsh", "winsock", "reset"],
                           capture_output=True, check=True, timeout=15)
            return True, "Winsock 已重置（需重启生效）"
        except Exception as e:
            return False, f"重置失败：{e}"

    @staticmethod
    def reset_ip():
        if platform.system().lower() != "windows":
            return False, "仅支持 Windows"
        try:
            subprocess.run(["ipconfig", "/release"],
                           capture_output=True, check=True, timeout=20)
            subprocess.run(["ipconfig", "/renew"],
                           capture_output=True, check=True, timeout=20)
            return True, "IP 地址已更新"
        except Exception as e:
            return False, f"IP 重置失败：{e}"

    @staticmethod
    def reset_network_adapter():
        if platform.system().lower() != "windows":
            return False, "仅支持 Windows"
        try:
            subprocess.run(["netsh", "int", "ip", "reset"],
                           capture_output=True, check=True, timeout=15)
            return True, "网络适配器已重置（建议重启）"
        except Exception as e:
            return False, f"重置失败：{e}"
