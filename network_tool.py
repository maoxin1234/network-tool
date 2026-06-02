#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络检测修复工具 — Windows 11 Fluent Design
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue

import history as hist
from network_utils import NetworkUtils, is_admin
from speed_tester import SpeedTester
from vpn_detector import VPNDetector
from ui_components import (
    S, ShadowCard, EdgeButton, StatusBadge,
    EdgeProgressBar, EdgeScrollFrame, SpeedGauge
)

# 检测失败时的修复建议
_SUGGESTIONS = {
    "internet": [
        ("reset_ip",      "↺ 更新 IP"),
        ("reset_adapter", "⚙ 重置适配器"),
        ("reset_winsock", "⚙ 重置 Winsock"),
    ],
    "dns": [
        ("flush_dns",   "🗂 刷新 DNS"),
        ("reset_proxy", "🔗 清除代理"),
    ],
    "ping": [
        ("reset_winsock", "⚙ 重置 Winsock"),
        ("flush_dns",     "🗂 刷新 DNS"),
    ],
}

_REPAIR_FUNCS = {
    "flush_dns":    NetworkUtils.flush_dns,
    "reset_proxy":  NetworkUtils.reset_proxy,
    "reset_winsock":NetworkUtils.reset_winsock,
    "reset_ip":     NetworkUtils.reset_ip,
    "reset_adapter":NetworkUtils.reset_network_adapter,
}


class NetworkToolApp:

    _NAV = [
        ("check",   "○", "一键检测"),
        ("speed",   "↯", "网速测试"),
        ("repair",  "⚙", "智能修复"),
        ("info",    "≡", "网络信息"),
        ("history", "◷", "检测历史"),
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("网络检测修复工具")
        self.root.geometry("940x680")
        self.root.minsize(820, 560)
        self.root.configure(bg=S.BG_APP)

        # 尝试 Windows 11 圆角窗口
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

        self.msg_queue     = queue.Queue()
        self.current_page  = None
        self.check_results = {}
        self._checking     = False
        self._speed_run    = False
        self._admin        = is_admin()

        # 速度页引用（页面重建前的保护）
        self.speed_gauge      = None
        self.speed_prog       = None
        self.speed_status_lbl = None
        self.speed_start_btn  = None
        self.speed_stop_btn   = None
        self.speed_detail     = {}
        self.speed_cancelled  = False

        # 检测页引用
        self.check_cards    = {}
        self.check_prog     = None
        self.check_prog_lbl = None
        self.check_start_btn= None
        self.summary_frame  = None

        # 修复页引用
        self.repair_rows = {}

        # 信息页引用
        self.info_content_frame = None
        self.info_refresh_btn   = None

        self._setup_ttk()
        self._build_shell()
        self._navigate("check")
        self._poll_queue()

        # F5 全局快捷键
        self.root.bind("<F5>", lambda e: self._f5_refresh())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 工具 ──────────────────────────────────────────────────

    def _alive(self, w):
        try:
            return bool(w and w.winfo_exists())
        except Exception:
            return False

    def _safe_cfg(self, w, **kw):
        if self._alive(w):
            w.config(**kw)

    def _f5_refresh(self):
        if self.current_page == "check" and not self._checking:
            self._run_check()
        elif self.current_page == "speed" and not self._speed_run:
            self._run_speed()
        elif self.current_page == "info":
            self._refresh_info()

    def _on_close(self):
        if self._checking or self._speed_run:
            if not messagebox.askyesno("确认退出", "后台任务正在运行，确定退出吗？"):
                return
        self.root.destroy()

    # ── TTK 样式 ──────────────────────────────────────────────

    def _setup_ttk(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Vertical.TScrollbar",
                     background=S.BORDER, troughcolor=S.BG_APP,
                     arrowcolor=S.T3, bordercolor=S.BG_APP, width=5)
        st.map("Vertical.TScrollbar", background=[("active", S.BORDER_S)])

    # ── 主布局 ────────────────────────────────────────────────

    def _build_shell(self):
        outer = tk.Frame(self.root, bg=S.BG_APP)
        outer.pack(fill=tk.BOTH, expand=True)

        # 侧栏
        self._sidebar = tk.Frame(outer, bg=S.BG_SIDE, width=S.SIDE_W)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # 分隔线
        tk.Frame(outer, bg=S.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # 内容区
        self._content = tk.Frame(outer, bg=S.BG_APP)
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _build_sidebar(self):
        # Logo
        top = tk.Frame(self._sidebar, bg=S.BG_SIDE)
        top.pack(fill=tk.X, padx=S.G4, pady=(S.G8, S.G4))

        lc = tk.Canvas(top, width=40, height=40,
                       bg=S.BG_SIDE, highlightthickness=0)
        lc.pack(side=tk.LEFT)
        lc.create_oval(2, 2, 38, 38, fill=S.ACCENT, outline="")
        lc.create_text(21, 21, text="◉", font=("Segoe UI Symbol", 16), fill="white")

        tf = tk.Frame(top, bg=S.BG_SIDE)
        tf.pack(side=tk.LEFT, padx=(S.G2, 0))
        tk.Label(tf, text="网络工具",
                 font=(S.FF, S.LG, "bold"),
                 bg=S.BG_SIDE, fg=S.T1).pack(anchor="w")
        tk.Label(tf, text="检测 · 修复 · 测速",
                 font=(S.FF, S.XS),
                 bg=S.BG_SIDE, fg=S.T3).pack(anchor="w")

        # 管理员状态徽章
        adm_frame = tk.Frame(self._sidebar, bg=S.BG_SIDE)
        adm_frame.pack(fill=tk.X, padx=S.G3, pady=(0, S.G3))
        adm_text = "● 管理员模式" if self._admin else "○ 普通用户"
        adm_color = S.SUCCESS if self._admin else S.WARNING_FG
        tk.Label(adm_frame, text=adm_text,
                 font=(S.FF, S.XS),
                 bg=S.BG_SIDE, fg=adm_color, anchor="w").pack(anchor="w")
        if not self._admin:
            tk.Label(adm_frame, text="部分修复需管理员权限",
                     font=(S.FF, S.XS),
                     bg=S.BG_SIDE, fg=S.T3, anchor="w").pack(anchor="w")

        # 分隔线
        tk.Frame(self._sidebar, bg=S.BORDER, height=1).pack(
            fill=tk.X, padx=S.G3, pady=(0, S.G2))

        # 导航按钮
        self._nav_cvs = {}
        wrap = tk.Frame(self._sidebar, bg=S.BG_SIDE)
        wrap.pack(fill=tk.X, padx=S.G2, pady=S.G1)

        for pid, icon, label in self._NAV:
            c = tk.Canvas(wrap, width=S.SIDE_W - S.G2 * 2, height=42,
                          highlightthickness=0, bd=0, bg=S.BG_SIDE)
            c.pack(fill=tk.X, pady=1)
            self._nav_cvs[pid] = c
            self._draw_nav(c, icon, label, False)
            c.bind("<Button-1>", lambda e, p=pid: self._navigate(p))
            c.bind("<Enter>",   lambda e, c=c, p=pid: self._nav_hover(c, True, p))
            c.bind("<Leave>",   lambda e, c=c, p=pid: self._nav_hover(c, False, p))

        # 快捷键提示
        tk.Frame(self._sidebar, bg=S.BORDER, height=1).pack(
            side=tk.BOTTOM, fill=tk.X, padx=S.G3, pady=(0, S.G2))
        hint = tk.Frame(self._sidebar, bg=S.BG_SIDE)
        hint.pack(side=tk.BOTTOM, fill=tk.X, padx=S.G4, pady=S.G2)
        tk.Label(hint, text="F5  快速刷新当前页面",
                 font=(S.FF, S.XS), bg=S.BG_SIDE, fg=S.T3, anchor="w").pack(anchor="w")
        tk.Label(hint, text="v2.0",
                 font=(S.FF, S.XS), bg=S.BG_SIDE, fg=S.TD, anchor="w").pack(anchor="w")

    def _draw_nav(self, canvas, icon, text, active, hover=False):
        from ui_components import _poly
        canvas.delete("all")
        w = canvas.winfo_width() or (S.SIDE_W - S.G2 * 2)
        h = 42
        r = S.R_MD

        if active:
            pts = _poly(3, 2, w - 6, h - 4, r)
            canvas.create_polygon(pts, fill=S.ACCENT_L, outline=S.ACCENT_L, smooth=True)
            canvas.create_rectangle(3, 8, 6, h - 8, fill=S.ACCENT, outline="")
            icon_c, text_c, fw = S.ACCENT, S.ACCENT, "bold"
        elif hover:
            pts = _poly(3, 2, w - 6, h - 4, r)
            canvas.create_polygon(pts, fill=S.BG_SIDE_H, outline=S.BG_SIDE_H, smooth=True)
            icon_c, text_c, fw = S.T2, S.T1, "normal"
        else:
            icon_c, text_c, fw = S.T3, S.T1, "normal"

        canvas.create_text(24, h // 2, text=icon,
                           font=("Segoe UI Symbol", 13), fill=icon_c)
        canvas.create_text(46, h // 2, text=text,
                           font=(S.FF, S.MD, fw), fill=text_c, anchor="w")

    def _nav_hover(self, canvas, on, pid):
        if pid != self.current_page:
            info = {p: (ic, lb) for p, ic, lb in self._NAV}
            ic, lb = info[pid]
            self._draw_nav(canvas, ic, lb, False, hover=on)

    # ── 导航 ──────────────────────────────────────────────────

    def _navigate(self, page_id):
        self.current_page = page_id
        info = {p: (ic, lb) for p, ic, lb in self._NAV}
        for pid, c in self._nav_cvs.items():
            ic, lb = info[pid]
            self._draw_nav(c, ic, lb, pid == page_id)

        for w in self._content.winfo_children():
            w.destroy()

        {
            "check":   self._page_check,
            "speed":   self._page_speed,
            "repair":  self._page_repair,
            "info":    self._page_info,
            "history": self._page_history,
        }[page_id]()

    # ── 页面标题 ──────────────────────────────────────────────

    def _header(self, title, subtitle=""):
        # 彩色顶部横幅
        banner = tk.Frame(self._content, bg=S.ACCENT, height=4)
        banner.pack(fill=tk.X)

        hf = tk.Frame(self._content, bg=S.BG_APP)
        hf.pack(fill=tk.X, padx=S.G8, pady=(S.G5, S.G3))

        tk.Label(hf, text=title,
                 font=(S.FF, S.XXL, "bold"),
                 bg=S.BG_APP, fg=S.T1, anchor="w").pack(anchor="w")

        if subtitle:
            tk.Label(hf, text=subtitle,
                     font=(S.FF, S.SM),
                     bg=S.BG_APP, fg=S.T2, anchor="w").pack(anchor="w", pady=(2, 0))

        tk.Frame(self._content, bg=S.BORDER, height=1).pack(
            fill=tk.X, padx=S.G8, pady=(0, S.G4))

    # ══════════════════════════════════════════════════════════
    #  一键检测页面
    # ══════════════════════════════════════════════════════════

    def _page_check(self):
        self._header("一键检测", "快速诊断互联网连接、DNS、延迟与 VPN/代理状态")

        scroll = EdgeScrollFrame(self._content, bg=S.BG_APP)
        scroll.pack(fill=tk.BOTH, expand=True, padx=S.G8, pady=(0, S.G4))
        sf = scroll.scroll_frame

        self.check_cards = {}

        items = [
            ("internet", "互联网连接",
             "测试能否访问外网服务器",
             "⬡",  S.ACCENT_L, S.ACCENT),
            ("dns",      "DNS 解析",
             "测试域名解析是否正常",
             "◎",  "#EDF7ED",  S.SUCCESS),
            ("ping",     "网络延迟",
             "Ping 测试延迟与丢包率",
             "↯",  "#FFF4CE",  S.WARNING_FG),
            ("vpn",      "VPN / 代理",
             "检测代理状态、类型与风险",
             "⛨",  "#F3EDFA",  "#7B4FB5"),
        ]

        for item_id, title, desc, icon, ic_bg, ic_fg in items:
            card = ShadowCard(sf)
            card.pack(fill=tk.X, pady=(0, S.G3))
            body = card.inner

            row = tk.Frame(body, bg=S.BG_CARD)
            row.pack(fill=tk.X, padx=S.G4, pady=S.G4)

            # 图标圆圈
            ic_c = tk.Canvas(row, width=44, height=44,
                              highlightthickness=0, bd=0, bg=S.BG_CARD)
            ic_c.pack(side=tk.LEFT, padx=(0, S.G3))
            ic_c.create_oval(2, 2, 42, 42, fill=ic_bg, outline="")
            ic_c.create_text(23, 23, text=icon,
                             font=("Segoe UI Symbol", 16), fill=ic_fg)

            # 中间文字区
            mid = tk.Frame(row, bg=S.BG_CARD)
            mid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tk.Label(mid, text=title,
                     font=(S.FF, S.LG, "bold"),
                     bg=S.BG_CARD, fg=S.T1, anchor="w").pack(anchor="w")
            tk.Label(mid, text=desc,
                     font=(S.FF, S.XS),
                     bg=S.BG_CARD, fg=S.T3, anchor="w").pack(anchor="w")
            res_lbl = tk.Label(mid, text="—",
                               font=(S.FF, S.SM),
                               bg=S.BG_CARD, fg=S.TD, anchor="w")
            res_lbl.pack(anchor="w", pady=(2, 0))

            # 右侧状态徽章
            badge = StatusBadge(row, size=14, bg=S.BG_CARD)
            badge.pack(side=tk.RIGHT, padx=(S.G3, 0))

            # 修复建议区（初始隐藏）
            sug_frame = tk.Frame(body, bg=S.BG_CARD)

            self.check_cards[item_id] = {
                "card":      card,
                "badge":     badge,
                "res_lbl":   res_lbl,
                "sug_frame": sug_frame,
                "ic_c":      ic_c,
                "ic_bg":     ic_bg,
                "ic_fg":     ic_fg,
            }

        # 操作栏
        act = tk.Frame(sf, bg=S.BG_APP)
        act.pack(fill=tk.X, pady=(S.G2, S.G3))

        self.check_start_btn = EdgeButton(
            act, "▶  开始检测", command=self._run_check,
            variant="primary", width=148, height=42, font_size=S.MD,
            parent_bg=S.BG_APP)
        self.check_start_btn.pack(side=tk.LEFT, padx=(0, S.G3))

        self.check_prog = EdgeProgressBar(act, width=240, height=6, bg=S.BG_APP)
        self.check_prog.pack(side=tk.LEFT, padx=(0, S.G2))

        self.check_prog_lbl = tk.Label(act, text="",
                                       font=(S.FF, S.XS),
                                       bg=S.BG_APP, fg=S.T3)
        self.check_prog_lbl.pack(side=tk.LEFT)

        self.summary_frame = tk.Frame(sf, bg=S.BG_APP)
        self.summary_frame.pack(fill=tk.X, pady=(0, S.G2))

        # 恢复已有结果
        if self.check_results:
            self._restore_check_ui()

        scroll.scroll_to_top()

    def _restore_check_ui(self):
        """页面重建后恢复上次检测结果"""
        for sid, result in self.check_results.items():
            d = self.check_cards.get(sid)
            if not d:
                continue
            if sid == "vpn":
                level = result.get("risk_level", "none")
                d["badge"].set_status(self._RISK_BADGE.get(level, "good"))
                self._safe_cfg(d["res_lbl"], text=result.get("summary", ""),
                               fg=self._RISK_COLOR.get(level, S.SUCCESS))
                if result.get("active"):
                    self._show_vpn_detail(sid, result)
                continue
            ok = result.get("status") == "ok"
            d["badge"].set_status("good" if ok else "bad")
            color = S.SUCCESS if ok else S.DANGER
            self._safe_cfg(d["res_lbl"], text=result.get("summary", ""), fg=color)
            if not ok:
                self._show_suggestions(sid, d)
        self._show_summary()

    def _run_check(self):
        if self._checking:
            return
        self._checking = True
        self.check_results.clear()

        self.check_start_btn.configure_state(False)
        self.check_prog.set_progress(0)
        self._safe_cfg(self.check_prog_lbl, text="准备中…")

        for d in self.check_cards.values():
            d["badge"].set_status("pending")
            self._safe_cfg(d["res_lbl"], text="等待检测…", fg=S.TD)
            for w in d["sug_frame"].winfo_children():
                w.destroy()
            d["sug_frame"].pack_forget()

        if self._alive(self.summary_frame):
            for w in self.summary_frame.winfo_children():
                w.destroy()

        threading.Thread(target=self._do_check, daemon=True).start()

    # 风险等级 → 徽章状态 / 颜色
    _RISK_BADGE = {"none": "good", "low": "good",
                   "medium": "warning", "high": "bad"}
    _RISK_COLOR = {"none": S.SUCCESS, "low": S.SUCCESS,
                   "medium": S.WARNING_FG, "high": S.DANGER}

    def _do_check(self):
        steps = [
            ("internet", self._step_internet),
            ("dns",      self._step_dns),
            ("ping",     self._step_ping),
            ("vpn",      self._step_vpn),
        ]
        total = len(steps)
        try:
            for i, (sid, fn) in enumerate(steps):
                self.msg_queue.put(("badge",        sid,  "running"))
                self.msg_queue.put(("check_result", sid,  "检测中…", S.T2))
                self.msg_queue.put(("progress",     int(i / total * 100),
                                    f"检测 {i+1} / {total}…"))
                result = fn()
                self.check_results[sid] = result

                if sid == "vpn":
                    # VPN 为信息型：徽章/颜色按风险等级，展示风险详情
                    level = result.get("risk_level", "none")
                    self.msg_queue.put(("badge", sid, self._RISK_BADGE.get(level, "good")))
                    self.msg_queue.put(("check_result", sid,
                                        result.get("summary", ""),
                                        self._RISK_COLOR.get(level, S.SUCCESS)))
                    if result.get("active"):
                        self.msg_queue.put(("show_vpn_detail", sid, result))
                else:
                    ok  = result.get("status") == "ok"
                    col = S.SUCCESS if ok else S.DANGER
                    self.msg_queue.put(("badge",        sid,  "good" if ok else "bad"))
                    self.msg_queue.put(("check_result", sid,  result.get("summary", ""), col))
                    if not ok:
                        self.msg_queue.put(("show_suggestions", sid, None))
                time.sleep(0.15)

            hist.append(self.check_results)
            self.msg_queue.put(("progress",   100, "检测完成"))
            self.msg_queue.put(("check_done", None, None))
        finally:
            self._checking = False

    def _step_internet(self):
        ok, host, err = NetworkUtils.check_internet()
        return {
            "status":  "ok" if ok else "fail",
            "summary": f"✓ 连接正常  ({host})" if ok else f"✗ {err}",
        }

    def _step_dns(self):
        ok, ips, info = NetworkUtils.check_dns()
        if ok:
            return {"status": "ok",
                    "summary": f"✓ 解析正常  {ips[0]}  · {info} ms"}
        return {"status": "fail", "summary": f"✗ 解析失败：{info}"}

    def _step_ping(self):
        ok, avg, lost, jitter = NetworkUtils.ping_host()
        if ok:
            jstr = f"  抖动 {jitter} ms" if jitter is not None else ""
            return {"status": "ok",
                    "summary": f"✓ 延迟 {avg} ms  丢包 {lost}%{jstr}"}
        return {"status": "fail",
                "summary": f"✗ 丢包率 {lost}%（网络不稳定）"}

    def _step_vpn(self):
        r = VPNDetector.detect()
        r["status"] = "ok"           # 信息型，不计入异常
        r["informational"] = True
        if r.get("active"):
            r["summary"] = f"⚠ {r['summary']}  · 风险{r['risk_label']}"
        else:
            r["summary"] = "✓ 未使用 VPN / 代理"
        return r

    def _show_vpn_detail(self, sid, result):
        """在 VPN 卡片内展示类型与风险详情"""
        d = self.check_cards.get(sid)
        if not d:
            return
        sug_frame = d["sug_frame"]
        for w in sug_frame.winfo_children():
            w.destroy()

        tk.Frame(d["card"].inner, bg=S.BORDER, height=1).pack(fill=tk.X, padx=S.G4)

        inner = tk.Frame(sug_frame, bg=S.BG_CARD)
        inner.pack(fill=tk.X, padx=S.G4, pady=S.G3)

        level = result.get("risk_level", "none")
        rcolor = self._RISK_COLOR.get(level, S.SUCCESS)

        # 风险等级标题行
        head = tk.Frame(inner, bg=S.BG_CARD)
        head.pack(fill=tk.X, anchor="w")
        tk.Label(head, text=f"⛨ 风险等级：{result.get('risk_label','无')}",
                 font=(S.FF, S.XS, "bold"),
                 bg=S.BG_CARD, fg=rcolor).pack(side=tk.LEFT)

        # 检测到的组件
        names = result.get("names", [])
        if names:
            tk.Label(inner, text="检测到：" + "；".join(names),
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.T2,
                     anchor="w", justify="left", wraplength=560
                     ).pack(anchor="w", pady=(2, 0))

        # 风险说明逐条
        for reason in result.get("reasons", []):
            tk.Label(inner, text="· " + reason,
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.T3,
                     anchor="w", justify="left", wraplength=560
                     ).pack(anchor="w")

        sug_frame.pack(fill=tk.X)

    def _show_suggestions(self, sid, d):
        """在卡片内展示修复建议按钮"""
        sug_frame = d["sug_frame"]
        for w in sug_frame.winfo_children():
            w.destroy()

        sep = tk.Frame(d["card"].inner, bg=S.BORDER, height=1)
        sep.pack(fill=tk.X, padx=S.G4)

        inner = tk.Frame(sug_frame, bg=S.BG_CARD)
        inner.pack(fill=tk.X, padx=S.G4, pady=S.G3)

        tk.Label(inner, text="建议修复：",
                 font=(S.FF, S.XS, "bold"),
                 bg=S.BG_CARD, fg=S.T2).pack(side=tk.LEFT, padx=(0, S.G2))

        feedback_lbl = tk.Label(inner, text="",
                                font=(S.FF, S.XS),
                                bg=S.BG_CARD, fg=S.T2)
        feedback_lbl.pack(side=tk.RIGHT, padx=(S.G2, 0))

        for repair_id, btn_text in _SUGGESTIONS.get(sid, []):
            EdgeButton(inner, btn_text,
                       command=lambda rid=repair_id, lbl=feedback_lbl:
                           self._quick_repair(rid, lbl),
                       variant="soft", width=110, height=28,
                       font_size=S.XS, parent_bg=S.BG_CARD
                       ).pack(side=tk.LEFT, padx=(0, S.G2))

        sug_frame.pack(fill=tk.X)

    def _quick_repair(self, repair_id, feedback_lbl):
        self._safe_cfg(feedback_lbl, text="修复中…", fg=S.WARNING_FG)

        def run():
            fn = _REPAIR_FUNCS.get(repair_id)
            if fn:
                ok, msg = fn()
                self.msg_queue.put(("repair_feedback", feedback_lbl,
                                    {"text": msg, "fg": S.SUCCESS if ok else S.DANGER}))

        threading.Thread(target=run, daemon=True).start()

    def _show_summary(self):
        if not self._alive(self.summary_frame):
            return
        for w in self.summary_frame.winfo_children():
            w.destroy()
        if not self.check_results:
            return

        # 仅统计连通性检测项，VPN 为信息型不计入异常
        conn = {k: v for k, v in self.check_results.items()
                if not v.get("informational")}
        ok_n  = sum(1 for r in conn.values() if r.get("status") == "ok")
        total = len(conn)
        all_ok = ok_n == total

        card = ShadowCard(self.summary_frame)
        card.pack(fill=tk.X)
        inner = tk.Frame(card.inner, bg=S.BG_CARD)
        inner.pack(fill=tk.X, padx=S.G4, pady=S.G4)

        emoji = "✅" if all_ok else "⚠️"
        title = "网络状态良好" if all_ok else f"发现 {total - ok_n} 项异常"
        color = S.SUCCESS if all_ok else S.WARNING_FG
        detail = f"全部 {total} 项通过" if all_ok else f"{ok_n} / {total} 项通过"

        tk.Label(inner, text=emoji, font=("Segoe UI Emoji", 26),
                 bg=S.BG_CARD).pack(side=tk.LEFT, padx=(0, S.G3))
        tf = tk.Frame(inner, bg=S.BG_CARD)
        tf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(tf, text=title,
                 font=(S.FF, S.LG, "bold"),
                 bg=S.BG_CARD, fg=color, anchor="w").pack(anchor="w")
        tk.Label(tf, text=detail,
                 font=(S.FF, S.XS),
                 bg=S.BG_CARD, fg=S.T3, anchor="w").pack(anchor="w")

        if not all_ok:
            EdgeButton(inner, "前往修复",
                       command=lambda: self._navigate("repair"),
                       variant="warning", width=90, height=32,
                       font_size=S.SM, parent_bg=S.BG_CARD
                       ).pack(side=tk.RIGHT, padx=(S.G3, 0))

    # ══════════════════════════════════════════════════════════
    #  网速测试页面
    # ══════════════════════════════════════════════════════════

    def _page_speed(self):
        self._header("网速测试", "多源实测下载速度，实时仪表盘显示")

        scroll = EdgeScrollFrame(self._content, bg=S.BG_APP)
        scroll.pack(fill=tk.BOTH, expand=True, padx=S.G8, pady=(0, S.G4))
        sf = scroll.scroll_frame

        # ── 仪表盘 + 详情 ──
        gauge_card = ShadowCard(sf)
        gauge_card.pack(fill=tk.X, pady=(0, S.G3))
        g_body = gauge_card.inner

        g_row = tk.Frame(g_body, bg=S.BG_CARD)
        g_row.pack(fill=tk.X, padx=S.G5, pady=S.G5)

        # 左：速度仪表盘
        self.speed_gauge = SpeedGauge(g_row, bg=S.BG_CARD)
        self.speed_gauge.pack(side=tk.LEFT, padx=(0, S.G8))

        # 右：详情列
        detail_col = tk.Frame(g_row, bg=S.BG_CARD)
        detail_col.pack(side=tk.LEFT, fill=tk.Y, anchor="n", pady=S.G4)

        self.speed_detail = {}
        rows = [
            ("avg",   "平均速度", "-- Mbps"),
            ("peak",  "峰值速度", "-- Mbps"),
            ("dl_mb", "下载量",   "-- MB"),
            ("time",  "耗时",     "-- 秒"),
            ("src",   "测速源",   "未测试"),
            ("grade", "网络评级", "--"),
        ]
        for key, lbl, default in rows:
            row = tk.Frame(detail_col, bg=S.BG_CARD)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=lbl + "：",
                     font=(S.FF, S.SM, "bold"),
                     bg=S.BG_CARD, fg=S.T2, width=8, anchor="w").pack(side=tk.LEFT)
            val = tk.Label(row, text=default,
                           font=(S.FF, S.MD),
                           bg=S.BG_CARD, fg=S.T1, anchor="w")
            val.pack(side=tk.LEFT)
            self.speed_detail[key] = val

        # ── 分源进度列表 ──
        src_card = ShadowCard(sf)
        src_card.pack(fill=tk.X, pady=(0, S.G3))
        self._speed_src_frame = tk.Frame(src_card.inner, bg=S.BG_CARD)
        self._speed_src_frame.pack(fill=tk.X, padx=S.G4, pady=S.G3)
        tk.Label(self._speed_src_frame, text="各测速源结果",
                 font=(S.FF, S.SM, "bold"),
                 bg=S.BG_CARD, fg=S.T2, anchor="w").pack(anchor="w", pady=(0, S.G2))
        self._speed_src_rows = {}
        for _, _, name in SpeedTester.SPEED_TEST_URLS:
            row = tk.Frame(self._speed_src_frame, bg=S.BG_CARD)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=name,
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.T3,
                     width=12, anchor="w").pack(side=tk.LEFT)
            bar = EdgeProgressBar(row, width=200, height=5, bg=S.BG_CARD)
            bar.pack(side=tk.LEFT, padx=(0, S.G2))
            val_lbl = tk.Label(row, text="等待…",
                               font=(S.FF, S.XS),
                               bg=S.BG_CARD, fg=S.TD, anchor="w")
            val_lbl.pack(side=tk.LEFT)
            self._speed_src_rows[name] = {"bar": bar, "lbl": val_lbl}

        # ── 进度 + 按钮 ──
        ctrl = tk.Frame(sf, bg=S.BG_APP)
        ctrl.pack(fill=tk.X, pady=(0, S.G2))

        self.speed_prog = EdgeProgressBar(ctrl, width=640, height=6, bg=S.BG_APP)
        self.speed_prog.pack(pady=(0, S.G2))

        self.speed_status_lbl = tk.Label(ctrl, text="准备就绪",
                                         font=(S.FF, S.XS),
                                         bg=S.BG_APP, fg=S.T3)
        self.speed_status_lbl.pack(anchor="w", pady=(0, S.G3))

        btn_row = tk.Frame(ctrl, bg=S.BG_APP)
        btn_row.pack(anchor="w")

        self.speed_start_btn = EdgeButton(
            btn_row, "▶  开始测速", command=self._run_speed,
            variant="primary", width=140, height=42, font_size=S.MD,
            parent_bg=S.BG_APP)
        self.speed_start_btn.pack(side=tk.LEFT, padx=(0, S.G2))

        self.speed_stop_btn = EdgeButton(
            btn_row, "⏹  停止", command=self._stop_speed,
            variant="outline", width=100, height=42, font_size=S.MD,
            parent_bg=S.BG_APP)
        self.speed_stop_btn.pack(side=tk.LEFT)
        self.speed_stop_btn.configure_state(False)

        self.speed_cancelled = False
        scroll.scroll_to_top()

    def _run_speed(self):
        if self._speed_run:
            return
        self._speed_run = True
        self.speed_cancelled = False

        self.speed_start_btn.configure_state(False)
        self.speed_stop_btn.configure_state(True)
        self.speed_prog.set_progress(0)
        self._safe_cfg(self.speed_status_lbl, text="连接测速源中…", fg=S.T2)

        if self._alive(self.speed_gauge):
            self.speed_gauge.set_speed(0)
        for val in self.speed_detail.values():
            self._safe_cfg(val, text="测速中…", fg=S.T3)
        for info in self._speed_src_rows.values():
            info["bar"].set_progress(0)
            self._safe_cfg(info["lbl"], text="等待…", fg=S.TD)

        threading.Thread(target=self._do_speed, daemon=True).start()

    def _stop_speed(self):
        self.speed_cancelled = True
        self._safe_cfg(self.speed_status_lbl, text="正在停止…", fg=S.WARNING_FG)

    def _do_speed(self):
        urls   = SpeedTester.SPEED_TEST_URLS
        n      = len(urls)
        best_s = best_dl = best_el = 0
        best_n = ""
        peak   = 0
        speeds = []

        try:
            for i, (url, expected, name) in enumerate(urls):
                if self.speed_cancelled:
                    break

                base_pct = int(i / n * 100)
                self.msg_queue.put(("speed_status", None,
                    (base_pct, f"测试 {name}… ({i+1}/{n})", S.T2)))

                max_b = expected if expected > 0 else 2 * 1024 * 1024

                def live_cb(spd, src_name=name, b=base_pct, total=n):
                    if not self.speed_cancelled:
                        self.msg_queue.put(("speed_live", src_name, spd))

                ok, spd, dl, el, err = SpeedTester.test_speed_sample(
                    url, timeout=15, max_bytes=max_b, progress_cb=live_cb)

                if self.speed_cancelled:
                    break

                if ok and spd > 0:
                    speeds.append(spd)
                    if spd > peak:
                        peak = spd
                    if spd > best_s:
                        best_s, best_dl, best_el, best_n = spd, dl, el, name
                    status_text = f"{spd:.1f} Mbps"
                    pct_fill = min(int(spd / max(best_s, spd, 1) * 100), 100)
                    color = S.ACCENT
                else:
                    err_short = (err or '').strip()
                    if len(err_short) > 40:
                        err_short = err_short[:38] + "…"
                    status_text = f"失败 {err_short}" if err_short else "失败"
                    pct_fill = 0
                    color = S.DANGER

                self.msg_queue.put(("speed_src_result", name,
                    {"pct": pct_fill, "text": status_text, "color": color}))
                self.msg_queue.put(("speed_status", None,
                    (int((i + 1) / n * 100), f"{name}: {status_text}", color)))
                time.sleep(0.1)

            if self.speed_cancelled:
                self.msg_queue.put(("speed_status", None,
                    (0, "已取消", S.T3)))
                self.msg_queue.put(("speed_result", None, None))
                return

            if not speeds:
                self.msg_queue.put(("speed_status", None,
                    (0, "所有测速源均不可达", S.DANGER)))
                self.msg_queue.put(("speed_result", None, None))
                return

            avg = round(sum(speeds) / len(speeds), 2)
            if   best_s >= 50: grade, gc = "⚡ 极速",  S.SUCCESS
            elif best_s >= 20: grade, gc = "🌟 高速",  S.SUCCESS
            elif best_s >= 5:  grade, gc = "👍 标准",  S.ACCENT
            elif best_s >= 1:  grade, gc = "📶 基础",  S.WARNING_FG
            else:              grade, gc = "🐢 较慢",  S.DANGER

            self.msg_queue.put(("speed_result", None, {
                "best":  best_s,
                "avg":   avg,
                "peak":  round(peak, 2),
                "dl_mb": round(best_dl / (1024 * 1024), 2),
                "el":    best_el,
                "src":   best_n,
                "grade": grade,
                "gc":    gc,
            }))
            self.msg_queue.put(("speed_status", None, (100, "测速完成", S.SUCCESS)))
        finally:
            self._speed_run = False

    def _show_speed_result(self, result):
        if not self._alive(self.speed_gauge):
            return
        if result is None:
            self.speed_gauge.set_speed(0)
            for val in self.speed_detail.values():
                if self._alive(val):
                    val.config(text="—", fg=S.DANGER)
        else:
            gc = result["gc"]
            self.speed_gauge.set_speed(result["best"])
            mapping = {
                "avg":   f"{result['avg']} Mbps",
                "peak":  f"{result['peak']} Mbps",
                "dl_mb": f"{result['dl_mb']} MB",
                "time":  f"{result['el']} 秒",
                "src":   result["src"],
                "grade": result["grade"],
            }
            for key, text in mapping.items():
                val = self.speed_detail.get(key)
                if val and self._alive(val):
                    val.config(text=text, fg=gc if key == "grade" else S.T1)

        if self._alive(self.speed_start_btn):
            self.speed_start_btn.configure_state(True)
        if self._alive(self.speed_stop_btn):
            self.speed_stop_btn.configure_state(False)
        self.speed_cancelled = False

    # ══════════════════════════════════════════════════════════
    #  智能修复页面
    # ══════════════════════════════════════════════════════════

    def _page_repair(self):
        self._header("智能修复", "一键修复常见网络问题")

        # 非管理员提示
        if not self._admin:
            warn = tk.Frame(self._content, bg=S.WARNING_BG,
                            highlightthickness=1, highlightbackground=S.WARNING_FG)
            warn.pack(fill=tk.X, padx=S.G8, pady=(0, S.G3))
            tk.Label(warn, text="⚠  当前非管理员模式，Winsock 重置、IP 释放等操作可能失败。请以管理员身份运行。",
                     font=(S.FF, S.SM), bg=S.WARNING_BG, fg=S.WARNING,
                     wraplength=700, justify="left"
                     ).pack(padx=S.G4, pady=S.G3, anchor="w")

        scroll = EdgeScrollFrame(self._content, bg=S.BG_APP)
        scroll.pack(fill=tk.BOTH, expand=True, padx=S.G8, pady=(0, S.G4))
        sf = scroll.scroll_frame

        items = [
            ("flush_dns",    "刷新 DNS 缓存",
             "清除本地 DNS 缓存，解决域名解析异常", "⚠ 安全操作，不影响正常使用",
             "🗂", False),
            ("reset_proxy",  "清除代理设置",
             "关闭系统代理，修复代理导致的连接问题",  "⚠ 会关闭当前代理",
             "🔗", False),
            ("reset_winsock","重置 Winsock",
             "重置 Windows 网络协议栈",             "⚠ 需要重启计算机生效",
             "⚙", True),
            ("reset_ip",     "释放并更新 IP",
             "重新获取 IP 地址，解决 IP 冲突",       "⚠ 操作期间短暂断网",
             "🔄", True),
            ("reset_adapter","重置网络适配器",
             "重置所有网络适配器到默认配置",          "⚠ 需要重启计算机生效",
             "🔌", True),
        ]

        self.repair_rows = {}

        for item_id, title, desc, warn_txt, icon, need_admin in items:
            card = ShadowCard(sf)
            card.pack(fill=tk.X, pady=(0, S.G3))
            body = card.inner

            row = tk.Frame(body, bg=S.BG_CARD)
            row.pack(fill=tk.X, padx=S.G4, pady=S.G4)

            tk.Label(row, text=icon, font=("Segoe UI Emoji", 22),
                     bg=S.BG_CARD).pack(side=tk.LEFT, padx=(0, S.G3))

            info_f = tk.Frame(row, bg=S.BG_CARD)
            info_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            hl = tk.Frame(info_f, bg=S.BG_CARD)
            hl.pack(anchor="w")
            tk.Label(hl, text=title,
                     font=(S.FF, S.MD, "bold"),
                     bg=S.BG_CARD, fg=S.T1).pack(side=tk.LEFT)
            if need_admin and not self._admin:
                tk.Label(hl, text=" 需要管理员",
                         font=(S.FF, S.XS),
                         bg=S.BG_CARD, fg=S.WARNING_FG).pack(side=tk.LEFT)

            tk.Label(info_f, text=desc,
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.T3, anchor="w"
                     ).pack(anchor="w")
            tk.Label(info_f, text=warn_txt,
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.WARNING_FG, anchor="w"
                     ).pack(anchor="w")
            status_lbl = tk.Label(info_f, text="",
                                  font=(S.FF, S.XS),
                                  bg=S.BG_CARD, fg=S.SUCCESS, anchor="w")
            status_lbl.pack(anchor="w")

            btn = EdgeButton(row, "执行",
                             command=lambda iid=item_id: self._do_repair(iid),
                             variant="outline", width=80, height=34,
                             font_size=S.SM, parent_bg=S.BG_CARD)
            btn.pack(side=tk.RIGHT, padx=(S.G3, 0))

            self.repair_rows[item_id] = {"btn": btn, "lbl": status_lbl}

        scroll.scroll_to_top()

    def _do_repair(self, item_id):
        d = self.repair_rows.get(item_id)
        if not d:
            return
        d["btn"].configure_state(False)
        self._safe_cfg(d["lbl"], text="修复中…", fg=S.WARNING_FG)

        def run():
            fn = _REPAIR_FUNCS.get(item_id)
            ok, msg = fn() if fn else (False, "未知操作")
            self.msg_queue.put(("repair_result", item_id,
                {"text": msg, "fg": S.SUCCESS if ok else S.DANGER}))

        threading.Thread(target=run, daemon=True).start()

    # ══════════════════════════════════════════════════════════
    #  网络信息页面
    # ══════════════════════════════════════════════════════════

    def _page_info(self):
        self._header("网络信息", "查看当前设备的网络配置详情")

        scroll = EdgeScrollFrame(self._content, bg=S.BG_APP)
        scroll.pack(fill=tk.BOTH, expand=True, padx=S.G8, pady=(0, S.G4))
        sf = scroll.scroll_frame

        act = tk.Frame(sf, bg=S.BG_APP)
        act.pack(fill=tk.X, pady=(0, S.G3))

        self.info_refresh_btn = EdgeButton(
            act, "↺  刷新", command=self._refresh_info,
            variant="outline", width=96, height=34,
            font_size=S.SM, parent_bg=S.BG_APP)
        self.info_refresh_btn.pack(side=tk.RIGHT)

        self.info_content_frame = tk.Frame(sf, bg=S.BG_APP)
        self.info_content_frame.pack(fill=tk.BOTH, expand=True)

        self._refresh_info()
        scroll.scroll_to_top()

    def _refresh_info(self):
        self.info_refresh_btn.configure_state(False)
        threading.Thread(
            target=lambda: self.msg_queue.put(
                ("net_info", None, NetworkUtils.get_network_info())),
            daemon=True).start()

    def _show_info(self, info):
        if not self._alive(self.info_content_frame):
            return
        for w in self.info_content_frame.winfo_children():
            w.destroy()

        rows = [
            ("💻", "主机名",    info.get("hostname", "未知")),
            ("🌐", "IPv4 地址", "\n".join(info.get("ipv4", ["无法获取"]))),
            ("🚪", "默认网关",  info.get("gateway") or "无法获取"),
            ("🔗", "MAC 地址",  info.get("mac", "未知")),
            ("📡", "DNS 服务器","\n".join(info.get("dns_servers", ["自动获取"]))),
        ]

        for emoji, label, value in rows:
            card = ShadowCard(self.info_content_frame)
            card.pack(fill=tk.X, pady=(0, S.G3))
            inner = tk.Frame(card.inner, bg=S.BG_CARD)
            inner.pack(fill=tk.X, padx=S.G4, pady=S.G4)

            tk.Label(inner, text=emoji,
                     font=("Segoe UI Emoji", 18), bg=S.BG_CARD
                     ).pack(side=tk.LEFT, padx=(0, S.G3))

            tf = tk.Frame(inner, bg=S.BG_CARD)
            tf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tk.Label(tf, text=label,
                     font=(S.FF, S.XS), bg=S.BG_CARD, fg=S.T3, anchor="w"
                     ).pack(anchor="w")
            tk.Label(tf, text=value,
                     font=(S.FF, S.MD, "bold"),
                     bg=S.BG_CARD, fg=S.T1, anchor="w", justify="left"
                     ).pack(anchor="w")

            # 复制按钮
            EdgeButton(inner, "复制",
                       command=lambda v=value: self._copy(v),
                       variant="ghost", width=56, height=28,
                       font_size=S.XS, parent_bg=S.BG_CARD
                       ).pack(side=tk.RIGHT)

        if self._alive(self.info_refresh_btn):
            self.info_refresh_btn.configure_state(True)

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text.replace("\n", "  "))

    # ══════════════════════════════════════════════════════════
    #  检测历史页面
    # ══════════════════════════════════════════════════════════

    def _page_history(self):
        self._header("检测历史", f"最近 {hist.MAX_RECORDS} 条记录，持久保存于本地")

        scroll = EdgeScrollFrame(self._content, bg=S.BG_APP)
        scroll.pack(fill=tk.BOTH, expand=True, padx=S.G8, pady=(0, S.G4))
        sf = scroll.scroll_frame

        records = hist.load_all()

        if not records:
            card = ShadowCard(sf)
            card.pack(fill=tk.X, pady=S.G3)
            inner = tk.Frame(card.inner, bg=S.BG_CARD)
            inner.pack(expand=True, pady=S.G8)
            tk.Label(inner, text="📋", font=("Segoe UI Emoji", 40),
                     bg=S.BG_CARD).pack()
            tk.Label(inner, text="暂无历史记录",
                     font=(S.FF, S.LG, "bold"),
                     bg=S.BG_CARD, fg=S.T1).pack(pady=(S.G3, 0))
            tk.Label(inner, text='在"一键检测"完成检测后，结果将自动保存到此处',
                     font=(S.FF, S.SM), bg=S.BG_CARD, fg=S.T3).pack()
        else:
            names = {"internet": "互联网", "dns": "DNS", "ping": "延迟"}
            for rec in records:
                ts      = rec.get("ts", "")
                results = rec.get("results", {})
                all_ok  = all(r.get("status") == "ok" for r in results.values())

                card = ShadowCard(sf)
                card.pack(fill=tk.X, pady=(0, S.G3))
                inner = tk.Frame(card.inner, bg=S.BG_CARD)
                inner.pack(fill=tk.X, padx=S.G4, pady=S.G3)

                # 时间戳行
                ts_row = tk.Frame(inner, bg=S.BG_CARD)
                ts_row.pack(fill=tk.X, pady=(0, S.G2))
                status_icon = "✅" if all_ok else "⚠️"
                tk.Label(ts_row, text=status_icon,
                         font=("Segoe UI Emoji", 13), bg=S.BG_CARD
                         ).pack(side=tk.LEFT, padx=(0, S.G2))
                tk.Label(ts_row, text=ts,
                         font=(S.FF, S.SM, "bold"),
                         bg=S.BG_CARD, fg=S.T1).pack(side=tk.LEFT)

                # 结果行
                res_row = tk.Frame(inner, bg=S.BG_CARD)
                res_row.pack(fill=tk.X, pady=(0, S.G1))
                for sid, res in results.items():
                    ok    = res.get("status") == "ok"
                    color = S.SUCCESS if ok else S.DANGER
                    mark  = "✓" if ok else "✗"
                    col_f = tk.Frame(res_row, bg=S.BG_CARD)
                    col_f.pack(side=tk.LEFT, padx=(0, S.G5))
                    tk.Label(col_f, text=f"{mark} {names.get(sid, sid)}",
                             font=(S.FF, S.XS, "bold"),
                             bg=S.BG_CARD, fg=color).pack(anchor="w")
                    summary = res.get("summary", "")
                    if summary:
                        tk.Label(col_f, text=summary,
                                 font=(S.FF, S.XS),
                                 bg=S.BG_CARD, fg=S.T3,
                                 wraplength=200, justify="left"
                                 ).pack(anchor="w")

        scroll.scroll_to_top()

    # ══════════════════════════════════════════════════════════
    #  消息队列轮询
    # ══════════════════════════════════════════════════════════

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                mtype = msg[0]
                mid   = msg[1]
                data  = msg[2] if len(msg) > 2 else None

                # 检测页
                if mtype == "badge":
                    d = self.check_cards.get(mid)
                    if d and self._alive(d["badge"]):
                        d["badge"].set_status(data)

                elif mtype == "check_result":
                    d = self.check_cards.get(mid)
                    if d:
                        self._safe_cfg(d["res_lbl"],
                                       text=msg[2], fg=msg[3])

                elif mtype == "show_suggestions":
                    d = self.check_cards.get(mid)
                    if d:
                        self._show_suggestions(mid, d)

                elif mtype == "show_vpn_detail":
                    self._show_vpn_detail(mid, data)

                elif mtype == "progress":
                    if self._alive(self.check_prog):
                        self.check_prog.set_progress(mid)
                    self._safe_cfg(self.check_prog_lbl, text=data)

                elif mtype == "check_done":
                    if self._alive(self.check_start_btn):
                        self.check_start_btn.configure_state(True)
                    self._show_summary()

                elif mtype == "repair_feedback":
                    widget, payload = mid, data
                    self._safe_cfg(widget, text=payload["text"], fg=payload["fg"])

                # 修复页
                elif mtype == "repair_result":
                    d = self.repair_rows.get(mid)
                    if d:
                        if self._alive(d["btn"]):
                            d["btn"].configure_state(True)
                        self._safe_cfg(d["lbl"], text=data["text"], fg=data["fg"])

                # 网速页
                elif mtype == "speed_status":
                    pct, text, color = data
                    if self._alive(self.speed_prog):
                        self.speed_prog.set_progress(pct)
                    self._safe_cfg(self.speed_status_lbl, text=text, fg=color)

                elif mtype == "speed_live":
                    # mid = source name, data = live speed
                    if self._alive(self.speed_gauge):
                        self.speed_gauge.set_speed(data, live=True)
                    row = self._speed_src_rows.get(mid)
                    if row:
                        max_known = max(
                            (float(r["lbl"].cget("text").split()[0])
                             for r in self._speed_src_rows.values()
                             if r["lbl"].cget("text")[0].isdigit()),
                            default=data) if data > 0 else 1
                        pct = min(int(data / max(max_known, data) * 100), 100)
                        row["bar"].set_progress(pct, color=S.ACCENT)
                        self._safe_cfg(row["lbl"],
                                       text=f"{data:.1f} Mbps ↗", fg=S.ACCENT)

                elif mtype == "speed_src_result":
                    row = self._speed_src_rows.get(mid)
                    if row:
                        row["bar"].set_progress(data["pct"], color=data["color"])
                        self._safe_cfg(row["lbl"],
                                       text=data["text"], fg=data["color"])

                elif mtype == "speed_result":
                    if self.current_page == "speed":
                        self._show_speed_result(data)

                # 信息页
                elif mtype == "net_info":
                    self._show_info(data)

        except queue.Empty:
            pass
        self.root.after(60, self._poll_queue)

    # ── 启动 ──────────────────────────────────────────────────

    def run(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w  = self.root.winfo_width()
        h  = self.root.winfo_height()
        self.root.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")
        self.root.mainloop()


if __name__ == "__main__":
    app = NetworkToolApp()
    app.run()
