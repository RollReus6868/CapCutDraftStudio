"""Bảng màu + ttk style cho CapCut Draft Studio — phong cách Youwee.

Từ 0.5.0 giao diện theo bộ khung chung "Youwee" của các tool:

* **Nền trung tính zinc + MỘT màu chủ đạo** (accent). Màu chủ đạo sinh ra từ
  một chủ đề (`THEMES`), mỗi chủ đề có bản sáng và tối, kèm dải gradient 3 điểm
  `from → via → to` dùng cho nút hành động chính, tên app và quầng sáng nền.
* **Hai khung nổi bo góc** (sidebar + nội dung) đặt trên nền cửa sổ hơi ánh màu.
* **Font Nunito** (tự nạp từ `assets/fonts/` nếu có, không thì dùng Segoe UI),
  bo góc cơ sở 10px, icon lucide.
* **Trạng thái là viên thuốc nền nhạt 10%**, không tô đặc.

Hai chế độ sáng / tối đổi được lúc đang chạy qua `Theme.apply()`; chủ đề màu đổi
qua `Theme.set_theme()`.
"""
from __future__ import annotations

import colorsys
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from . import icons

# --------------------------------------------------------------------------- #
# Chủ đề màu (HSL) — giá trị lấy từ Youwee, thêm chủ đề riêng "Studio"
# --------------------------------------------------------------------------- #

#: key → (nhãn, {mode: (primary, from, via, to)})
THEMES: dict[str, tuple[str, dict]] = {
    # chủ đề riêng của tool: xanh ngọc của dải phim / màn hình dựng
    "studio": ("Studio", {
        "light": ((188, 85, 38), (173, 80, 40), (188, 85, 42), (208, 85, 52)),
        "dark": ((188, 85, 50), (173, 85, 30), (188, 90, 34), (208, 85, 42)),
    }),
    "ocean": ("Ocean", {
        "light": ((215, 90, 55), (200, 90, 50), (215, 85, 55), (230, 80, 60)),
        "dark": ((215, 95, 60), (200, 95, 35), (215, 90, 40), (230, 85, 45)),
    }),
    "midnight": ("Midnight", {
        "light": ((262, 83, 58), (240, 60, 50), (280, 70, 55), (320, 65, 50)),
        "dark": ((270, 80, 65), (240, 70, 35), (280, 80, 40), (320, 75, 35)),
    }),
    "aurora": ("Aurora", {
        "light": ((175, 80, 40), (160, 80, 45), (190, 85, 50), (220, 80, 55)),
        "dark": ((175, 85, 50), (160, 90, 30), (190, 95, 35), (220, 90, 40)),
    }),
    "sunset": ("Sunset", {
        "light": ((25, 95, 53), (15, 90, 55), (35, 95, 55), (45, 90, 50)),
        "dark": ((30, 95, 55), (15, 85, 40), (35, 90, 42), (45, 85, 38)),
    }),
    "forest": ("Forest", {
        "light": ((152, 75, 40), (140, 70, 40), (160, 65, 45), (175, 60, 42)),
        "dark": ((152, 80, 48), (140, 75, 28), (160, 70, 32), (175, 65, 30)),
    }),
    "candy": ("Candy", {
        "light": ((340, 85, 55), (330, 85, 60), (350, 80, 65), (10, 85, 60)),
        "dark": ((340, 90, 60), (330, 90, 42), (350, 85, 48), (10, 90, 45)),
    }),
}
DEFAULT_THEME = "studio"


def hsl(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def blend(fg: str, bg: str, ratio: float) -> str:
    """Trộn `ratio` phần `fg` với nền `bg` — dùng để sinh nền nhạt cho huy hiệu."""
    a, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    mix = tuple(int(round(a[i] * ratio + b[i] * (1 - ratio))) for i in range(3))
    return "#%02x%02x%02x" % mix


def build_palette(mode: str, theme_key: str = DEFAULT_THEME) -> dict:
    """Bảng màu đầy đủ cho một chế độ + chủ đề."""
    _, spec = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
    dark = mode != "light"
    p, f, v, t = spec["dark" if dark else "light"]
    primary = hsl(*p)
    g_from, g_via, g_to = hsl(*f), hsl(*v), hsl(*t)
    if dark:
        window = blend(g_from, "#09090b", 0.07)
        bg = blend(g_via, "#111114", 0.035)
        surface = blend("#ffffff", bg, 0.035)
        c = {
            "window": window, "bg": bg, "surface": surface,
            "surface_alt": blend("#ffffff", bg, 0.075),
            "surface_hi": blend("#ffffff", bg, 0.12),
            "border": blend("#ffffff", bg, 0.11),
            "border_soft": blend("#ffffff", bg, 0.065),
            "panel_border": blend("#ffffff", window, 0.07),
            "text": "#fafafa", "text_dim": "#a1a1aa", "text_faint": "#71717a",
            "accent": primary,
            "accent_hover": blend("#ffffff", primary, 0.15),
            "accent_press": blend("#000000", primary, 0.18),
            "accent_soft": blend(primary, surface, 0.14),
            "accent_text": hsl(p[0], 100, 8),
            "success": "#34d399", "warn": "#fbbf24", "error": "#f87171", "info": "#38bdf8",
            "entry_bg": blend("#000000", bg, 0.22),
            "select_bg": blend(primary, surface, 0.26),
            "row_alt": blend("#ffffff", surface, 0.025),
            "shadow": "#000000",
        }
    else:
        window = blend(g_from, "#f4f4f5", 0.08)
        bg = blend(g_via, "#ffffff", 0.012)
        surface = blend("#f4f4f5", bg, 0.55)
        c = {
            "window": window, "bg": bg, "surface": surface,
            "surface_alt": blend("#f4f4f5", "#ececef", 0.6),
            "surface_hi": "#e4e4e7",
            "border": "#e4e4e7", "border_soft": "#ececef",
            "panel_border": blend("#000000", window, 0.06),
            "text": "#09090b", "text_dim": "#5f5f69", "text_faint": "#8e8e98",
            "accent": primary,
            "accent_hover": blend("#ffffff", primary, 0.12),
            "accent_press": blend("#000000", primary, 0.15),
            "accent_soft": blend(primary, surface, 0.11),
            "accent_text": "#ffffff",
            "success": "#059669", "warn": "#d97706", "error": "#dc2626", "info": "#0284c7",
            "entry_bg": "#ffffff",
            "select_bg": blend(primary, "#ffffff", 0.16),
            "row_alt": "#fafafa",
            "shadow": "#d4d4d8",
        }
    for key in ("success", "warn", "error"):
        c[f"{key}_soft"] = blend(c[key], c["surface"], 0.12)
    c.update(name="light" if not dark else "dark", theme=theme_key, sidebar=c["bg"],
             grad_from=g_from, grad_via=g_via, grad_to=g_to,
             accent_10=blend(primary, c["bg"], 0.10))
    return c


# giữ tên cũ cho code / test cũ
DARK = build_palette("dark")
LIGHT = build_palette("light")

# --------------------------------------------------------------------------- #
# Màu theo ngữ nghĩa — mỗi mục, mỗi chế độ cảnh, mỗi ô thống kê một màu riêng.
# Theo Youwee, màu ngữ nghĩa chỉ dùng cho ô icon và viên trạng thái; nút bấm và
# mục đang chọn luôn dùng màu chủ đạo của chủ đề.
# --------------------------------------------------------------------------- #

#: màu của từng trang (ô icon của trang)
SECTION_COLORS = {
    "dashboard": {"dark": "#38bdf8", "light": "#0284c7"},   # sky
    "settings":  {"dark": "#a78bfa", "light": "#7c3aed"},   # violet
    "render":    {"dark": "#fb923c", "light": "#ea580c"},   # orange
    "presets":   {"dark": "#34d399", "light": "#059669"},   # emerald
    "guide":     {"dark": "#22d3ee", "light": "#0891b2"},   # cyan
}

#: icon lucide của từng trang
SECTION_ICONS = {
    "dashboard": "layout-dashboard", "settings": "sliders-horizontal",
    "render": "clapperboard", "presets": "bookmark", "guide": "book-open",
}

#: màu của từng chế độ dựng cảnh
MODE_COLORS = {
    "CUT":     {"dark": "#60a5fa", "light": "#2563eb"},
    "SLOW":    {"dark": "#fbbf24", "light": "#b45309"},
    "SPEEDUP": {"dark": "#fb923c", "light": "#c2410c"},
    "IMAGE":   {"dark": "#a78bfa", "light": "#7c3aed"},
    "ERR":     {"dark": "#f87171", "light": "#dc2626"},
}

#: màu của từng ô thống kê ở trang Tổng quan
TILE_COLORS = {
    "audio":    {"dark": "#38bdf8", "light": "#0284c7"},
    "visual":   {"dark": "#a78bfa", "light": "#7c3aed"},
    "bgm":      {"dark": "#22d3ee", "light": "#0891b2"},
    "scenes":   {"dark": "#34d399", "light": "#059669"},
    "duration": {"dark": "#fb923c", "light": "#ea580c"},
}

#: màu trạng thái của một việc trong hàng đợi render
STATE_COLORS = {
    "pending":   {"dark": "#a1a1aa", "light": "#71717a"},
    "running":   {"dark": "#fb923c", "light": "#c2410c"},
    "done":      {"dark": "#34d399", "light": "#059669"},
    "error":     {"dark": "#f87171", "light": "#dc2626"},
    "cancelled": {"dark": "#fbbf24", "light": "#b45309"},
}

RADIUS = 10          # --radius của Youwee (0.625rem)


# --------------------------------------------------------------------------- #
# Ảnh bo góc cho ttk (vẽ bằng Pillow, phóng 4 lần để mịn)
# --------------------------------------------------------------------------- #
def rounded_image(w: int, h: int, r: int, fill: str | None, border: str | None = None,
                  bw: float = 1.0, inset: int = 0) -> Image.Image:
    k = 4
    img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (inset * k, inset * k, (w - inset) * k - 1, (h - inset) * k - 1)
    rr = max(0, r * k)
    if border:
        d.rounded_rectangle(box, rr, fill=_hex_to_rgb(border) + (255,))
        b = int(round(bw * k))
        inner = (box[0] + b, box[1] + b, box[2] - b, box[3] - b)
        if fill:
            d.rounded_rectangle(inner, max(0, rr - b), fill=_hex_to_rgb(fill) + (255,))
        else:
            d.rounded_rectangle(inner, max(0, rr - b), fill=(0, 0, 0, 0))
    elif fill:
        d.rounded_rectangle(box, rr, fill=_hex_to_rgb(fill) + (255,))
    return img.resize((w, h), Image.BOX)


def gradient_image(w: int, h: int, r: int, stops: tuple[str, str, str],
                   lift: float = 0.0) -> Image.Image:
    """Hình chữ nhật bo góc tô gradient 135° qua 3 điểm màu (nút CTA, logo)."""
    k = 2
    W, H = max(1, w * k), max(1, h * k)
    cols = [_hex_to_rgb(s) for s in stops]
    if lift:
        cols = [tuple(int(c + (255 - c) * lift) for c in col) for col in cols]
    grad = Image.new("RGB", (W, H))
    px = grad.load()
    span = float(W + H - 2) or 1.0
    for y in range(H):
        for x in range(W):
            t = (x + y) / span
            if t < 0.5:
                a, b, u = cols[0], cols[1], t * 2
            else:
                a, b, u = cols[1], cols[2], (t - 0.5) * 2
            px[x, y] = (int(a[0] + (b[0] - a[0]) * u), int(a[1] + (b[1] - a[1]) * u),
                        int(a[2] + (b[2] - a[2]) * u))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), r * k, fill=255)
    grad.putalpha(mask)
    return grad.resize((w, h), Image.BOX)


# --------------------------------------------------------------------------- #
# Font
# --------------------------------------------------------------------------- #
def _font_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent.parent
    dirs = [here / "assets" / "fonts"]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.insert(0, Path(base) / "assets" / "fonts")
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "assets" / "fonts")
    return dirs


def font_files() -> list[Path]:
    out = []
    for d in _font_dirs():
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.suffix.lower() in (".ttf", ".otf"))
    return out


def load_private_fonts() -> None:
    """Nạp font đi kèm (assets/fonts) cho riêng tiến trình này, không cần cài."""
    if os.name != "nt":
        return
    try:
        import ctypes
        add = ctypes.windll.gdi32.AddFontResourceExW
        for f in font_files():
            add(str(f), 0x10, 0)      # FR_PRIVATE
    except Exception:
        pass


def brand_font_file(bold: bool = True) -> str | None:
    """File font dùng để vẽ chữ gradient (tên app) bằng Pillow."""
    for f in font_files():
        name = f.stem.lower()
        if "nunito" in name and (not bold or "bold" in name or "[" in name
                                 or "variable" in name):
            return str(f)
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in ("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"):
        if (windir / name).is_file():
            return str(windir / name)
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/Library/Fonts/Arial Bold.ttf"):
        if Path(cand).is_file():
            return cand
    return None


class Theme:
    """Giữ palette hiện hành và cấu hình toàn bộ ttk style."""

    def __init__(self, root: tk.Misc, mode: str = "dark", theme_key: str = DEFAULT_THEME
                 ) -> None:
        self.root = root
        self.style = ttk.Style(root)
        self._listeners: list = []
        self.theme_key = theme_key if theme_key in THEMES else DEFAULT_THEME
        self.c = build_palette(mode, self.theme_key)
        self._gen = 0
        self._imgs: dict[int, list] = {}
        self._init_fonts()
        self.apply(mode)

    # -- fonts ------------------------------------------------------------- #
    def _init_fonts(self) -> None:
        load_private_fonts()
        family = self._pick_family(
            ["Nunito", "Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
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
        self.f_tiny = tkfont.Font(family=family, size=8, weight="bold")
        self.f_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.f_h1 = tkfont.Font(family=family, size=17, weight="bold")
        self.f_h2 = tkfont.Font(family=family, size=12, weight="bold")
        self.f_h3 = tkfont.Font(family=family, size=10, weight="bold")
        self.f_nav = tkfont.Font(family=family, size=10, weight="bold")
        self.f_btn = tkfont.Font(family=family, size=10, weight="bold")
        self.f_btn_big = tkfont.Font(family=family, size=11, weight="bold")
        self.f_stat = tkfont.Font(family=family, size=20, weight="bold")
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

    def set_theme(self, key: str) -> None:
        if key in THEMES:
            self.theme_key = key
            self.apply(self.c["name"])

    @property
    def is_dark(self) -> bool:
        return self.c["name"] == "dark"

    @property
    def grad(self) -> tuple[str, str, str]:
        return self.c["grad_from"], self.c["grad_via"], self.c["grad_to"]

    def icon(self, name: str, size: int = 16, color: str | None = None):
        return icons.photo(name, size, color or self.c["text_dim"])

    # -- áp dụng ----------------------------------------------------------- #
    def apply(self, mode: str) -> None:
        self.c = build_palette(mode, self.theme_key)
        c = self.c
        s = self.style
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        try:
            self.root.configure(bg=c["window"])
        except tk.TclError:
            pass

        self._gen += 1
        self._imgs[self._gen] = []
        for old in [g for g in self._imgs if g < self._gen - 1]:
            del self._imgs[old]

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
    # ảnh bo góc dùng làm phần tử ttk
    # ------------------------------------------------------------------ #
    def _photo(self, img: Image.Image) -> ImageTk.PhotoImage:
        ph = ImageTk.PhotoImage(img, master=self.root)
        self._imgs[self._gen].append(ph)
        return ph

    def _round(self, fill, border=None, r=8, w=32, h=32, bw=1.0):
        return self._photo(rounded_image(w, h, r, fill, border, bw))

    def _el(self, name: str) -> str:
        return f"yw{self._gen}.{name}"

    def _button_style(self, s, name: str, fill, fg, border=None, hover=None,
                      hover_fg=None, hover_border=None, press=None, dis_fill=None,
                      pad=(16, 9), font=None, on=None, r=None):
        c = self.c
        r = RADIUS - 2 if r is None else r
        on = on or c["surface"]
        normal = self._round(fill, border, r)
        hov = self._round(hover or fill, hover_border or border, r)
        prs = self._round(press or hover or fill, hover_border or border, r)
        dis = self._round(dis_fill or c["surface_alt"], None if dis_fill else border, r)
        el = self._el(name + ".bg")
        s.element_create(el, "image", normal, ("disabled", dis), ("pressed", prs),
                         ("active", hov), border=r + 2, padding=1, sticky="nsew")
        s.layout(name, [(el, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [
                ("Button.label", {"sticky": "nsew"})]})]})])
        s.configure(name, background=on, foreground=fg, padding=pad,
                    font=font or self.f_btn, anchor="center", borderwidth=0, relief="flat")
        s.map(name, foreground=[("disabled", c["text_faint"]),
                                ("active", hover_fg or fg)],
              background=[("active", on), ("pressed", on)])

    # ------------------------------------------------------------------ #
    # màu theo ngữ nghĩa
    # ------------------------------------------------------------------ #
    def _resolve_palettes(self) -> None:
        mode = self.c["name"]
        self.section = {k: v[mode] for k, v in SECTION_COLORS.items()}
        self.mode_color = {k: v[mode] for k, v in MODE_COLORS.items()}
        self.tile = {k: v[mode] for k, v in TILE_COLORS.items()}
        self.state = {k: v[mode] for k, v in STATE_COLORS.items()}
        self.icon_name = dict(SECTION_ICONS)

    def soft(self, color: str, ratio: float = 0.16, on: str = "surface") -> str:
        """Nền nhạt cùng tông với `color`, đặt trên nền `on`."""
        return blend(color, self.c[on], ratio)

    def _semantic(self, s, c) -> None:
        """Sinh style cho từng mục / chế độ / ô thống kê / trạng thái."""
        for key, col in self.section.items():
            s.configure(f"{key}.Title.TLabel", background=c["bg"], foreground=c["text"],
                        font=self.f_h1)
            s.configure(f"{key}.Bar.TFrame", background=c["accent"])
            s.configure(f"{key}.Soft.TFrame", background=self.soft(col, 0.12, "bg"))
            # nút hành động chính cũ: nay đều mang màu chủ đạo
            self._button_style(s, f"{key}.Do.TButton", c["accent"], c["accent_text"],
                               hover=c["accent_hover"], press=c["accent_press"],
                               pad=(26, 12), font=self.f_btn_big, r=RADIUS + 2)

        for key, col in self.mode_color.items():
            s.configure(f"{key}.Mode.TLabel", background=self.soft(col, 0.12),
                        foreground=col, font=self.f_tiny, padding=(9, 3))

        self._progress(s, "Render", c["accent"], 10, c["surface"])

        for key, col in self.tile.items():
            s.configure(f"{key}.Stat.TLabel", background=c["surface"], foreground=c["text"],
                        font=self.f_stat)
            s.configure(f"{key}.Tile.TFrame", background=col)

        for key, col in self.state.items():
            s.configure(f"{key}.State.TLabel", background=self.soft(col, 0.12),
                        foreground=col, font=self.f_tiny, padding=(9, 3))

    # ------------------------------------------------------------------ #
    def _frames(self, s, c) -> None:
        s.configure(".", background=c["bg"], foreground=c["text"],
                    font=self.f_base, borderwidth=0, focuscolor=c["accent"])
        s.configure("TFrame", background=c["bg"])
        s.configure("Window.TFrame", background=c["window"])
        s.configure("Surface.TFrame", background=c["surface"])
        s.configure("SurfaceAlt.TFrame", background=c["surface_alt"])
        s.configure("Sidebar.TFrame", background=c["sidebar"])
        s.configure("Divider.TFrame", background=c["border_soft"])
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
                    font=self.f_small)
        s.configure("Stat.TLabel", background=c["surface"], foreground=c["text"], font=self.f_stat)
        s.configure("StatAccent.TLabel", background=c["surface"], foreground=c["accent"],
                    font=self.f_stat)
        s.configure("Ok.TLabel", background=c["surface"], foreground=c["success"], font=self.f_bold)
        s.configure("Warn.TLabel", background=c["surface"], foreground=c["warn"], font=self.f_bold)
        s.configure("Err.TLabel", background=c["surface"], foreground=c["error"], font=self.f_bold)
        s.configure("Brand.TLabel", background=c["sidebar"], foreground=c["text"],
                    font=self.f_h2)
        s.configure("BrandDim.TLabel", background=c["sidebar"], foreground=c["text_faint"],
                    font=self.f_small)
        s.configure("Status.TLabel", background=c["bg"], foreground=c["text_dim"],
                    font=self.f_small)
        s.configure("StatusStrong.TLabel", background=c["bg"], foreground=c["text"],
                    font=self.f_bold)
        # nhãn dạng viên thuốc: nền nhạt 10% + chữ cùng tông
        for name, fg in (("BadgeOk", c["success"]), ("BadgeWarn", c["warn"]),
                         ("BadgeErr", c["error"]), ("BadgeInfo", c["accent"]),
                         ("BadgeMuted", c["text_dim"])):
            bg = c["surface_alt"] if name == "BadgeMuted" else blend(fg, c["surface"], 0.12)
            s.configure(f"{name}.TLabel", background=bg, foreground=fg,
                        font=self.f_tiny, padding=(8, 2))

    def _buttons(self, s, c) -> None:
        # --- outline (nút mặc định / Secondary) ---
        for name in ("TButton", "Secondary.TButton"):
            self._button_style(s, name, c["bg"], c["text"], border=c["border"],
                               hover=c["accent_soft"], hover_fg=c["accent"],
                               hover_border=blend(c["accent"], c["border"], 0.45),
                               press=blend(c["accent"], c["surface"], 0.22))
        # --- Primary: nền màu chủ đạo ---
        for name, pad, font in (("Accent.TButton", (20, 9), self.f_btn),
                                ("Primary.TButton", (26, 12), self.f_btn_big)):
            self._button_style(s, name, c["accent"], c["accent_text"], hover=c["accent_hover"],
                               press=c["accent_press"], pad=pad, font=font)
        # --- Ghost: nền muted nhạt, hover ánh màu chủ đạo ---
        self._button_style(s, "Ghost.TButton", c["surface_alt"], c["text_dim"],
                           hover=c["accent_soft"], hover_fg=c["accent"],
                           press=blend(c["accent"], c["surface"], 0.22),
                           pad=(13, 7), font=self.f_small)
        # --- Danger ---
        self._button_style(s, "Danger.TButton", c["surface_alt"], c["error"],
                           hover=c["error_soft"],
                           hover_border=blend(c["error"], c["surface"], 0.35),
                           press=blend(c["error"], c["surface"], 0.22))
        self._button_style(s, "DangerSolid.TButton", c["error"], "#ffffff",
                           hover=blend("#ffffff", c["error"], 0.12), pad=(18, 10))
        # --- nút đặt trên nền khung (thanh hành động dưới cùng) ---
        self._button_style(s, "Subtle.TButton", c["surface_alt"], c["text"],
                           hover=c["surface_hi"], press=c["border"], on=c["bg"],
                           pad=(18, 12), r=RADIUS + 2)
        self._button_style(s, "SubtleDanger.TButton", c["surface_alt"], c["error"],
                           hover=c["error_soft"], press=blend(c["error"], c["bg"], 0.22),
                           on=c["bg"], pad=(18, 12), r=RADIUS + 2)
        self._button_style(s, "Outline.TButton", c["bg"], c["text"], border=c["border"],
                           hover=c["accent_soft"], hover_fg=c["accent"],
                           hover_border=blend(c["accent"], c["border"], 0.45),
                           on=c["bg"], pad=(20, 12), r=RADIUS + 2)

        # --- tab phân đoạn (SegmentedControl) ---
        track = c["surface_alt"]
        self._button_style(s, "Tab.TButton", track, c["text_dim"], hover=c["surface_hi"],
                           hover_fg=c["text"], on=track, pad=(18, 8), font=self.f_bold)
        self._button_style(s, "TabActive.TButton", c["bg"], c["accent"],
                           border=c["border_soft"], on=track, pad=(18, 8), font=self.f_bold)

    def _inputs(self, s, c) -> None:
        r = RADIUS - 2
        normal = self._round(c["entry_bg"], c["border"], r)
        hover = self._round(c["entry_bg"], blend(c["accent"], c["border"], 0.35), r)
        focus = self._round(c["entry_bg"], c["accent"], r, bw=1.6)
        dis = self._round(c["surface_alt"], c["border_soft"], r)
        field = self._el("field")
        s.element_create(field, "image", normal, ("disabled", dis), ("focus", focus),
                         ("hover", hover), border=r + 2, padding=1, sticky="nsew")
        layout = [(field, {"sticky": "nsew", "children": [
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"})]})]})]
        for style_name in ("TEntry", "Surface.TEntry"):
            s.layout(style_name, layout)
            s.configure(style_name, foreground=c["text"], insertcolor=c["text"],
                        padding=(10, 7), selectbackground=c["select_bg"],
                        selectforeground=c["text"], background=c["surface"])
            s.map(style_name, foreground=[("disabled", c["text_faint"])])

        arrow = self._el("arrow")
        s.element_create(arrow, "image", self.icon("chevron-down", 16, c["text_dim"]),
                         ("active", self.icon("chevron-down", 16, c["accent"])),
                         sticky="", width=26)
        s.layout("TCombobox", [(field, {"sticky": "nsew", "children": [
            (arrow, {"side": "right", "sticky": "ns"}),
            ("Combobox.padding", {"expand": "1", "sticky": "nsew", "children": [
                ("Combobox.textarea", {"sticky": "nsew"})]})]})])
        s.configure("TCombobox", foreground=c["text"], padding=(10, 6),
                    background=c["surface"], selectbackground=c["entry_bg"],
                    selectforeground=c["text"], insertcolor=c["text"])
        s.map("TCombobox",
              foreground=[("disabled", c["text_faint"])],
              fieldbackground=[("readonly", c["entry_bg"])],
              selectbackground=[("readonly", c["entry_bg"])],
              selectforeground=[("readonly", c["text"])])
        self.root.option_add("*TCombobox*Listbox.background", c["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent_soft"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["accent"])
        self.root.option_add("*TCombobox*Listbox.font", self.f_base)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.root.option_add("*TCombobox*Listbox.highlightThickness", 0)

    def _indicator(self, kind: str, selected: bool, hover: bool, disabled: bool):
        """Ô tích / nút tròn 16px, chừa lề phải 8px để cách chữ."""
        c = self.c
        k = 4
        W, S = 26 * k, 16 * k
        img = Image.new("RGBA", (W, S + 4 * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y0 = 2 * k
        box = (k, y0, k + S - 1, y0 + S - 1)
        accent = c["text_faint"] if disabled else c["accent"]
        if kind == "check":
            if selected:
                d.rounded_rectangle(box, 4 * k, fill=_hex_to_rgb(accent) + (255,))
                tick = icons.render("check", 12, c["accent_text"], stroke=3.2)
                img.alpha_composite(tick.resize((12 * k, 12 * k), Image.BOX),
                                    (k + 2 * k, y0 + 2 * k))
            else:
                edge = blend(c["accent"], c["border"], 0.6) if hover else \
                    blend(c["text"], c["border"], 0.18)
                d.rounded_rectangle(box, 4 * k, fill=_hex_to_rgb(edge) + (255,))
                d.rounded_rectangle((box[0] + 1.5 * k, box[1] + 1.5 * k, box[2] - 1.5 * k,
                                     box[3] - 1.5 * k), 3 * k,
                                    fill=_hex_to_rgb(c["entry_bg"]) + (255,))
        else:
            edge = accent if selected else (blend(c["accent"], c["border"], 0.6) if hover
                                            else blend(c["text"], c["border"], 0.18))
            d.ellipse(box, fill=_hex_to_rgb(edge) + (255,))
            d.ellipse((box[0] + 1.5 * k, box[1] + 1.5 * k, box[2] - 1.5 * k, box[3] - 1.5 * k),
                      fill=_hex_to_rgb(c["entry_bg"]) + (255,))
            if selected:
                d.ellipse((box[0] + 4.5 * k, box[1] + 4.5 * k, box[2] - 4.5 * k,
                           box[3] - 4.5 * k), fill=_hex_to_rgb(accent) + (255,))
        return self._photo(img.resize((26, 20), Image.BOX))

    def _controls(self, s, c) -> None:
        for base, kind, part in (("TCheckbutton", "check", "Checkbutton"),
                                 ("TRadiobutton", "radio", "Radiobutton")):
            ind = self._el(f"{kind}.indicator")
            s.element_create(
                ind, "image", self._indicator(kind, False, False, False),
                ("disabled", "selected", self._indicator(kind, True, False, True)),
                ("disabled", self._indicator(kind, False, False, True)),
                ("selected", self._indicator(kind, True, False, False)),
                ("active", self._indicator(kind, False, True, False)),
                sticky="")
            s.layout(base, [(f"{part}.padding", {"sticky": "nswe", "children": [
                (ind, {"side": "left", "sticky": ""}),
                (f"{part}.label", {"side": "left", "sticky": "nswe"})]})])
            s.configure(base, background=c["surface"], foreground=c["text"],
                        padding=(2, 5), font=self.f_base)
            s.map(base,
                  background=[("active", c["surface"])],
                  foreground=[("disabled", c["text_faint"]), ("active", c["accent"])])
        for plain in ("Plain.TCheckbutton", "Plain.TRadiobutton"):
            s.configure(plain, background=c["bg"], foreground=c["text"])
            s.map(plain, background=[("active", c["bg"])])
        s.configure("Alt.TCheckbutton", background=c["surface_alt"], foreground=c["text"])
        s.map("Alt.TCheckbutton", background=[("active", c["surface_alt"])])

        # --- thanh trượt: rãnh bo tròn + núm tròn ---
        trough = self._el("scale.trough")
        s.element_create(trough, "image", self._round(c["surface_hi"], None, 3, 24, 6),
                         border=3, sticky="ew", height=6)
        knob = self._el("scale.slider")

        def knob_img(fill, ring):
            k = 4
            img = Image.new("RGBA", (18 * k, 18 * k), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((k, k, 17 * k - 1, 17 * k - 1), fill=_hex_to_rgb(ring) + (255,))
            d.ellipse((3 * k, 3 * k, 15 * k - 1, 15 * k - 1), fill=_hex_to_rgb(fill) + (255,))
            return self._photo(img.resize((18, 18), Image.BOX))

        s.element_create(knob, "image", knob_img(c["entry_bg"], c["accent"]),
                         ("pressed", knob_img(c["accent"], c["accent"])),
                         ("active", knob_img(c["accent_soft"], c["accent_hover"])), sticky="")
        s.layout("Horizontal.TScale", [(trough, {"sticky": "ew", "children": [
            (knob, {"side": "left", "sticky": ""})]})])
        s.configure("Horizontal.TScale", background=c["surface"])

        # --- thanh tiến trình: viên thuốc bo tròn ---
        for name, color, thick in (("Thin", c["accent"], 8), ("Ok", c["success"], 8),
                                   ("Err", c["error"], 8), ("Thick", c["accent"], 12),
                                   ("ThickOk", c["success"], 12)):
            self._progress(s, name, color, thick, c["bg"])
        self._progress(s, "", c["accent"], 8, c["bg"])

        s.configure("TSeparator", background=c["border_soft"])
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

    def _progress(self, s, name: str, color: str, thick: int, on: str) -> None:
        c = self.c
        r = thick // 2
        style = f"{name}.Horizontal.TProgressbar" if name else "Horizontal.TProgressbar"
        tr = self._el(f"{name or 'base'}.ptrough")
        bar = self._el(f"{name or 'base'}.pbar")
        s.element_create(tr, "image", self._round(c["surface_alt"], None, r, thick * 3, thick),
                         border=(r, 0, r, 0), height=thick, sticky="ew")
        s.element_create(bar, "image", self._round(color, None, r, thick * 3, thick),
                         border=(r, 0, r, 0), height=thick, sticky="ew")
        s.layout(style, [(tr, {"sticky": "ew", "children": [
            (bar, {"side": "left", "sticky": "ns"})]})])
        s.configure(style, background=on, thickness=thick, borderwidth=0)

    def _tables(self, s, c) -> None:
        s.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["text"], borderwidth=0, rowheight=32, font=self.f_base,
                    bordercolor=c["surface"], lightcolor=c["surface"], darkcolor=c["surface"])
        s.map("Treeview",
              background=[("selected", c["select_bg"])],
              foreground=[("selected", c["text"])])
        s.configure("Treeview.Heading", background=c["surface_alt"], foreground=c["text_dim"],
                    font=self.f_tiny, relief="flat", padding=(10, 9), borderwidth=0,
                    bordercolor=c["surface_alt"], lightcolor=c["surface_alt"],
                    darkcolor=c["surface_alt"])
        s.map("Treeview.Heading",
              background=[("active", c["surface_hi"])],
              foreground=[("active", c["text"])])

        # --- thanh cuộn mảnh, núm bo tròn, không mũi tên ---
        for orient, on, key in (("Vertical", c["surface"], "TScrollbar"),
                                ("Horizontal", c["surface"], "TScrollbar"),
                                ("Vertical", c["bg"], "Panel"),
                                ("Horizontal", c["bg"], "Panel")):
            vert = orient == "Vertical"
            thumb = self._el(f"{key}.{orient}.thumb")
            w, h = (10, 30) if vert else (30, 10)
            norm = self._photo(rounded_image(w, h, 3, c["surface_hi"], inset=2))
            act = self._photo(rounded_image(w, h, 3, c["text_faint"], inset=2))
            s.element_create(thumb, "image", norm, ("pressed", act), ("active", act),
                             border=5, sticky="nsew")
            style = f"{orient}.TScrollbar" if key == "TScrollbar" else f"Panel.{orient}.TScrollbar"
            s.layout(style, [(f"{orient}.Scrollbar.trough", {
                "sticky": "ns" if vert else "ew",
                "children": [(thumb, {"expand": "1", "sticky": "nswe"})]})])
            s.configure(style, troughcolor=on, background=on, bordercolor=on,
                        lightcolor=on, darkcolor=on, borderwidth=0, arrowsize=10, width=10)
