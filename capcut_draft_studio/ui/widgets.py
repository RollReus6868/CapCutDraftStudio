"""Widget dùng chung: Card, PathPicker, StatTile, LogView, ScrollFrame,
SegmentedTabs, SliderField, Badge — cùng các khối kiểu Youwee: RoundBox (khung
bo góc), IconTile, GradientButton, NavItem, GradientDivider."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import icons
from .theme import Theme, blend, brand_font_file, gradient_image, rounded_image


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _flatten(img: Image.Image, on: str) -> Image.Image:
    """Ghép ảnh RGBA lên nền đặc `on` — tk.Label không có nền trong suốt."""
    base = Image.new("RGBA", img.size, _rgb(on) + (255,))
    base.alpha_composite(img)
    return base


class RoundBox:
    """Khung bo góc có viền 1px, dựng bằng lưới 3×3 (4 góc là ảnh, cạnh là Frame).

    Không dùng Canvas nên widget con co giãn tự nhiên như frame thường.
    `fill`, `border`, `on` là khoá màu trong palette (on = màu nền phía sau).
    """

    def __init__(self, parent, theme: Theme, fill: str = "surface",
                 border: str | None = "border_soft", on: str = "bg", radius: int = 12,
                 padding=0, body_style: str = "Surface.TFrame"):
        self.theme = theme
        self.keys = (fill, border, on)
        self.r = radius
        self._imgs: list = []
        self.outer = tk.Frame(parent, bd=0, highlightthickness=0)
        self.outer.columnconfigure(1, weight=1)
        self.outer.rowconfigure(1, weight=1)
        self.corners = [tk.Label(self.outer, bd=0, highlightthickness=0, padx=0, pady=0)
                        for _ in range(4)]
        for lbl, (r, c) in zip(self.corners, ((0, 0), (0, 2), (2, 0), (2, 2))):
            lbl.grid(row=r, column=c, sticky="nsew")
        self.edges = {}
        self.lines = {}
        for side, (r, c, sticky) in {"top": (0, 1, "ew"), "bottom": (2, 1, "ew"),
                                     "left": (1, 0, "ns"), "right": (1, 2, "ns")}.items():
            f = tk.Frame(self.outer, bd=0, highlightthickness=0,
                         height=radius if side in ("top", "bottom") else 1,
                         width=radius if side in ("left", "right") else 1)
            f.grid(row=r, column=c, sticky=sticky)
            f.pack_propagate(False)
            line = tk.Frame(f, bd=0, highlightthickness=0,
                            height=1, width=1)
            line.pack(side=side, fill="x" if side in ("top", "bottom") else "y")
            self.edges[side] = f
            self.lines[side] = line
        self.body = ttk.Frame(self.outer, style=body_style, padding=padding)
        self.body.grid(row=1, column=1, sticky="nsew")
        self._paint(theme.c)
        theme.on_change(self._paint)

    def _paint(self, c):
        fill_key, border_key, on_key = self.keys
        fill, on = c[fill_key], c[on_key]
        border = c[border_key] if border_key else fill
        r = self.r
        size = 2 * r + 2
        full = _flatten(rounded_image(size, size, r, fill, border if border_key else None),
                        on)
        boxes = ((0, 0), (size - r, 0), (0, size - r), (size - r, size - r))
        self._imgs = []
        for lbl, (x, y) in zip(self.corners, boxes):
            ph = ImageTk.PhotoImage(full.crop((x, y, x + r, y + r)))
            self._imgs.append(ph)
            lbl.configure(image=ph, bg=on, width=r, height=r)
        self.outer.configure(bg=fill)
        for side, f in self.edges.items():
            f.configure(bg=fill)
            self.lines[side].configure(bg=border)


class IconTile(tk.Label):
    """Ô icon bo góc nền nhạt 10% (IconTile của Youwee)."""

    def __init__(self, parent, theme: Theme, icon: str, color=None, size: int = 32,
                 on: str = "surface", icon_size: int | None = None, solid: bool = False):
        super().__init__(parent, bd=0, highlightthickness=0, padx=0, pady=0)
        self.theme = theme
        self.icon_name = icon
        self.color = color             # None = màu chủ đạo; hoặc hàm trả về màu
        self.size = size
        self.on = on
        self.icon_size = icon_size or max(14, int(size * 0.5))
        self.solid = solid
        self._paint(theme.c)
        theme.on_change(self._paint)

    def set_icon(self, icon: str, color=None):
        self.icon_name = icon
        self.color = color
        self._paint(self.theme.c)

    def _color(self) -> str:
        col = self.color() if callable(self.color) else self.color
        return col or self.theme.c["accent"]

    def _paint(self, c):
        col = self._color()
        on = c[self.on]
        s = self.size
        if self.solid:
            base = gradient_image(s, s, max(6, s // 4), self.theme.grad)
            fg = "#ffffff"
        else:
            base = rounded_image(s, s, max(6, s // 4), blend(col, on, 0.13))
            fg = col
        img = _flatten(base, on)
        ic = icons.render(self.icon_name, self.icon_size, fg)
        off = (s - self.icon_size) // 2
        img.alpha_composite(ic, (off, off))
        self._img = ImageTk.PhotoImage(img)
        self.configure(image=self._img, bg=on)


def gradient_text(theme: Theme, text: str, px: int, on: str) -> ImageTk.PhotoImage | None:
    """Chữ tô gradient (tên app) — vẽ bằng Pillow vì Tk không tô gradient cho chữ."""
    path = brand_font_file()
    if not path:
        return None
    try:
        font = ImageFont.truetype(path, px)
        try:
            font.set_variation_by_name("ExtraBold")
        except Exception:
            pass
    except OSError:
        return None
    l, t, r, b = font.getbbox(text)
    w, h = r - l + 4, b - t + 6
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((2 - l, 3 - t), text, font=font, fill=255)
    grad = gradient_image(w, h, 0, theme.grad).convert("RGB")
    out = Image.new("RGBA", (w, h), _rgb(on) + (255,))
    out.paste(grad, (0, 0), mask)
    return ImageTk.PhotoImage(out)


class GradientButton(tk.Canvas):
    """Nút hành động chính tô gradient 3 điểm (btn-gradient). Mỗi màn hình MỘT nút.

    Dùng được như ttk.Button ở những chỗ app cần: .configure(state=, text=),
    .cget("state").
    """

    def __init__(self, parent, theme: Theme, text: str, icon: str = "", command=None,
                 on: str = "bg", height: int = 46, padx: int = 26, radius: int = 12):
        super().__init__(parent, height=height, bd=0, highlightthickness=0,
                         cursor="hand2", takefocus=1)
        self.theme = theme
        self.text = text
        self.icon_name = icon
        self.command = command
        self.on = on
        self.h = height
        self.padx = padx
        self.r = radius
        self.state = "normal"
        self.hover = False
        self.pressed = False
        self._cache: dict = {}
        self.configure(width=self._natural_width())
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        theme.on_change(lambda c: (self._cache.clear(), self._draw()))

    def _natural_width(self) -> int:
        w = self.theme.f_btn_big.measure(self.text) + 2 * self.padx
        return w + (26 if self.icon_name else 0)

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._draw()

    def _release(self, e):
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        was = self.pressed
        self._set(pressed=False)
        if was and inside:
            self.invoke()

    def invoke(self):
        if self.state != "disabled" and self.command:
            self.command()

    def _bg(self, w, h, mode):
        key = (w, h, mode)
        img = self._cache.get(key)
        if img is None:
            c = self.theme.c
            if mode == "disabled":
                base = rounded_image(w, h, self.r, c["surface_alt"])
            else:
                lift = {"hover": 0.10, "pressed": -0.0}.get(mode, 0.0)
                base = gradient_image(w, h, self.r, self.theme.grad, lift=lift)
            img = ImageTk.PhotoImage(_flatten(base, c[self.on]))
            self._cache[key] = img
        return img

    def _draw(self):
        c = self.theme.c
        w = max(self.winfo_width(), 2)
        h = self.h
        self.delete("all")
        self.configure(bg=c[self.on])
        disabled = self.state == "disabled"
        mode = "disabled" if disabled else ("pressed" if self.pressed else
                                            ("hover" if self.hover else "normal"))
        self.create_image(0, 0, image=self._bg(w, h, mode), anchor="nw")
        fg = c["text_faint"] if disabled else "#ffffff"
        font = self.theme.f_btn_big
        tw = font.measure(self.text)
        total = tw + (26 if self.icon_name else 0)
        x = (w - total) // 2
        y = h // 2 + (1 if self.pressed else 0)
        if self.icon_name:
            self._icon = icons.photo(self.icon_name, 18, fg)
            self.create_image(x, y, image=self._icon, anchor="w")
            x += 26
        self.create_text(x, y, text=self.text, fill=fg, font=font, anchor="w")
        self.configure(cursor="arrow" if disabled else "hand2")

    def configure(self, cnf=None, **kw):
        changed = False
        for key in ("state", "text", "command"):
            if key in kw:
                setattr(self, key, kw.pop(key))
                changed = True
        if "text" in (cnf or {}):
            self.text = cnf.pop("text")
        res = super().configure(cnf, **kw) if (cnf or kw) else None
        if changed:
            self._draw()
        return res

    config = configure

    def cget(self, key):
        if key in ("state", "text"):
            return getattr(self, key)
        return super().cget(key)


class Tooltip:
    """Chú thích nhỏ hiện bên phải widget (dùng khi sidebar thu gọn)."""

    def __init__(self, widget, theme: Theme, text_fn):
        self.widget, self.theme, self.text_fn = widget, theme, text_fn
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        text = self.text_fn()
        if not text or self.tip:
            return
        c = self.theme.c
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() // 2 - 14
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=text, bg=c["surface_hi"], fg=c["text"],
                 font=self.theme.f_small, padx=10, pady=5).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class NavItem(tk.Canvas):
    """Mục điều hướng: icon 20px + nhãn; mục đang chọn nền primary/10, chữ primary,
    vạch sáng bên trái. Khi sidebar thu gọn chỉ còn icon + tooltip."""

    H = 42

    def __init__(self, parent, theme: Theme, icon: str, label: str, command=None,
                 icon_color=None):
        super().__init__(parent, height=self.H, bd=0, highlightthickness=0, cursor="hand2")
        self.theme = theme
        self.icon_name = icon
        self.label = label
        self.command = command
        self.icon_color = icon_color          # hàm trả về màu riêng (mặt trời / mặt trăng)
        self.active = False
        self.hover = False
        self.collapsed = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False))
        self.bind("<ButtonRelease-1>", self._click)
        Tooltip(self, theme, lambda: self.label if self.collapsed else "")
        theme.on_change(lambda c: self._draw())

    def _click(self, e):
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height() and self.command:
            self.command()

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._draw()

    def set(self, icon: str | None = None, label: str | None = None):
        if icon:
            self.icon_name = icon
        if label is not None:
            self.label = label
        self._draw()

    def _draw(self):
        c = self.theme.c
        w = max(self.winfo_width(), 2)
        h = self.H
        self.delete("all")
        self.configure(bg=c["bg"])
        fill = None
        if self.active:
            fill = c["accent_10"]
        elif self.hover:
            fill = c["surface_alt"]
        if fill:
            self._bgimg = ImageTk.PhotoImage(_flatten(rounded_image(w, h, 12, fill), c["bg"]))
            self.create_image(0, 0, image=self._bgimg, anchor="nw")
        if self.active and not self.collapsed:
            # vạch sáng bên trái
            bar = rounded_image(4, 20, 2, c["accent"])
            self._barimg = ImageTk.PhotoImage(_flatten(bar, fill))
            self.create_image(0, h // 2, image=self._barimg, anchor="w")
        if self.icon_color and not self.active:
            col = self.icon_color()
        else:
            col = c["accent"] if self.active else (c["text"] if self.hover else c["text_dim"])
        self._icon = icons.photo(self.icon_name, 20, col)
        if self.collapsed:
            self.create_image(w // 2, h // 2, image=self._icon)
        else:
            self.create_image(14, h // 2, image=self._icon, anchor="w")
            fg = c["accent"] if self.active else (c["text"] if self.hover else c["text_dim"])
            self.create_text(46, h // 2, text=self.label, anchor="w", fill=fg,
                             font=self.theme.f_nav)


class GradientDivider(tk.Canvas):
    """Đường kẻ 1px mờ dần hai đầu — thay cho <hr> cứng."""

    def __init__(self, parent, theme: Theme, on: str = "bg"):
        super().__init__(parent, height=1, bd=0, highlightthickness=0)
        self.theme, self.on = theme, on
        self.bind("<Configure>", lambda e: self._draw())
        theme.on_change(lambda c: self._draw())

    def _draw(self):
        c = self.theme.c
        w = max(self.winfo_width(), 2)
        line = Image.new("RGBA", (w, 1))
        col = _rgb(c["border"])
        for x in range(w):
            t = x / max(1, w - 1)
            a = int(255 * min(1.0, 2.2 * min(t, 1 - t)))
            line.putpixel((x, 0), col + (a,))
        self._img = ImageTk.PhotoImage(_flatten(line, c[self.on]))
        self.delete("all")
        self.configure(bg=c[self.on])
        self.create_image(0, 0, image=self._img, anchor="nw")


class Card(ttk.Frame):
    """Khối nội dung bo góc nền surface, viền 1px, tiêu đề + ô icon tuỳ chọn.

    Bản thân Card CHÍNH LÀ vùng nội dung: widget con có thể dùng pack hoặc
    grid tùy ý vì phần tiêu đề nằm ở frame anh em, không nằm trong Card.
    Dùng .grid_in()/.place_in() để đặt Card vào cha (thay cho .grid()/.pack()).
    """

    RADIUS = 12

    def __init__(self, parent, theme: Theme, title: str = "", subtitle: str = "",
                 padding: int = 18, accent: str = "", icon: str = "", **kw):
        self.theme = theme
        self.accent = accent
        pad = max(0, padding - self.RADIUS) if padding > 2 else 0
        self.box = RoundBox(parent, theme, fill="surface", border="border_soft", on="bg",
                            radius=self.RADIUS, padding=pad)
        self.outer = self.box.outer
        self.container = self.box.body

        if title:
            head = ttk.Frame(self.container, style="Surface.TFrame")
            head.pack(fill="x", pady=(0, 12))
            name = icons.from_glyph(icon) if icon else ""
            if name:
                self.icon_tile = IconTile(head, theme, name,
                                          color=self._accent_color, size=34)
                self.icon_tile.pack(side="left", anchor="n", padx=(0, 12))
            text = ttk.Frame(head, style="Surface.TFrame")
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=title, style="H2.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(text, text=subtitle, style="SurfaceDim.TLabel",
                          wraplength=820, justify="left").pack(anchor="w", pady=(2, 0))

        super().__init__(self.container, style="Surface.TFrame", **kw)
        super().pack(fill="both", expand=True)
        self.body = self

    def _accent_color(self) -> str:
        th = self.theme
        return (th.section.get(self.accent) or th.tile.get(self.accent)
                or th.mode_color.get(self.accent) or th.c["accent"])

    def place_in(self, **kw):
        self.outer.pack(**kw)
        return self

    def grid_in(self, **kw):
        self.outer.grid(**kw)
        return self


class ScrollFrame(ttk.Frame):
    """Frame cuộn dọc bằng canvas, dùng cho trang dài."""

    def __init__(self, parent, theme: Theme, **kw):
        super().__init__(parent, **kw)
        self.theme = theme
        self.canvas = tk.Canvas(self, bg=theme.c["bg"], highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                  style="Panel.Vertical.TScrollbar")
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))
        theme.on_change(lambda c: self.canvas.configure(bg=c["bg"]))

    def _on_inner(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _bind_wheel(self, on: bool):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._wheel)
            self.canvas.bind_all("<Button-4>", self._wheel)
            self.canvas.bind_all("<Button-5>", self._wheel)
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(seq)

    def _wheel(self, e):
        if getattr(e, "num", None) == 4:
            delta = -1
        elif getattr(e, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if e.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")


class SegmentedTabs(ttk.Frame):
    """Dải tab ngang kiểu phân đoạn — dùng để gộp nhiều trang con vào một trang.

    `options` là [(khoá, nhãn), ...]. Gọi `.select(khoá)` để đổi tab; callback
    `on_change(khoá)` chạy sau mỗi lần đổi.
    """

    def __init__(self, parent, theme: Theme, options, on_change=None, **kw):
        super().__init__(parent, style="TFrame", **kw)
        self.theme = theme
        self.on_change = on_change
        self.options = list(options)
        self.buttons: dict[str, ttk.Button] = {}
        # rãnh bo góc nền muted, tab đang chọn nổi lên (SegmentedControl)
        track = RoundBox(self, theme, fill="surface_alt", border=None, on="bg", radius=6,
                         body_style="SurfaceAlt.TFrame")
        track.outer.pack(fill="x", expand=True)
        host = track.body
        for i, (key, label) in enumerate(self.options):
            b = ttk.Button(host, text=label, style="Tab.TButton",
                           command=lambda k=key: self.select(k))
            b.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0), sticky="ew")
            host.columnconfigure(i, weight=1)
            self.buttons[key] = b
        self.current = self.options[0][0] if self.options else ""
        self._paint()

    def _paint(self):
        for key, btn in self.buttons.items():
            btn.configure(style="TabActive.TButton" if key == self.current else "Tab.TButton")

    def select(self, key: str):
        if key not in self.buttons:
            return
        self.current = key
        self._paint()
        if self.on_change:
            self.on_change(key)


class GapDialog(tk.Toplevel):
    """Đặt riêng khoảng nghỉ cho một cảnh. `self.result`:

    None  = bấm Huỷ · ""  = trả về tự động · "join"/"short"/"full"/"long"
    hoặc một chuỗi số giây.
    """

    CHOICES = [
        ("", "Tự động — để tool tự đoán theo lời thoại"),
        ("join", "Nối liền — không nghỉ, nối thẳng vào cảnh sau"),
        ("short", "Nghỉ ngắn — một nửa khoảng nghỉ đủ"),
        ("full", "Nghỉ đủ — đúng bằng cài đặt"),
        ("long", "Nghỉ dài — nhấn mạnh chuyển ý"),
        ("custom", "Tự nhập số giây:"),
    ]

    def __init__(self, parent, theme: Theme, scene: int, current: str = "",
                 reason: str = ""):
        super().__init__(parent)
        self.result: str | None = None
        self.theme = theme
        self.title(f"Khoảng nghỉ sau cảnh {scene:04d}")
        self.configure(bg=theme.c["bg"])
        self.resizable(False, False)
        self.transient(parent)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Khoảng nghỉ sau cảnh {scene:04d}",
                  style="H2.TLabel").pack(anchor="w")
        if reason:
            ttk.Label(body, text=f"Tool đang chọn: {reason}", style="Dim.TLabel",
                      wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))

        preset, custom = "", ""
        if current:
            if current in ("join", "short", "full", "long"):
                preset = current
            else:
                preset, custom = "custom", current
        self.choice = tk.StringVar(value=preset)
        self.custom = tk.StringVar(value=custom or "0.30")

        for value, label in self.CHOICES:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(10 if value == "" else 3, 0))
            ttk.Radiobutton(row, text=label, variable=self.choice, value=value,
                            style="Plain.TRadiobutton").pack(side="left")
            if value == "custom":
                ttk.Entry(row, textvariable=self.custom, width=7,
                          justify="center").pack(side="left", padx=(8, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(20, 0))
        ttk.Button(buttons, text="Huỷ", style="Ghost.TButton",
                   command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Lưu", style="Accent.TButton",
                   command=self._ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._ok())
        self.update_idletasks()
        self._centre(parent)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _centre(self, parent):
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def _ok(self):
        value = self.choice.get()
        if value == "custom":
            raw = self.custom.get().strip().replace(",", ".")
            try:
                value = f"{max(0.0, float(raw)):.2f}"
            except ValueError:
                value = ""
        self.result = value
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class Badge(ttk.Label):
    """Nhãn viên thuốc nhỏ: ok / warn / err / info / muted, hoặc style tự đặt."""

    KIND = {"ok": "BadgeOk", "warn": "BadgeWarn", "err": "BadgeErr",
            "info": "BadgeInfo", "muted": "BadgeMuted"}

    def __init__(self, parent, text: str = "", kind: str = "muted",
                 style_name: str = "", **kw):
        super().__init__(parent, text=text,
                         style=style_name or f"{self.KIND.get(kind, 'BadgeMuted')}.TLabel",
                         **kw)

    def set(self, text: str, kind: str = "muted", style_name: str = ""):
        self.configure(text=text,
                       style=style_name or f"{self.KIND.get(kind, 'BadgeMuted')}.TLabel")


class PathPicker(ttk.Frame):
    """Hàng: nhãn + ô nhập đường dẫn + nút Chọn + huy hiệu tồn tại."""

    def __init__(self, parent, theme: Theme, label: str, var: tk.StringVar,
                 kind: str = "dir", hint: str = "", on_change=None,
                 filetypes=None, **kw):
        super().__init__(parent, style="Surface.TFrame", **kw)
        self.theme = theme
        self.var = var
        self.kind = kind
        self.filetypes = filetypes
        self.on_change = on_change
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self, style="Surface.TFrame")
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text=label, style="Field.TLabel").pack(side="left")
        self.badge = Badge(top, "chưa chọn", "muted")
        self.badge.pack(side="right")

        self.entry = ttk.Entry(self, textvariable=var)
        self.entry.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(self, text="Chọn…", style="Secondary.TButton",
                   command=self.browse).grid(row=1, column=1, sticky="w", padx=(8, 0),
                                             pady=(5, 0))
        if hint:
            ttk.Label(self, text=hint, style="Hint.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        var.trace_add("write", lambda *_: self.refresh_badge())
        self.refresh_badge()

    def browse(self):
        if self.kind == "dir":
            p = filedialog.askdirectory(title="Chọn thư mục")
        else:
            p = filedialog.askopenfilename(title="Chọn file",
                                           filetypes=self.filetypes or [("Tất cả", "*.*")])
        if p:
            self.var.set(p)
            if self.on_change:
                self.on_change(p)

    def refresh_badge(self):
        raw = (self.var.get() or "").strip()
        if not raw:
            self.badge.set("chưa chọn", "muted")
            return
        p = Path(raw)
        ok = p.is_dir() if self.kind == "dir" else p.is_file()
        self.badge.set("hợp lệ" if ok else "không tồn tại", "ok" if ok else "err")


class StatTile(ttk.Frame):
    """Ô số liệu: ô icon màu + giá trị lớn + nhãn nhỏ, trong khung bo góc."""

    def __init__(self, parent, theme: Theme, label: str, value: str = "—",
                 color_key: str = "", icon: str = "", **kw):
        self.theme = theme
        self.color_key = color_key
        self.box = RoundBox(parent, theme, fill="surface", border="border_soft", on="bg",
                            radius=12, padding=(4, 2))
        self.outer = self.box.outer
        super().__init__(self.box.body, style="Surface.TFrame", **kw)
        super().pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)

        name = icons.from_glyph(icon) if icon else ""
        if name:
            IconTile(self, theme, name, color=self._color, size=40).grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
        self.value_lbl = ttk.Label(self, text=value, style=self._value_style())
        self.value_lbl.grid(row=0, column=1, sticky="sw")
        ttk.Label(self, text=label, style="SurfaceDim.TLabel").grid(
            row=1, column=1, sticky="nw")

    def _color(self) -> str:
        return self.theme.tile.get(self.color_key) or self.theme.c["accent"]

    def _value_style(self) -> str:
        return f"{self.color_key}.Stat.TLabel" if self.color_key else "Stat.TLabel"

    def set(self, value: str):
        self.value_lbl.configure(text=str(value))

    def grid_in(self, **kw):
        self.outer.grid(**kw)
        return self


class SliderField(ttk.Frame):
    """Thanh trượt + ô số, hai chiều — dễ chỉnh hơn ô nhập trơ trọi.

    Giá trị vẫn lưu trong `var` (StringVar) nên cấu hình và preset cũ không đổi.
    """

    def __init__(self, parent, theme: Theme, label: str, var: tk.StringVar,
                 from_: float = 0.0, to: float = 1.0, step: float = 0.01,
                 decimals: int = 2, unit: str = "", hint: str = "", **kw):
        super().__init__(parent, style="Surface.TFrame", **kw)
        self.theme = theme
        self.var = var
        self.decimals = decimals
        self.step = step
        self._busy = False
        self.columnconfigure(0, weight=1)

        head = ttk.Frame(self, style="Surface.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text=label, style="Field.TLabel").pack(side="left")
        if unit:
            ttk.Label(head, text=unit, style="Hint.TLabel").pack(side="right")

        self.value = tk.DoubleVar(value=self._read())
        self.scale = ttk.Scale(self, orient="horizontal", from_=from_, to=to,
                               variable=self.value, command=self._from_scale)
        self.scale.grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 10))
        self.entry = ttk.Entry(self, textvariable=var, width=7, justify="center")
        self.entry.grid(row=1, column=1, sticky="e", pady=(6, 0))
        if hint:
            ttk.Label(self, text=hint, style="Hint.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        var.trace_add("write", lambda *_: self._from_var())

    def _read(self) -> float:
        try:
            return float(str(self.var.get()).strip().replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def _fmt(self, v: float) -> str:
        return f"{v:.{self.decimals}f}" if self.decimals else str(int(round(v)))

    def _from_scale(self, _raw=None):
        if self._busy:
            return
        self._busy = True
        try:
            v = self.value.get()
            if self.step:
                v = round(v / self.step) * self.step
            self.var.set(self._fmt(v))
        finally:
            self._busy = False

    def _from_var(self):
        if self._busy:
            return
        self._busy = True
        try:
            self.value.set(self._read())
        except tk.TclError:
            pass
        finally:
            self._busy = False


class LogView(ttk.Frame):
    """Console log có tô màu theo mức, tự cuộn, copy, xóa."""

    LEVELS = {
        "ERROR": "error", "FAIL": "error",
        "WARN": "warn",
        "SUCCESS": "success", "OK": "success", "DONE": "success",
        "BUILD": "info", "SCAN": "info", "VALIDATE": "info",
        "SUB": "info", "PLAN": "info", "HARVEST": "info",
        "RENDER": "info", "EXPORT": "info", "UPDATE": "info", "QUEUE": "info",
    }

    def __init__(self, parent, theme: Theme, height: int = 14, title: str = "Nhật ký", **kw):
        super().__init__(parent, style="Surface.TFrame", **kw)
        self.theme = theme
        self.autoscroll = tk.BooleanVar(value=True)
        self._lines: list[tuple[str, str]] = []

        bar = ttk.Frame(self, style="Surface.TFrame")
        bar.pack(fill="x", pady=(0, 10))
        ttk.Label(bar, text=title, style="H2.TLabel").pack(side="left")
        # Ô "Tự cuộn" đứng cạnh tiêu đề: để bên phải cùng 3 nút thì hay bị
        # bóp mất chữ khi cửa sổ hẹp.
        ttk.Checkbutton(bar, text="Tự cuộn", variable=self.autoscroll,
                        style="TCheckbutton").pack(side="left", padx=(16, 0))
        ttk.Button(bar, text="Xóa", style="Ghost.TButton",
                   command=self.clear).pack(side="right")
        ttk.Button(bar, text="Sao chép", style="Ghost.TButton",
                   command=self.copy_all).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="Lưu", style="Ghost.TButton",
                   command=self.save_as).pack(side="right", padx=(0, 6))

        wrap = ttk.Frame(self, style="Surface.TFrame")
        wrap.pack(fill="both", expand=True)
        c = theme.c
        self.text = tk.Text(wrap, height=height, wrap="word", bd=0, highlightthickness=0,
                            bg=c["entry_bg"], fg=c["text_dim"], insertbackground=c["text"],
                            font=theme.f_mono, padx=14, pady=12, state="disabled",
                            selectbackground=c["select_bg"])
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._configure_tags()
        theme.on_change(self._on_theme)

    def _configure_tags(self):
        c = self.theme.c
        self.text.tag_configure("plain", foreground=c["text_dim"])
        self.text.tag_configure("info", foreground=c["info"])
        self.text.tag_configure("success", foreground=c["success"])
        self.text.tag_configure("warn", foreground=c["warn"])
        self.text.tag_configure("error", foreground=c["error"])

    def _on_theme(self, c):
        self.text.configure(bg=c["entry_bg"], fg=c["text_dim"], insertbackground=c["text"],
                            selectbackground=c["select_bg"])
        self._configure_tags()

    @classmethod
    def classify(cls, line: str) -> str:
        s = line.lstrip()
        if s.startswith("["):
            key = s[1:s.find("]")].strip().upper() if "]" in s else ""
            return cls.LEVELS.get(key, "plain")
        return "plain"

    def append(self, line: str):
        tag = self.classify(line)
        self._lines.append((tag, line))
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag)
        if self.autoscroll.get():
            self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self._lines.clear()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def dump(self) -> str:
        return "\n".join(t for _, t in self._lines)

    def copy_all(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.dump())
        except tk.TclError:
            pass

    def save_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".log",
                                         filetypes=[("Log", "*.log"), ("Text", "*.txt")],
                                         initialfile="capcut-draft-studio.log")
        if p:
            Path(p).write_text(self.dump(), encoding="utf-8")
            self.append(f"[OK] Đã lưu log: {p}")


class MappedCombobox(ttk.Combobox):
    """Combobox hiện nhãn tiếng Việt nhưng ghi giá trị gốc vào StringVar.

    `options` là [(giá trị lưu, nhãn hiển thị), ...]. File cấu hình và preset
    vẫn lưu giá trị gốc nên đổi nhãn về sau không làm hỏng cấu hình cũ.
    """

    def __init__(self, parent, var: tk.StringVar, options, fallback: str = "", **kw):
        self.var = var
        self.options = list(options)
        self._label_of = {k: v for k, v in self.options}
        self._key_of = {v: k for k, v in self.options}
        self.fallback = fallback or (self.options[0][0] if self.options else "")
        self._display = tk.StringVar()
        super().__init__(parent, textvariable=self._display, state="readonly",
                         values=[label for _, label in self.options], **kw)
        self.bind("<<ComboboxSelected>>", self._on_select)
        var.trace_add("write", lambda *_: self._sync_from_var())
        self._sync_from_var()

    def _on_select(self, _event=None):
        key = self._key_of.get(self._display.get())
        if key is not None and self.var.get() != key:
            self.var.set(key)

    def _sync_from_var(self):
        key = (self.var.get() or "").strip()
        if key not in self._label_of:
            key = self.fallback
            if self.var.get() != key:
                self.var.set(key)
                return
        label = self._label_of.get(key, "")
        if self._display.get() != label:
            self._display.set(label)


def field_row(parent, theme: Theme, label: str, var: tk.StringVar, width: int = 14,
              hint: str = "") -> ttk.Frame:
    """Ô nhập nhỏ có nhãn phía trên, dùng cho các tham số số."""
    f = ttk.Frame(parent, style="Surface.TFrame")
    ttk.Label(f, text=label, style="Field.TLabel").pack(anchor="w")
    ttk.Entry(f, textvariable=var, width=width).pack(anchor="w", fill="x", pady=(5, 0))
    if hint:
        ttk.Label(f, text=hint, style="Hint.TLabel").pack(anchor="w", pady=(3, 0))
    return f


def labeled_combo(parent, theme: Theme, label: str, var: tk.StringVar, options,
                  fallback: str = "", hint: str = "", width: int = 24) -> ttk.Frame:
    """Nhãn + MappedCombobox, xếp dọc — dùng nhiều ở trang Cài đặt và Render."""
    f = ttk.Frame(parent, style="Surface.TFrame")
    ttk.Label(f, text=label, style="Field.TLabel").pack(anchor="w")
    MappedCombobox(f, var, options, fallback=fallback, width=width,
                   height=min(14, len(list(options)))).pack(anchor="w", fill="x", pady=(5, 0))
    if hint:
        ttk.Label(f, text=hint, style="Hint.TLabel").pack(anchor="w", pady=(3, 0))
    return f
