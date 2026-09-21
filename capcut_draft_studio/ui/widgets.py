"""Widget dùng chung: Card, PathPicker, StatTile, LogView, ScrollFrame,
SegmentedTabs, SliderField, Badge, JobTable."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .theme import Theme


class Card(ttk.Frame):
    """Khối nội dung nền surface, có viền 1px và tiêu đề tùy chọn.

    Bản thân Card CHÍNH LÀ vùng nội dung: widget con có thể dùng pack hoặc
    grid tùy ý vì phần tiêu đề nằm ở frame anh em, không nằm trong Card.
    Dùng .grid_in()/.place_in() để đặt Card vào cha (thay cho .grid()/.pack()).
    """

    def __init__(self, parent, theme: Theme, title: str = "", subtitle: str = "",
                 padding: int = 18, **kw):
        self.theme = theme
        self.outer = tk.Frame(parent, bg=theme.c["border_soft"], highlightthickness=0, bd=0)
        self.container = ttk.Frame(self.outer, style="Surface.TFrame", padding=padding)
        self.container.pack(fill="both", expand=True, padx=1, pady=1)
        theme.on_change(lambda c: self.outer.configure(bg=c["border_soft"]))

        if title:
            head = ttk.Frame(self.container, style="Surface.TFrame")
            head.pack(fill="x", pady=(0, 14))
            ttk.Label(head, text=title, style="H2.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(head, text=subtitle, style="SurfaceDim.TLabel",
                          wraplength=860, justify="left").pack(anchor="w", pady=(4, 0))

        super().__init__(self.container, style="Surface.TFrame", **kw)
        super().pack(fill="both", expand=True)
        self.body = self

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
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
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
        super().__init__(parent, style="SurfaceAlt.TFrame", padding=5, **kw)
        self.theme = theme
        self.on_change = on_change
        self.options = list(options)
        self.buttons: dict[str, ttk.Button] = {}
        for i, (key, label) in enumerate(self.options):
            b = ttk.Button(self, text=label, style="Tab.TButton",
                           command=lambda k=key: self.select(k))
            b.grid(row=0, column=i, padx=(0 if i == 0 else 4, 0), sticky="ew")
            self.columnconfigure(i, weight=1)
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


class Badge(ttk.Label):
    """Nhãn viên thuốc nhỏ: ok / warn / err / info / muted."""

    KIND = {"ok": "BadgeOk", "warn": "BadgeWarn", "err": "BadgeErr",
            "info": "BadgeInfo", "muted": "BadgeMuted"}

    def __init__(self, parent, text: str = "", kind: str = "muted", **kw):
        super().__init__(parent, text=text, style=f"{self.KIND.get(kind, 'BadgeMuted')}.TLabel",
                         **kw)

    def set(self, text: str, kind: str = "muted"):
        self.configure(text=text, style=f"{self.KIND.get(kind, 'BadgeMuted')}.TLabel")


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
    """Ô số liệu: giá trị lớn + nhãn nhỏ."""

    def __init__(self, parent, theme: Theme, label: str, value: str = "—",
                 accent: bool = False, **kw):
        self.theme = theme
        self.outer = tk.Frame(parent, bg=theme.c["border_soft"])
        super().__init__(self.outer, style="Surface.TFrame", padding=(18, 15), **kw)
        super().pack(fill="both", expand=True, padx=1, pady=1)
        theme.on_change(lambda c: self.outer.configure(bg=c["border_soft"]))
        self.value_lbl = ttk.Label(self, text=value,
                                   style="StatAccent.TLabel" if accent else "Stat.TLabel")
        self.value_lbl.pack(anchor="w")
        ttk.Label(self, text=label, style="SurfaceDim.TLabel").pack(anchor="w", pady=(3, 0))

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
