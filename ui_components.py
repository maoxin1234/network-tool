#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI 组件模块 — Windows 11 Fluent Design
"""

import tkinter as tk
from tkinter import ttk
import math


# ══════════════════════════════════════════════════════════════
#  样式常量
# ══════════════════════════════════════════════════════════════

class S:
    # 主题色
    ACCENT       = "#005FB8"
    ACCENT_H     = "#004EA0"
    ACCENT_L     = "#EBF3FB"
    ACCENT_DARK  = "#003D80"

    # 状态色
    SUCCESS      = "#0E7A0E"
    SUCCESS_BG   = "#DFF6DD"
    WARNING      = "#9B5C00"
    WARNING_BG   = "#FFF4CE"
    WARNING_FG   = "#F0A500"
    DANGER       = "#C42B1C"
    DANGER_BG    = "#FDE7E9"

    # 背景层次
    BG_APP   = "#EFEFEF"
    BG_LAYER = "#F8F8F8"
    BG_CARD  = "#FFFFFF"
    BG_SIDE  = "#E5E5E5"
    BG_SIDE_H= "#D8D8D8"
    BG_HOVER = "#EBF3FB"

    # 阴影 / 边框
    SHADOW   = "#C8C8C8"
    BORDER   = "#E3E3E3"
    BORDER_S = "#C0C0C0"

    # 文字
    T1  = "#1A1A1A"
    T2  = "#5A5A5A"
    T3  = "#8A8A8A"
    TD  = "#B5B5B5"
    TW  = "#FFFFFF"

    # 字体
    FF   = "Microsoft YaHei UI"
    XS   = 9
    SM   = 10
    MD   = 11
    LG   = 13
    XL   = 16
    XXL  = 22

    # 圆角
    R_SM = 5
    R_MD = 8
    R_LG = 12
    R_XL = 16

    # 间距 (8px 网格)
    G1 = 4
    G2 = 8
    G3 = 12
    G4 = 16
    G5 = 20
    G6 = 24
    G8 = 32

    SIDE_W = 200


# ── 工具函数 ──────────────────────────────────────────────────

def _poly(x, y, w, h, r):
    """圆角矩形 polygon 点列表"""
    r = min(r, w // 2, h // 2)
    return [
        x+r, y,  x+w-r, y,
        x+w, y,  x+w, y+r,
        x+w, y+h-r,  x+w, y+h,
        x+w-r, y+h,  x+r, y+h,
        x, y+h,  x, y+h-r,
        x, y+r,  x, y,
    ]


# ══════════════════════════════════════════════════════════════
#  基础组件
# ══════════════════════════════════════════════════════════════

class ShadowCard(tk.Frame):
    """带阴影的白色卡片"""

    def __init__(self, parent, bg=S.BG_CARD, **kwargs):
        super().__init__(parent, bg=S.SHADOW, bd=0, **kwargs)
        mid = tk.Frame(self, bg=S.BORDER, bd=0)
        mid.pack(fill=tk.BOTH, expand=True, padx=(0, 2), pady=(0, 2))
        self.inner = tk.Frame(mid, bg=bg, bd=0)
        self.inner.pack(fill=tk.BOTH, expand=True, padx=(0, 1), pady=(0, 1))


class EdgeButton(tk.Canvas):
    """Fluent 风格按钮"""

    _V = {
        "primary": dict(bg=S.ACCENT,   bgh=S.ACCENT_H,  bgd="#C0C0C0", fg=S.TW,      fgd=S.TD),
        "success": dict(bg=S.SUCCESS,  bgh="#0A6A0A",   bgd="#C0C0C0", fg=S.TW,      fgd=S.TD),
        "warning": dict(bg="#E09A00",  bgh="#C08800",   bgd="#C0C0C0", fg=S.TW,      fgd=S.TD),
        "danger":  dict(bg=S.DANGER,   bgh="#A82418",   bgd="#C0C0C0", fg=S.TW,      fgd=S.TD),
        "outline": dict(bg=S.BG_CARD,  bgh=S.ACCENT_L,  bgd=S.BG_CARD, fg=S.ACCENT,  fgd=S.TD),
        "ghost":   dict(bg="",         bgh=S.BG_SIDE_H, bgd="",        fg=S.T1,      fgd=S.TD),
        "soft":    dict(bg=S.ACCENT_L, bgh="#DCE9F8",   bgd=S.BG_CARD, fg=S.ACCENT,  fgd=S.TD),
    }

    def __init__(self, parent, text, command=None,
                 variant="primary", width=120, height=36,
                 font_size=S.MD, radius=S.R_MD, parent_bg=S.BG_APP, **kwargs):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, bg=parent_bg, **kwargs)
        self.text = text
        self.command = command
        self._bw = width
        self._bh = height
        self._r  = radius
        self._font  = (S.FF, font_size, "bold")
        self._hov   = False
        self._ena   = True
        self._c     = self._V.get(variant, self._V["primary"])
        self._draw()
        self.bind("<Enter>",    lambda e: self._hover(True))
        self.bind("<Leave>",    lambda e: self._hover(False))
        self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        bg = (self._c["bgd"] if not self._ena
              else self._c["bgh"] if self._hov
              else self._c["bg"])
        if bg:
            self.create_polygon(_poly(0, 0, self._bw, self._bh, self._r),
                                fill=bg, outline=bg, smooth=True)
        fg = self._c["fgd"] if not self._ena else self._c["fg"]
        self.create_text(self._bw / 2, self._bh / 2,
                         text=self.text, fill=fg, font=self._font)

    def _hover(self, on):
        if self._ena:
            self._hov = on
            self._draw()

    def _click(self, e):
        if self._ena and self.command:
            self._hov = False
            self._draw()
            self.command()

    def configure_state(self, enabled=True):
        self._ena = enabled
        self._draw()


class StatusBadge(tk.Canvas):
    """脉冲状态圆点"""

    _C = {
        "good":    S.SUCCESS,
        "warning": S.WARNING_FG,
        "bad":     S.DANGER,
        "pending": S.TD,
        "running": S.ACCENT,
    }
    _PULSE = {"running"}

    def __init__(self, parent, size=12, **kwargs):
        super().__init__(parent, width=size + 4, height=size + 4,
                         highlightthickness=0, bd=0, **kwargs)
        self._sz     = size
        self._status = "pending"
        self._phase  = True
        self._draw(S.TD)

    def set_status(self, status):
        self._status = status
        self._phase  = True
        self._draw(self._C.get(status, S.TD))
        if status in self._PULSE:
            self._animate()

    def _draw(self, color):
        self.delete("all")
        cx = cy = (self._sz + 4) / 2
        r = self._sz / 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=color, outline="")

    def _animate(self):
        if self._status not in self._PULSE:
            return
        self._phase = not self._phase
        self._draw(S.ACCENT if self._phase else "#80B3E0")
        self.after(500, self._animate)


class PillLabel(tk.Canvas):
    """圆角胶囊标签"""

    def __init__(self, parent, text, fg, bg, font_size=S.XS, **kwargs):
        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)
        font = (S.FF, font_size, "bold")
        tmp = tk.Label(self, text=text, font=font)
        tw = tmp.winfo_reqwidth() + 16
        th = tmp.winfo_reqheight() + 4
        tmp.destroy()
        self.config(width=tw, height=th)
        self.create_polygon(_poly(0, 0, tw, th, th // 2),
                            fill=bg, outline=bg, smooth=True)
        self.create_text(tw // 2, th // 2, text=text, fill=fg, font=font)


class EdgeProgressBar(tk.Canvas):
    """圆角进度条，支持自定义颜色"""

    def __init__(self, parent, width=300, height=6, color=None, **kwargs):
        super().__init__(parent, width=width, height=height + 4,
                         highlightthickness=0, bd=0, **kwargs)
        self._bw   = width
        self._bh   = height
        self._col  = color or S.ACCENT
        self._prog = 0
        self._draw()

    def _draw(self):
        self.delete("all")
        r = self._bh // 2
        self.create_polygon(_poly(0, 2, self._bw, self._bh + 2, r),
                            fill=S.BORDER, outline=S.BORDER, smooth=True)
        if self._prog > 0:
            w = max(self._bh, int(self._bw * self._prog / 100))
            self.create_polygon(_poly(0, 2, w, self._bh + 2, r),
                                fill=self._col, outline=self._col, smooth=True)

    def set_progress(self, v, color=None):
        self._prog = max(0, min(100, v))
        if color:
            self._col = color
        self._draw()


class SpeedGauge(tk.Canvas):
    """半圆弧速度仪表盘"""

    SIZE = 230

    def __init__(self, parent, **kwargs):
        W = self.SIZE
        H = W // 2 + 40
        super().__init__(parent, width=W, height=H,
                         highlightthickness=0, bd=0, **kwargs)
        self._speed   = 0.0
        self._max     = 100.0
        self._live    = False
        self._draw()

    # cx=115, cy=115(bottom of arc area), r=95
    def _arc_box(self):
        cx = self.SIZE // 2
        cy = self.SIZE // 2
        r  = self.SIZE // 2 - 20
        return cx - r, cy - r, cx + r, cy + r, cx, cy

    def _color(self, ratio):
        if ratio >= 0.65: return S.SUCCESS
        if ratio >= 0.25: return S.ACCENT
        return S.WARNING_FG

    def _draw(self):
        self.delete("all")
        x0, y0, x1, y1, cx, cy = self._arc_box()

        # 背景轨道（顶部半圆，从左→上→右）
        self.create_arc(x0, y0, x1, y1, start=0, extent=180,
                        style="arc", outline=S.BORDER, width=20)

        # 刻度线
        for i in range(6):
            angle_deg = 180 - i * 36   # 180° → 0°，均匀 6 段
            angle_rad = math.radians(angle_deg)
            r_outer = self.SIZE // 2 - 18
            r_inner = self.SIZE // 2 - 30
            lx1 = cx + r_outer * math.cos(angle_rad)
            ly1 = cy - r_outer * math.sin(angle_rad)
            lx2 = cx + r_inner * math.cos(angle_rad)
            ly2 = cy - r_inner * math.sin(angle_rad)
            self.create_line(lx1, ly1, lx2, ly2, fill=S.BORDER, width=2)

        # 速度弧（实心）
        if self._speed > 0:
            ratio  = min(self._speed / self._max, 1.0)
            extent = 180 * ratio
            col    = self._color(ratio)
            self.create_arc(x0, y0, x1, y1, start=180, extent=-extent,
                            style="arc", outline=col, width=20)

        # 中心速度数字
        ratio = min(self._speed / self._max, 1.0) if self._speed > 0 else 0
        fg = self._color(ratio) if self._speed > 0 else S.TD
        text = f"{self._speed:.1f}" if self._speed > 0 else "—"

        self.create_text(cx, cy - 28, text=text,
                         font=(S.FF, 36, "bold"), fill=fg)
        self.create_text(cx, cy - 4, text="Mbps",
                         font=(S.FF, S.SM), fill=S.T2)

        if self._live:
            self.create_text(cx, cy + 14, text="● 实时",
                             font=(S.FF, S.XS), fill=S.ACCENT)

    def set_speed(self, speed, max_speed=None, live=False):
        self._speed = speed
        self._live  = live
        if max_speed and max_speed > 0:
            self._max = max_speed
        self._draw()


class EdgeScrollFrame(tk.Frame):
    """带滚动条的内容容器"""

    def __init__(self, parent, bg=S.BG_LAYER, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self._cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = ttk.Scrollbar(self, orient="vertical", command=self._cv.yview)
        self.scroll_frame = tk.Frame(self._cv, bg=bg)

        self.scroll_frame.bind("<Configure>",
            lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._win = self._cv.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self._cv.configure(yscrollcommand=self._sb.set)
        self._cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._cv.bind("<Configure>",
            lambda e: self._cv.itemconfig(self._win, width=e.width))
        self._cv.bind("<MouseWheel>",
            lambda e: self._cv.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.scroll_frame.bind("<MouseWheel>",
            lambda e: self._cv.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def scroll_to_top(self):
        self._cv.yview_moveto(0)

    def bind_scroll(self, widget):
        """让子控件也能触发滚动"""
        widget.bind("<MouseWheel>",
            lambda e: self._cv.yview_scroll(int(-1 * (e.delta / 120)), "units"))
