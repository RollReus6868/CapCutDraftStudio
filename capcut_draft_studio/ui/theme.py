"""Bảng màu + ttk style cho CapCut Draft Studio.

Hai theme: dark (mặc định) và light, đổi được lúc đang chạy qua `Theme.apply()`.

Nguyên tắc thiết kế của bản 0.4.0
--------------------------------
* **Nút phải nhìn ra ngay là nút.** Ba cấp rõ ràng: Primary (hành động chính,
  nền accent đặc, chữ to đậm) → Secondary (nền nổi + viền rõ) → Ghost (nút phụ,
  nhẹ nhất). Mọi nút đều có trạng thái hover và nhấn khác hẳn trạng thái thường.
* **Chữ đủ tương phản.** Nhãn phụ không dùng màu quá nhạt như bản cũ.
* **Khoảng cách thoáng hơn** để mắt tách được từng khối.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #

DARK = {
    "name": "dark",
    "bg": "#0f1116",           # nền cửa sổ
    "surface": "#171a22",      # nền thẻ / panel
    "surface_alt": "#212632",  # nền nổi hơn (nút phụ, header bảng)
    "surface_hi": "#2a3040",   # hover của nút phụ
    "sidebar": "#0a0c11",
    "border": "#2b3140",
    "border_soft": "#232834",
    "text": "#eef1f8",
    "text_dim": "#a3abc0",     # sáng hơn bản cũ để đọc được
    "text_faint": "#727a91",
    "accent": "#5b8cff",
    "accent_hover": "#7ba4ff",
    "accent_press": "#3f6fe0",
    "accent_soft": "#1b2440",
    "accent_text": "#ffffff",
    "success": "#34d399",
    "success_soft": "#10291f",
    "warn": "#fbbf24",
    "warn_soft": "#2a2312",
    "error": "#f87171",
    "error_soft": "#2d1719",
    "info": "#60a5fa",
    "entry_bg": "#10131a",
    "select_bg": "#2e3f68",
    "row_alt": "#1c202a",
    "shadow": "#05070b",
}

LIGHT = {
    "name": "light",
    "bg": "#f3f5fa",
    "surface": "#ffffff",
    "surface_alt": "#eceff6",
    "surface_hi": "#dfe4ef",
    "sidebar": "#12151d",      # sidebar luôn tối để tương phản
    "border": "#d6dbe7",
    "border_soft": "#e6eaf2",
    "text": "#10131b",
    "text_dim": "#4f586d",
    "text_faint": "#7b8397",
    "accent": "#2f62e8",
    "accent_hover": "#1d4fd4",
    "accent_press": "#1740b4",
    "accent_soft": "#e4ecff",
    "accent_text": "#ffffff",
    "success": "#0f8a5f",
    "success_soft": "#e2f5ed",
    "warn": "#9a6a06",
    "warn_soft": "#fdf3dc",
    "error": "#c62f2f",
    "error_soft": "#fbe6e6",
    "info": "#1f6fb2",
    "entry_bg": "#ffffff",
    "select_bg": "#cddcfd",
    "row_alt": "#f6f8fc",
    "shadow": "#c9cfdd",
}

# Sidebar luôn dùng tông tối -> màu chữ riêng
SIDEBAR_TEXT = "#c7cddd"
SIDEBAR_TEXT_ACTIVE = "#ffffff"
SIDEBAR_HOVER = "#1b2130"

# --------------------------------------------------------------------------- #
# Màu theo ngữ nghĩa — mỗi mục, mỗi chế độ cảnh, mỗi ô thống kê một màu riêng
# để nhìn vào là biết ngay đang ở đâu và cảnh nào đang dùng kiểu gì.
# --------------------------------------------------------------------------- #

#: màu của từng trang trong thanh điều hướng
SECTION_COLORS = {
    "dashboard": {"dark": "#5b8cff", "light": "#2f62e8"},   # xanh dương
    "settings":  {"dark": "#a78bfa", "light": "#7c3aed"},   # tím
    "render":    {"dark": "#fb923c", "light": "#c2410c"},   # cam
    "presets":   {"dark": "#34d399", "light": "#0f8a5f"},   # xanh lá
    "guide":     {"dark": "#22d3ee", "light": "#0e7490"},   # xanh ngọc
}

#: biểu tượng cạnh tên trang
SECTION_ICONS = {
    "dashboard": "▦", "settings": "⚙", "render": "▶",
    "presets": "★", "guide": "?",
}

#: màu của từng chế độ dựng cảnh
MODE_COLORS = {
    "CUT":     {"dark": "#5b8cff", "light": "#2f62e8"},
    "SLOW":    {"dark": "#fbbf24", "light": "#a16207"},
    "SPEEDUP": {"dark": "#fb923c", "light": "#c2410c"},
    "IMAGE":   {"dark": "#a78bfa", "light": "#7c3aed"},
    "ERR":     {"dark": "#f87171", "light": "#c62f2f"},
}

#: màu của từng ô thống kê ở trang Tổng quan
TILE_COLORS = {
    "audio":    {"dark": "#5b8cff", "light": "#2f62e8"},
    "visual":   {"dark": "#a78bfa", "light": "#7c3aed"},
    "bgm":      {"dark": "#22d3ee", "light": "#0e7490"},
    "scenes":   {"dark": "#34d399", "light": "#0f8a5f"},
    "duration": {"dark": "#fb923c", "light": "#c2410c"},
}

#: màu trạng thái của một việc trong hàng đợi render
STATE_COLORS = {
    "pending":   {"dark": "#8b93a7", "light": "#6b7280"},
    "running":   {"dark": "#fb923c", "light": "#c2410c"},
    "done":      {"dark": "#34d399", "light": "#0f8a5f"},
    "error":     {"dark": "#f87171", "light": "#c62f2f"},
    "cancelled": {"dark": "#fbbf24", "light": "#a16207"},
}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def blend(fg: str, bg: str, ratio: float) -> str:
    """Trộn `ratio` phần `fg` với nền `bg` — dùng để sinh nền nhạt cho huy hiệu."""
    a, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    mix = tuple(int(round(a[i] * ratio + b[i] * (1 - ratio))) for i in range(3))
    return "#%02x%02x%02x" % mix


class Theme:
    """Giữ palette hiện hành và cấu hình toàn bộ ttk style."""

    def __init__(self, root: tk.Misc, mode: str = "dark") -> None:
        self.root = root
        self.style = ttk.Style(root)
        self._listeners: list = []
        self.c = DARK if mode != "light" else LIGHT
        self._init_fonts()
        self.apply(mode)

    # -- fonts ------------------------------------------------------------- #
    def _init_fonts(self) -> None:
        family = self._pick_family(
            ["Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
             "Helvetica Neue", "Roboto", "DejaVu Sans", "TkDefaultFont"]
        )
        mono = self._pick_family(
            ["Cascadia Mono", "Consolas", "SF Mono", "JetBrains Mono",
             "DejaVu Sans Mono", "Courier New"]
        )
        self.family = family
        self.mono_family = mono
        self.f_base = tkfont.Font(family=family, size=10)
        self.f_small = tkfont.Font(family=family, size=9)
        self.f_tiny = tkfont.Font(family=family, size=8)
        self.f_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.f_h1 = tkfont.Font(family=family, size=18, weight="bold")
        self.f_h2 = tkfont.Font(family=family, size=12, weight="bold")
        self.f_h3 = tkfont.Font(family=family, size=10, weight="bold")
        self.f_nav = tkfont.Font(family=family, size=11)
        self.f_btn = tkfont.Font(family=family, size=10, weight="bold")
        self.f_btn_big = tkfont.Font(family=family, size=11, weight="bold")
        self.f_stat = tkfont.Font(family=family, size=21, weight="bold")
        self.f_mono = tkfont.Font(family=mono, size=9)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass

    def _pick_family(self, candidates: list[str]) -> str:
        try:
            available = {f.lower() for f in tkfont.families(self.root)}
        except tk.TclError:
            return candidates[-1]
        for name in candidates:
            if name.lower() in available:
                return name
        return candidates[-1]

    # -- theme switching --------------------------------------------------- #
    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    def toggle(self) -> str:
        new = "light" if self.c["name"] == "dark" else "dark"
        self.apply(new)
        return new

    @property
    def is_dark(self) -> bool:
        return self.c["name"] == "dark"

    # -- áp dụng ----------------------------------------------------------- #
    def apply(self, mode: str) -> None:
        self.c = LIGHT if mode == "light" else DARK
        c = self.c
        s = self.style
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        try:
            self.root.configure(bg=c["bg"])
        except tk.TclError:
            pass

        self._resolve_palettes()
        self._frames(s, c)
        self._labels(s, c)
        self._buttons(s, c)
        self._inputs(s, c)
        self._controls(s, c)
        self._tables(s, c)
        self._semantic(s, c)

        for cb in self._listeners:
            try:
                cb(c)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ #
    # màu theo ngữ nghĩa
    # ------------------------------------------------------------------ #
    def _resolve_palettes(self) -> None:
        mode = self.c["name"]
        self.section = {k: v[mode] for k, v in SECTION_COLORS.items()}
        self.mode_color = {k: v[mode] for k, v in MODE_COLORS.items()}
        self.tile = {k: v[mode] for k, v in TILE_COLORS.items()}
        self.state = {k: v[mode] for k, v in STATE_COLORS.items()}
        self.icon = dict(SECTION_ICONS)

    def soft(self, color: str, ratio: float = 0.16, on: str = "surface") -> str:
        """Nền nhạt cùng tông với `color`, đặt trên nền `on`."""
        return blend(color, self.c[on], ratio)

    def _semantic(self, s, c) -> None:
        """Sinh style cho từng mục / chế độ / ô thống kê / trạng thái."""
        for key, col in self.section.items():
            s.configure(f"{key}.Title.TLabel", background=c["bg"], foreground=col,
                        font=self.f_h1)
            s.configure(f"{key}.Bar.TFrame", background=col)
            s.configure(f"{key}.Soft.TFrame", background=self.soft(col, 0.14, "bg"))
            s.configure(f"{key}Nav.TButton", background=col, foreground="#ffffff",
                        font=self.f_btn, anchor="w", padding=(14, 11), borderwidth=0,
                        relief="flat", lightcolor=col, darkcolor=col)
            s.map(f"{key}Nav.TButton",
                  background=[("active", blend(col, "#ffffff", 0.82))],
                  lightcolor=[("active", blend(col, "#ffffff", 0.82))],
                  darkcolor=[("active", blend(col, "#ffffff", 0.82))])
            # nút hành động chính mang màu của trang đang mở
            s.configure(f"{key}.Do.TButton", background=col, foreground="#ffffff",
                        font=self.f_btn_big, padding=(26, 13), borderwidth=0,
                        relief="flat", lightcolor=col, darkcolor=col)
            s.map(f"{key}.Do.TButton",
                  background=[("pressed", blend(col, "#000000", 0.78)),
                              ("active", blend(col, "#ffffff", 0.84)),
                              ("disabled", c["surface_alt"])],
                  foreground=[("disabled", c["text_faint"])],
                  lightcolor=[("active", blend(col, "#ffffff", 0.84))],
                  darkcolor=[("active", blend(col, "#ffffff", 0.84))])

        # tab con của trang Cài đặt mang màu của chính trang đó
        settings_col = self.section["settings"]
        s.configure("TabActive.TButton", background=settings_col, foreground="#ffffff",
                    font=self.f_btn, padding=(18, 9), borderwidth=0, relief="flat",
                    lightcolor=settings_col, darkcolor=settings_col)
        s.map("TabActive.TButton",
              background=[("active", blend(settings_col, "#ffffff", 0.84))],
              lightcolor=[("active", blend(settings_col, "#ffffff", 0.84))],
              darkcolor=[("active", blend(settings_col, "#ffffff", 0.84))])

        for key, col in self.mode_color.items():
            s.configure(f"{key}.Mode.TLabel", background=self.soft(col, 0.18),
                        foreground=col, font=self.f_tiny, padding=(9, 3))

        # thanh tiến trình của trang Render mang màu cam của trang đó
        rcol = self.section["render"]
        s.configure("Render.Horizontal.TProgressbar", background=rcol,
                    troughcolor=c["surface_alt"], borderwidth=0, thickness=14,
                    lightcolor=rcol, darkcolor=rcol, bordercolor=c["surface_alt"])

        for key, col in self.tile.items():
            s.configure(f"{key}.Stat.TLabel", background=c["surface"], foreground=col,
                        font=self.f_stat)
            s.configure(f"{key}.Tile.TFrame", background=col)

        for key, col in self.state.items():
            s.configure(f"{key}.State.TLabel", background=self.soft(col, 0.18),
                        foreground=col, font=self.f_tiny, padding=(9, 3))

    # ------------------------------------------------------------------ #
    def _frames(self, s, c) -> None:
        s.configure(".", background=c["bg"], foreground=c["text"],
                    font=self.f_base, borderwidth=0, focuscolor=c["accent"])
        s.configure("TFrame", background=c["bg"])
        s.configure("Surface.TFrame", background=c["surface"])
        s.configure("SurfaceAlt.TFrame", background=c["surface_alt"])
        s.configure("Sidebar.TFrame", background=c["sidebar"])
        s.configure("Divider.TFrame", background=c["border"])
        s.configure("Accent.TFrame", background=c["accent"])
        s.configure("AccentSoft.TFrame", background=c["accent_soft"])

    def _labels(self, s, c) -> None:
        s.configure("TLabel", background=c["bg"], foreground=c["text"])
        s.configure("Surface.TLabel", background=c["surface"], foreground=c["text"])
        s.configure("SurfaceAlt.TLabel", background=c["surface_alt"], foreground=c["text"])
        s.configure("H1.TLabel", background=c["bg"], foreground=c["text"], font=self.f_h1)
        s.configure("H2.TLabel", background=c["surface"], foreground=c["text"], font=self.f_h2)
        s.configure("H3.TLabel", background=c["surface"], foreground=c["text"], font=self.f_h3)
        s.configure("Dim.TLabel", background=c["bg"], foreground=c["text_dim"], font=self.f_small)
        s.configure("SurfaceDim.TLabel", background=c["surface"],
                    foreground=c["text_dim"], font=self.f_small)
        s.configure("Field.TLabel", background=c["surface"], foreground=c["text_dim"],
                    font=self.f_small)
        s.configure("Hint.TLabel", background=c["surface"], foreground=c["text_faint"],
                    font=self.f_tiny)
        s.configure("Stat.TLabel", background=c["surface"], foreground=c["text"], font=self.f_stat)
        s.configure("StatAccent.TLabel", background=c["surface"], foreground=c["accent"],
                    font=self.f_stat)
        s.configure("Ok.TLabel", background=c["surface"], foreground=c["success"], font=self.f_bold)
        s.configure("Warn.TLabel", background=c["surface"], foreground=c["warn"], font=self.f_bold)
        s.configure("Err.TLabel", background=c["surface"], foreground=c["error"], font=self.f_bold)
        s.configure("Brand.TLabel", background=c["sidebar"], foreground=SIDEBAR_TEXT_ACTIVE,
                    font=self.f_h2)
        s.configure("BrandDim.TLabel", background=c["sidebar"], foreground="#7d86a0",
                    font=self.f_small)
        s.configure("Status.TLabel", background=c["bg"], foreground=c["text_dim"],
                    font=self.f_small)
        s.configure("StatusStrong.TLabel", background=c["bg"], foreground=c["text"],
                    font=self.f_bold)
        # nhãn dạng viên thuốc
        for name, fg, bg in (("BadgeOk", c["success"], c["success_soft"]),
                             ("BadgeWarn", c["warn"], c["warn_soft"]),
                             ("BadgeErr", c["error"], c["error_soft"]),
                             ("BadgeInfo", c["accent"], c["accent_soft"]),
                             ("BadgeMuted", c["text_faint"], c["surface_alt"])):
            s.configure(f"{name}.TLabel", background=bg, foreground=fg,
                        font=self.f_tiny, padding=(8, 3))

    def _buttons(self, s, c) -> None:
        # --- nút mặc định = Secondary: nền nổi + viền rõ ---
        s.configure("TButton", background=c["surface_alt"], foreground=c["text"],
                    borderwidth=1, relief="flat", padding=(16, 9), font=self.f_btn,
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"])
        s.map("TButton",
              background=[("pressed", c["border"]), ("active", c["surface_hi"]),
                          ("disabled", c["surface"])],
              foreground=[("disabled", c["text_faint"])],
              bordercolor=[("active", c["accent"]), ("disabled", c["border_soft"])],
              lightcolor=[("active", c["accent"])], darkcolor=[("active", c["accent"])])
        s.configure("Secondary.TButton", background=c["surface_alt"], foreground=c["text"],
                    borderwidth=1, relief="flat", padding=(16, 9), font=self.f_btn,
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"])
        s.map("Secondary.TButton",
              background=[("pressed", c["border"]), ("active", c["surface_hi"]),
                          ("disabled", c["surface"])],
              foreground=[("disabled", c["text_faint"])],
              bordercolor=[("active", c["accent"])],
              lightcolor=[("active", c["accent"])], darkcolor=[("active", c["accent"])])

        # --- Primary: hành động chính, không thể nhìn nhầm ---
        for name, pad, font in (("Accent.TButton", (22, 11), self.f_btn),
                                ("Primary.TButton", (26, 13), self.f_btn_big)):
            s.configure(name, background=c["accent"], foreground=c["accent_text"],
                        font=font, padding=pad, borderwidth=0, relief="flat",
                        lightcolor=c["accent"], darkcolor=c["accent"],
                        bordercolor=c["accent"])
            s.map(name,
                  background=[("pressed", c["accent_press"]), ("active", c["accent_hover"]),
                              ("disabled", c["surface_alt"])],
                  foreground=[("disabled", c["text_faint"])],
                  lightcolor=[("pressed", c["accent_press"]), ("active", c["accent_hover"])],
                  darkcolor=[("pressed", c["accent_press"]), ("active", c["accent_hover"])])

        # --- Ghost: nút phụ, nhẹ nhất ---
        # Ghost vẫn phải NHÌN RA LÀ NÚT: có nền riêng và viền thấy được,
        # chỉ nhạt hơn Secondary chứ không phẳng lì như chữ thường.
        s.configure("Ghost.TButton", background=c["surface_alt"], foreground=c["text_dim"],
                    padding=(13, 7), font=self.f_small, borderwidth=1,
                    bordercolor=c["border"], lightcolor=c["border"],
                    darkcolor=c["border"], relief="flat")
        s.map("Ghost.TButton",
              background=[("active", c["surface_hi"]), ("pressed", c["border"]),
                          ("disabled", c["surface"])],
              foreground=[("active", c["text"]), ("disabled", c["text_faint"])],
              bordercolor=[("active", c["accent"])],
              lightcolor=[("active", c["accent"])], darkcolor=[("active", c["accent"])])

        # --- Danger ---
        s.configure("Danger.TButton", background=c["surface_alt"], foreground=c["error"],
                    padding=(16, 9), font=self.f_btn, borderwidth=1,
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                    relief="flat")
        s.map("Danger.TButton",
              background=[("active", c["error_soft"]), ("pressed", c["error_soft"]),
                          ("disabled", c["surface"])],
              foreground=[("disabled", c["text_faint"])],
              bordercolor=[("active", c["error"])],
              lightcolor=[("active", c["error"])], darkcolor=[("active", c["error"])])
        s.configure("DangerSolid.TButton", background=c["error"], foreground="#ffffff",
                    padding=(18, 10), font=self.f_btn, borderwidth=0, relief="flat",
                    lightcolor=c["error"], darkcolor=c["error"])
        s.map("DangerSolid.TButton",
              background=[("active", c["error"]), ("disabled", c["surface_alt"])],
              foreground=[("disabled", c["text_faint"])])

        # --- điều hướng trái ---
        s.configure("Nav.TButton", background=c["sidebar"], foreground=SIDEBAR_TEXT,
                    font=self.f_nav, anchor="w", padding=(18, 11), borderwidth=0,
                    relief="flat", lightcolor=c["sidebar"], darkcolor=c["sidebar"])
        s.map("Nav.TButton",
              background=[("active", SIDEBAR_HOVER), ("pressed", SIDEBAR_HOVER)],
              foreground=[("active", SIDEBAR_TEXT_ACTIVE)],
              lightcolor=[("active", SIDEBAR_HOVER)], darkcolor=[("active", SIDEBAR_HOVER)])
        s.configure("NavActive.TButton", background=c["accent"], foreground=SIDEBAR_TEXT_ACTIVE,
                    font=self.f_btn, anchor="w", padding=(18, 11), borderwidth=0,
                    relief="flat", lightcolor=c["accent"], darkcolor=c["accent"])
        s.map("NavActive.TButton",
              background=[("active", c["accent_hover"]), ("pressed", c["accent_press"])],
              lightcolor=[("active", c["accent_hover"])],
              darkcolor=[("active", c["accent_hover"])])

        # --- tab phân đoạn bên trong trang Cài đặt ---
        s.configure("Tab.TButton", background=c["surface_alt"], foreground=c["text_dim"],
                    font=self.f_base, padding=(18, 9), borderwidth=0, relief="flat",
                    lightcolor=c["surface_alt"], darkcolor=c["surface_alt"])
        s.map("Tab.TButton",
              background=[("active", c["surface_hi"])],
              foreground=[("active", c["text"])],
              lightcolor=[("active", c["surface_hi"])], darkcolor=[("active", c["surface_hi"])])
        s.configure("TabActive.TButton", background=c["accent"], foreground=c["accent_text"],
                    font=self.f_btn, padding=(18, 9), borderwidth=0, relief="flat",
                    lightcolor=c["accent"], darkcolor=c["accent"])
        s.map("TabActive.TButton",
              background=[("active", c["accent_hover"])],
              lightcolor=[("active", c["accent_hover"])],
              darkcolor=[("active", c["accent_hover"])])

    def _inputs(self, s, c) -> None:
        for style_name in ("TEntry", "Surface.TEntry"):
            s.configure(style_name, fieldbackground=c["entry_bg"], background=c["entry_bg"],
                        foreground=c["text"], insertcolor=c["text"], borderwidth=1,
                        relief="flat", padding=(9, 7))
            s.map(style_name,
                  bordercolor=[("focus", c["accent"]), ("!focus", c["border"])],
                  lightcolor=[("focus", c["accent"]), ("!focus", c["border"])],
                  darkcolor=[("focus", c["accent"]), ("!focus", c["border"])],
                  fieldbackground=[("disabled", c["surface_alt"])],
                  foreground=[("disabled", c["text_faint"])])

        s.configure("TCombobox", fieldbackground=c["entry_bg"], background=c["surface_alt"],
                    foreground=c["text"], arrowcolor=c["text_dim"], borderwidth=1,
                    relief="flat", padding=(9, 6))
        s.map("TCombobox",
              fieldbackground=[("readonly", c["entry_bg"]), ("disabled", c["surface_alt"])],
              foreground=[("disabled", c["text_faint"])],
              arrowcolor=[("active", c["accent"])],
              bordercolor=[("focus", c["accent"]), ("hover", c["accent"]), ("!focus", c["border"])],
              lightcolor=[("focus", c["accent"]), ("!focus", c["border"])],
              darkcolor=[("focus", c["accent"]), ("!focus", c["border"])],
              selectbackground=[("readonly", c["entry_bg"])],
              selectforeground=[("readonly", c["text"])])
        self.root.option_add("*TCombobox*Listbox.background", c["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["accent_text"])
        self.root.option_add("*TCombobox*Listbox.font", self.f_base)

    def _controls(self, s, c) -> None:
        for base in ("TCheckbutton", "TRadiobutton"):
            s.configure(base, background=c["surface"], foreground=c["text"],
                        focuscolor=c["surface"], padding=(3, 6), font=self.f_base,
                        indicatorsize=13)
            s.map(base,
                  background=[("active", c["surface"])],
                  foreground=[("active", c["accent"]), ("disabled", c["text_faint"])],
                  indicatorcolor=[("selected", c["accent"]), ("!selected", c["entry_bg"])],
                  bordercolor=[("!selected", c["border"]), ("selected", c["accent"])],
                  lightcolor=[("selected", c["accent"])], darkcolor=[("selected", c["accent"])])
        s.configure("Plain.TCheckbutton", background=c["bg"], foreground=c["text"],
                    focuscolor=c["bg"])
        s.map("Plain.TCheckbutton", background=[("active", c["bg"])])
        s.configure("Alt.TCheckbutton", background=c["surface_alt"], foreground=c["text"],
                    focuscolor=c["surface_alt"])
        s.map("Alt.TCheckbutton", background=[("active", c["surface_alt"])])

        # --- thanh trượt ---
        s.configure("Horizontal.TScale", background=c["surface"], troughcolor=c["surface_alt"],
                    bordercolor=c["border"], lightcolor=c["accent"], darkcolor=c["accent"],
                    borderwidth=0, sliderthickness=15)
        s.map("Horizontal.TScale",
              background=[("active", c["surface"])],
              lightcolor=[("active", c["accent_hover"])],
              darkcolor=[("active", c["accent_hover"])])

        # --- thanh tiến trình ---
        for name, color, thick in (("Thin", c["accent"], 8), ("Ok", c["success"], 8),
                                   ("Err", c["error"], 8), ("Thick", c["accent"], 14),
                                   ("ThickOk", c["success"], 14)):
            s.configure(f"{name}.Horizontal.TProgressbar", background=color,
                        troughcolor=c["surface_alt"], borderwidth=0, thickness=thick,
                        lightcolor=color, darkcolor=color, bordercolor=c["surface_alt"])

        s.configure("TSeparator", background=c["border"])
        s.configure("TLabelframe", background=c["surface"], bordercolor=c["border"],
                    borderwidth=1, relief="solid")
        s.configure("TLabelframe.Label", background=c["surface"], foreground=c["text_dim"],
                    font=self.f_small)
        s.configure("TNotebook", background=c["bg"], borderwidth=0)
        s.configure("TNotebook.Tab", background=c["surface_alt"], foreground=c["text_dim"],
                    padding=(16, 9), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", c["surface"])],
              foreground=[("selected", c["text"])])

    def _tables(self, s, c) -> None:
        s.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["text"], borderwidth=0, rowheight=30, font=self.f_base)
        s.map("Treeview",
              background=[("selected", c["select_bg"])],
              foreground=[("selected", c["text"])])
        s.configure("Treeview.Heading", background=c["surface_alt"], foreground=c["text_dim"],
                    font=self.f_small, relief="flat", padding=(10, 9), borderwidth=0)
        s.map("Treeview.Heading",
              background=[("active", c["surface_hi"])],
              foreground=[("active", c["text"])])

        s.configure("Vertical.TScrollbar", background=c["surface_alt"], troughcolor=c["bg"],
                    borderwidth=0, arrowcolor=c["text_dim"], width=12,
                    bordercolor=c["bg"], lightcolor=c["surface_alt"],
                    darkcolor=c["surface_alt"])
        s.map("Vertical.TScrollbar", background=[("active", c["border"])])
        s.configure("Horizontal.TScrollbar", background=c["surface_alt"], troughcolor=c["bg"],
                    borderwidth=0, arrowcolor=c["text_dim"],
                    bordercolor=c["bg"], lightcolor=c["surface_alt"],
                    darkcolor=c["surface_alt"])
        s.map("Horizontal.TScrollbar", background=[("active", c["border"])])
