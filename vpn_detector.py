#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN / 代理检测模块
检测是否使用 VPN/代理、类型、并给出风险评估
"""

import socket
import subprocess
import platform
import re
import ssl
import urllib.request


# 适配器/描述关键字 → (友好名称, 类别)
# 类别：proxy 代理型 / tunnel 虚拟网卡 / corp 企业 / mesh 组网 / system 系统拨号
_ADAPTER_SIGNS = [
    # 商业 / 组网
    ("tailscale",   "Tailscale",        "mesh"),
    ("zerotier",    "ZeroTier",         "mesh"),
    ("hamachi",     "LogMeIn Hamachi",  "mesh"),
    # 虚拟网卡型
    ("wireguard",   "WireGuard",        "tunnel"),
    ("wintun",      "WireGuard/Wintun", "tunnel"),
    ("tap-windows", "OpenVPN (TAP)",    "tunnel"),
    ("tap-win32",   "OpenVPN (TAP)",    "tunnel"),
    ("openvpn",     "OpenVPN",          "tunnel"),
    ("softether",   "SoftEther VPN",    "tunnel"),
    # 注意：不要用裸 "tun"，会误匹配 Windows 自带的 "Tunnel adapter"
    # (Teredo / ISATAP / 6to4)，那是 IPv6 过渡适配器，并非 VPN
    ("tun/tap",     "TUN/TAP 隧道",      "tunnel"),
    # 企业 VPN
    ("anyconnect",  "Cisco AnyConnect", "corp"),
    ("cisco",       "Cisco VPN",        "corp"),
    ("forticlient", "FortiClient",      "corp"),
    ("fortinet",    "Fortinet VPN",     "corp"),
    ("pulse",       "Pulse Secure",     "corp"),
    ("globalprotect","GlobalProtect",   "corp"),
    ("checkpoint",  "Check Point VPN",  "corp"),
    # 商业 VPN 客户端
    ("nordvpn",     "NordVPN",          "tunnel"),
    ("expressvpn",  "ExpressVPN",       "tunnel"),
    ("surfshark",   "Surfshark",        "tunnel"),
    ("astrill",     "Astrill",          "tunnel"),
    ("cloudflare",  "Cloudflare WARP",  "tunnel"),
    ("warp",        "Cloudflare WARP",  "tunnel"),
]

_CATEGORY_NAME = {
    "proxy":  "代理型（Clash / V2Ray / SS 类）",
    "tunnel": "虚拟网卡型（WireGuard / OpenVPN 类）",
    "corp":   "企业 VPN",
    "mesh":   "异地组网（Mesh VPN）",
    "system": "系统拨号 VPN（PPTP / L2TP / IKEv2）",
}

_IP_ECHO_URLS = [
    "https://myip.ipip.net",
    "https://api.ipify.org",
    "http://ip.3322.net",
]


def _decode(b):
    for enc in ("utf-8", "gbk", "gb2312"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "ignore")


# 复用 SSL 上下文与 opener，避免每次检测重建（省 CPU 与内存）
_SSL_CTX = ssl._create_unverified_context()
_DIRECT_OPENER = urllib.request.build_opener(            # 强制直连
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_SSL_CTX))
_PROXY_OPENER = urllib.request.build_opener(             # 走系统代理
    urllib.request.HTTPSHandler(context=_SSL_CTX))


class VPNDetector:

    # ── 系统代理（注册表）──────────────────────────────────

    @staticmethod
    def _read_system_proxy():
        """返回 (enabled, server_str)"""
        if platform.system().lower() != "windows":
            return False, ""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server = ""
            try:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            return bool(enable), server or ""
        except Exception:
            return False, ""

    # ── 网络适配器扫描 ────────────────────────────────────

    @staticmethod
    def _scan_adapters():
        """返回 [(friendly_name, category), ...]"""
        found = []
        system = platform.system().lower()
        try:
            if system == "windows":
                proc = subprocess.run(["ipconfig", "/all"],
                                      capture_output=True, timeout=10)
                text = _decode(proc.stdout)
            else:
                proc = subprocess.run(["ifconfig", "-a"],
                                      capture_output=True, timeout=10)
                text = _decode(proc.stdout)
        except Exception:
            return found

        low = text.lower()

        # 关键字匹配
        seen = set()
        for kw, name, cat in _ADAPTER_SIGNS:
            if kw in low and name not in seen:
                found.append((name, cat))
                seen.add(name)

        # PPP 拨号 VPN（PPTP/L2TP/IKEv2）
        if re.search(r"ppp\s*适配器", low) or re.search(r"ppp adapter", low):
            if "系统拨号 VPN" not in seen:
                found.append(("系统拨号 VPN", "system"))
                seen.add("系统拨号 VPN")

        return found

    # ── Cloudflare WARP 检测 ──────────────────────────────

    @staticmethod
    def _check_warp():
        """通过 Cloudflare 官方 trace 端点检测 WARP。
        返回 (status, ip, loc)  status ∈ {'off','on','plus',None}
        WARP 是网络层隧道，即使直连 socket 也会经它转发，故此处直接请求即可。
        """
        try:
            req = urllib.request.Request(
                "https://www.cloudflare.com/cdn-cgi/trace",
                headers={"User-Agent": "Mozilla/5.0"})
            text = _DIRECT_OPENER.open(req, timeout=5).read().decode("utf-8", "ignore")
            kv = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
            return kv.get("warp"), kv.get("ip"), kv.get("loc")
        except Exception:
            return None, None, None

    # ── 出口 IP 检测 ──────────────────────────────────────

    @staticmethod
    def _fetch_ip(opener, timeout=4):
        for url in _IP_ECHO_URLS:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"})
                raw = opener.open(req, timeout=timeout).read().decode("utf-8", "ignore")
                m = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", raw)
                if m:
                    return m.group(0)
            except Exception:
                continue
        return None

    @staticmethod
    def _egress_compare():
        """对比直连出口 IP 与系统代理出口 IP，判断代理是否真在转发。
        返回 (direct_ip, proxy_ip, rerouting:bool|None)
        """
        d_ip = VPNDetector._fetch_ip(_DIRECT_OPENER)
        p_ip = VPNDetector._fetch_ip(_PROXY_OPENER)
        if d_ip and p_ip:
            return d_ip, p_ip, (d_ip != p_ip)
        return d_ip, p_ip, None

    # ── 主入口 ────────────────────────────────────────────

    @staticmethod
    def detect():
        result = {
            "active":     False,
            "categories": [],     # 中文类别描述
            "names":      [],     # 具体软件/适配器名
            "summary":    "",
            "risk_level": "none", # none / low / medium / high
            "risk_label": "无",
            "reasons":    [],
            "egress_ip":  None,
            "real_ip":    None,
        }

        cats = set()
        names = []

        # 1) 系统代理
        proxy_on, proxy_server = VPNDetector._read_system_proxy()
        local_proxy = False
        if proxy_on and proxy_server:
            cats.add("proxy")
            names.append(f"系统代理 {proxy_server}")
            if re.search(r"127\.0\.0\.1|localhost|::1", proxy_server):
                local_proxy = True

        # 2) 网络适配器
        for name, cat in VPNDetector._scan_adapters():
            cats.add(cat)
            names.append(name)

        # 3) Cloudflare WARP（网络层隧道，不设代理、名称难匹配，需专门检测）
        warp_on = False
        warp_status, warp_ip, warp_loc = VPNDetector._check_warp()
        if warp_status in ("on", "plus"):
            warp_on = True
            cats.add("tunnel")
            tag = "Cloudflare WARP+" if warp_status == "plus" else "Cloudflare WARP"
            if not any("WARP" in n for n in names):
                names.append(tag)
            result["egress_ip"] = warp_ip

        result["active"] = bool(cats)
        result["categories"] = [_CATEGORY_NAME[c] for c in cats]
        result["names"] = names

        if not cats:
            result["summary"]    = "未检测到 VPN 或代理"
            result["risk_level"] = "none"
            result["risk_label"] = "无"
            return result

        # 4) 出口 IP 对比（仅在有代理时验证是否真转发）
        rerouting = None
        if proxy_on:
            try:
                real_ip, egress_ip, rerouting = VPNDetector._egress_compare()
                result["real_ip"]   = real_ip
                result["egress_ip"] = egress_ip
            except Exception:
                pass

        # 5) 风险评估
        reasons = []
        score = 0  # 0-1 低, 2 中, 3+ 高

        if warp_on:
            loc = f"，出口地区 {warp_loc}" if warp_loc else ""
            reasons.append(f"全局流量经 Cloudflare WARP 隧道转发{loc}；"
                           "Cloudflare 为可信厂商，但可见你的访问元数据与 DNS")
        if local_proxy:
            score += 1
            reasons.append("流量经本地代理转发到远程节点，节点可窥探未加密(HTTP)内容")
        if "proxy" in cats:
            score += 1
            reasons.append("已启用系统代理，DNS 查询可能泄漏真实访问目标")
        if "tunnel" in cats:
            score += 1
            reasons.append("虚拟网卡接管全局流量，所有连接经第三方隧道")
        if rerouting is True:
            score += 1
            reasons.append(f"出口 IP 已被改变（真实 {result['real_ip']} → 出口 {result['egress_ip']}）")
        elif rerouting is False:
            reasons.append("代理已配置但出口 IP 未改变（可能为分流/PAC 模式）")
        if len(cats) >= 2:
            score += 1
            reasons.append("检测到多重 VPN/代理叠加，配置复杂易出错")
        if "corp" in cats:
            reasons.append("企业 VPN 通常可信，但单位可审计你的流量")

        if "corp" in cats and len(cats) == 1:
            level, label = "low", "较低"
        elif score >= 3:
            level, label = "high", "较高"
        elif score >= 1:
            level, label = "medium", "中等"
        else:
            level, label = "low", "较低"

        result["risk_level"] = level
        result["risk_label"] = label
        result["reasons"]    = reasons
        result["summary"]    = "检测到：" + "、".join(result["categories"])
        return result


if __name__ == "__main__":
    import json
    print(json.dumps(VPNDetector.detect(), ensure_ascii=False, indent=2))
