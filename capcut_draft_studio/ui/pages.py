"""Nội dung từng trang của CapCut Draft Studio.

Từ 0.4.0, năm mục cũ (Cảnh quay, Nhạc nền, Hiệu ứng SFX, Phụ đề, Nâng cao)
được gộp vào MỘT trang "Cài đặt" với dải tab ngang, và có thêm trang
"Render video" để xuất file mp4 ngay trong tool.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import animations, render
from ..media import harvest_sfx_from_capcut, list_bgm_files, list_sfx_items
from ..styles import harvest_sub_styles, list_sub_styles
from ..subtitles import excel_columns
from .widgets import (Badge, Card, LogView, MappedCombobox, PathPicker, ScrollFrame,
                      SegmentedTabs, SliderField, StatTile, field_row, labeled_combo)

MODE_LABEL = {"CUT": "● Cắt", "SLOW": "● Chậm", "SPEEDUP": "● Nhanh", "IMAGE": "● Ảnh"}

SETTING_TABS = [
    ("scenes", "Cảnh quay"),
    ("music", "Nhạc nền"),
    ("sfx", "Hiệu ứng SFX"),
    ("subtitle", "Phụ đề"),
    ("advanced", "Nâng cao"),
]

SUB_SOURCE_CHOICES = (
    ("auto", "Tự động (ưu tiên manifest → Excel → Texts)"),
    ("manifest", "Chỉ _manifest.json"),
    ("excel", "Chỉ file Excel"),
    ("texts", "Chỉ thư mục Texts/"),
    ("off", "Tắt phụ đề"),
)

ENGINE_CHOICES = (
    ("ffmpeg", "ffmpeg — tool tự render (khuyến nghị)"),
    ("capcut", "CapCut — nhờ CapCut tự export (chỉ Windows)"),
)

HW_CHOICES = (
    ("auto", "Tự động — dùng card đồ hoạ nếu có"),
    ("cpu", "Chỉ CPU — chậm hơn nhưng chắc chắn chạy"),
)


def _open_folder(path: Path):
    """Mở thư mục bằng trình quản lý file của hệ điều hành."""
    p = Path(path)
    if not p.exists():
        messagebox.showwarning("Không tìm thấy", f"Không tồn tại:\n{p}")
        return
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except OSError as e:
        messagebox.showerror("Lỗi", str(e))


def _fmt_dur(sec: float) -> str:
    sec = max(0.0, float(sec))
    m, s = divmod(int(round(sec)), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# =========================================================================== #
# 1. TỔNG QUAN
# =========================================================================== #
def build_dashboard(app):
    page = app.pages["dashboard"]
    page.columnconfigure(0, weight=1)
    page.rowconfigure(2, weight=1)
    th = app.theme

    stats = ttk.Frame(page)
    stats.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    for i in range(5):
        stats.columnconfigure(i, weight=1, uniform="stat")
    app.tiles = {}
    specs = [("audio", "File giọng đọc", "♪"), ("visual", "Video / Ảnh", "▣"),
             ("bgm", "Nhạc nền", "♫"), ("scenes", "Cảnh hợp lệ", "✓"),
             ("duration", "Tổng thời lượng", "◐")]
    for i, (key, label, icon) in enumerate(specs):
        tile = StatTile(stats, th, label, "—", color_key=key, icon=icon)
        tile.grid_in(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
        app.tiles[key] = tile

    paths = Card(page, th, "Thư mục làm việc",
                 "Ba đường dẫn bắt buộc. Huy hiệu bên phải cho biết đường dẫn có tồn tại hay không.",
                 accent="dashboard", icon="▦")
    paths.grid_in(row=1, column=0, sticky="ew", pady=(0, 16))
    paths.columnconfigure(0, weight=1)
    paths.columnconfigure(1, weight=1)

    PathPicker(paths, th, "Folder VIDEO — chứa Audio/, Videos/, Images/, Texts/",
               app.vars["input_dir"], "dir",
               on_change=lambda *_: (refresh_overview(app), refresh_music(app))
               ).grid(row=0, column=0, sticky="ew", padx=(0, 16), pady=(0, 14))
    PathPicker(paths, th, "Folder KÊNH — chứa Logo/, BGM/, Text Claim/, SFX/",
               app.vars["channel_dir"], "dir",
               on_change=lambda *_: app.refresh_all_lists()
               ).grid(row=0, column=1, sticky="ew", pady=(0, 14))
    PathPicker(paths, th, "Folder CapCut Drafts",
               app.vars["capcut_drafts"], "dir",
               hint="…/CapCut/User Data/Projects/com.lveditor.draft"
               ).grid(row=1, column=0, sticky="ew", padx=(0, 16))

    right = ttk.Frame(paths, style="Surface.TFrame")
    right.grid(row=1, column=1, sticky="ew")
    right.columnconfigure(0, weight=1)
    ttk.Label(right, text="Tên project CapCut", style="Field.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w")
    ttk.Entry(right, textvariable=app.vars["draft_name"]).grid(
        row=1, column=0, columnspan=2, sticky="ew", pady=(5, 12))

    ttk.Label(right, text="Khung hình", style="Field.TLabel").grid(row=2, column=0, sticky="w")
    ratio = ttk.Frame(right, style="Surface.TFrame")
    ratio.grid(row=3, column=0, sticky="w", pady=(3, 0))
    ttk.Radiobutton(ratio, text="Ngang 16:9", variable=app.vars["aspect"],
                    value="landscape").pack(side="left", padx=(0, 18))
    ttk.Radiobutton(ratio, text="Dọc 9:16", variable=app.vars["aspect"],
                    value="portrait").pack(side="left")

    fps_box = ttk.Frame(right, style="Surface.TFrame")
    fps_box.grid(row=2, column=1, rowspan=2, sticky="e")
    field_row(fps_box, th, "FPS", app.vars["fps"], width=8).pack(side="left", padx=(0, 12))
    labeled_combo(fps_box, th, "Hiệu ứng ảnh", app.vars["image_anim"],
                  animations.MODE_CHOICES, fallback=animations.MODE_VARIETY,
                  width=26).pack(side="left")

    bottom = ttk.Frame(page)
    bottom.grid(row=2, column=0, sticky="nsew")
    bottom.columnconfigure(1, weight=1)
    bottom.rowconfigure(0, weight=1)

    feat = Card(bottom, th, "Chức năng", "Tắt bớt để dựng nhanh hơn.",
                accent="scenes", icon="⚙")
    feat.grid_in(row=0, column=0, sticky="nsew", padx=(0, 16))
    from .app import BOOL_LABELS
    feat.columnconfigure(0, weight=1, uniform="feat")
    feat.columnconfigure(1, weight=1, uniform="feat")
    items = [(k, v) for k, v in BOOL_LABELS.items() if k in app.boolvars]
    half = (len(items) + 1) // 2
    for i, (key, label) in enumerate(items):
        r, c = (i, 0) if i < half else (i - half, 1)
        ttk.Checkbutton(feat, text=label, variable=app.boolvars[key]).grid(
            row=r, column=c, sticky="w", pady=1, padx=(0, 12))
    feat.rowconfigure(half, weight=1)
    actions = ttk.Frame(feat, style="Surface.TFrame")
    actions.grid(row=half + 1, column=0, columnspan=2, sticky="ews", pady=(18, 0))
    for i in range(3):
        actions.columnconfigure(i, weight=1, uniform="act")
    ttk.Button(actions, text="Lưu cài đặt kênh", style="Secondary.TButton",
               command=app.save_channel).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Button(actions, text="Làm mới asset", style="Ghost.TButton",
               command=app.refresh_all_lists).grid(row=0, column=1, sticky="ew", padx=(0, 8))
    ttk.Button(actions, text="Mở folder VIDEO", style="Ghost.TButton",
               command=lambda: _open_folder(Path(app.vars["input_dir"].get()))
               ).grid(row=0, column=2, sticky="ew")

    logcard = Card(bottom, th, padding=16, accent="bgm")
    logcard.grid_in(row=0, column=1, sticky="nsew")
    app.logview = LogView(logcard, th, height=11)
    app.logview.pack(fill="both", expand=True)


def refresh_overview(app):
    """Đếm nhanh file trong folder VIDEO để hiện lên ô thống kê."""
    from ..models import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS
    if not hasattr(app, "tiles"):
        return
    raw = app.vars["input_dir"].get().strip()
    base = Path(raw) if raw else None

    def count(sub, exts):
        d = base / sub if base else None
        if not d or not d.is_dir():
            return 0
        return sum(1 for f in d.iterdir()
                   if f.is_file() and f.suffix.lower() in exts and f.stem.isdigit())

    audio = 0
    if base and base.is_dir():
        for name in ("Audio", "Voice", "Voices", "audio", "voice"):
            audio = count(name, AUDIO_EXTS)
            if audio:
                break
    visual = count("Videos", VIDEO_EXTS) + count("Images", IMAGE_EXTS)
    app.tiles["audio"].set(audio or "—")
    app.tiles["visual"].set(visual or "—")
    app.tiles["bgm"].set(len(list_bgm_files(app.bgm_folder())) or "—")


def update_asset_stats(app, assets):
    if not hasattr(app, "tiles"):
        return
    app.tiles["audio"].set(len(assets.audios))
    app.tiles["visual"].set(len(assets.videos) + len(assets.images))
    app.tiles["bgm"].set(len(assets.bgm_files))


def update_plan_stats(app, plan, errors):
    if not hasattr(app, "tiles"):
        return
    app.tiles["scenes"].set(f"{len(plan)}" + (f" / {len(plan)+len(errors)}" if errors else ""))
    total = plan[-1].end if plan else 0.0
    app.tiles["duration"].set(_fmt_dur(total))


# =========================================================================== #
# 2. CÀI ĐẶT — một trang, năm tab con
# =========================================================================== #
def build_settings(app):
    page = app.pages["settings"]
    page.columnconfigure(0, weight=1)
    page.rowconfigure(1, weight=1)
    th = app.theme

    app.settings_tabs = SegmentedTabs(page, th, SETTING_TABS,
                                      on_change=lambda k: show_setting_tab(app, k))
    app.settings_tabs.grid(row=0, column=0, sticky="ew", pady=(0, 14))

    holder = ttk.Frame(page)
    holder.grid(row=1, column=0, sticky="nsew")
    holder.columnconfigure(0, weight=1)
    holder.rowconfigure(0, weight=1)
    app.setting_pages = {}
    for key, _ in SETTING_TABS:
        frame = ttk.Frame(holder)
        frame.grid(row=0, column=0, sticky="nsew")
        app.setting_pages[key] = frame

    build_scenes(app, app.setting_pages["scenes"])
    build_music(app, app.setting_pages["music"])
    build_sfx(app, app.setting_pages["sfx"])
    build_subtitle(app, app.setting_pages["subtitle"])
    build_advanced(app, app.setting_pages["advanced"])
    show_setting_tab(app, "scenes")


def show_setting_tab(app, key: str):
    frame = app.setting_pages.get(key)
    if frame is not None:
        frame.tkraise()
        app.settings_tabs.current = key
        app.settings_tabs._paint()


# --------------------------------------------------------------------------- #
# 2a. Cảnh quay
# --------------------------------------------------------------------------- #
SCENE_COLS = [
    ("num", "Cảnh", 62, "center"),
    ("mode", "Chế độ", 76, "center"),
    ("audio", "Giọng đọc", 140, "w"),
    ("dur", "Dài", 62, "center"),
    ("gap", "Nghỉ", 60, "center"),
    ("visual", "Hình ảnh / video", 150, "w"),
    ("speed", "Tốc độ", 68, "center"),
    ("start", "Bắt đầu", 70, "center"),
    ("note", "Ghi chú", 280, "w"),
]


def build_scenes(app, page):
    page.columnconfigure(0, weight=1)
    page.rowconfigure(1, weight=1)
    th = app.theme

    bar = Card(page, th, padding=14, accent="settings")
    bar.grid_in(row=0, column=0, sticky="ew", pady=(0, 12))
    app.scene_filter = tk.StringVar(value="all")
    ttk.Label(bar, text="Lọc:", style="Field.TLabel").pack(side="left", padx=(0, 10))
    for value, label in [("all", "Tất cả"), ("CUT", "Cắt"), ("SLOW", "Chậm"),
                         ("SPEEDUP", "Nhanh"), ("IMAGE", "Ảnh"), ("ERR", "Lỗi")]:
        ttk.Radiobutton(bar, text=label, variable=app.scene_filter, value=value,
                        command=lambda: _apply_scene_filter(app)).pack(side="left", padx=(0, 14))
    app.scene_summary = ttk.Label(bar, text="Chưa có dữ liệu — bấm KIỂM TRA.",
                                  style="SurfaceDim.TLabel")
    app.scene_summary.pack(side="right")

    table_card = Card(page, th, padding=1, accent="settings")
    table_card.grid_in(row=1, column=0, sticky="nsew")
    wrap = ttk.Frame(table_card, style="Surface.TFrame")
    wrap.pack(fill="both", expand=True)

    tree = ttk.Treeview(wrap, columns=[c[0] for c in SCENE_COLS], show="headings",
                        selectmode="browse")
    for key, label, width, anchor in SCENE_COLS:
        tree.heading(key, text=label, anchor=anchor)
        tree.column(key, width=width, minwidth=48, anchor=anchor,
                    stretch=(key in ("visual", "note")))
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    app.scene_tree = tree
    _configure_scene_tags(app)
    th.on_change(lambda c: _configure_scene_tags(app))
    app.scene_rows = []


def _configure_scene_tags(app):
    """Mỗi chế độ dựng một màu nền riêng — liếc bảng là thấy ngay tỉ lệ."""
    th = app.theme
    c = th.c
    t = app.scene_tree
    t.tag_configure("odd", background=c["row_alt"])
    t.tag_configure("even", background=c["surface"])
    for mode, col in th.mode_color.items():
        t.tag_configure(f"m{mode}", background=th.soft(col, 0.14), foreground=c["text"])
    t.tag_configure("mERR", background=th.soft(th.mode_color["ERR"], 0.20),
                    foreground=th.mode_color["ERR"])


def fill_scene_table(app, plan, errors):
    rows = []
    for p in plan:
        rows.append({
            "mode": p.mode,
            "values": (
                f"{p.number:04d}",
                MODE_LABEL.get(p.mode, p.mode),
                p.audio_path.name,
                _fmt_dur(p.audio_duration),
                f"{p.gap:.2f}s" if p.gap else "—",
                p.visual_path.name,
                f"{p.speed:.2f}×" if p.mode in ("SLOW", "SPEEDUP") else "1.00×",
                _fmt_dur(p.start),
                _scene_note(p),
            ),
        })
    for e in errors:
        num, _, rest = str(e).partition(":")
        rows.append({
            "mode": "ERR",
            "values": (num.strip(), "Lỗi", "—", "—", "—", "—", "—", "—",
                       rest.strip() or str(e)),
        })
    rows.sort(key=lambda r: r["values"][0])
    app.scene_rows = rows
    _apply_scene_filter(app)

    counts = {m: sum(1 for r in rows if r["mode"] == m)
              for m in ("CUT", "SLOW", "SPEEDUP", "IMAGE", "ERR")}
    total = plan[-1].end if plan else 0
    app.scene_summary.configure(
        text=(f"Cắt {counts['CUT']}  ·  Chậm {counts['SLOW']}  ·  Nhanh {counts['SPEEDUP']}"
              f"  ·  Ảnh {counts['IMAGE']}  ·  Lỗi {counts['ERR']}  ·  Tổng {_fmt_dur(total)}"),
        style="Err.TLabel" if counts["ERR"] else "SurfaceDim.TLabel")


def _scene_note(p) -> str:
    extra = f" (đã tính {p.gap:.2f}s nghỉ)" if p.gap else ""
    if p.mode == "SLOW":
        return f"Video {p.video_duration:.1f}s ngắn hơn giọng đọc → làm chậm{extra}"
    if p.mode == "SPEEDUP":
        return f"Video {p.video_duration:.1f}s dài hơn giọng đọc → tăng tốc{extra}"
    if p.mode == "IMAGE":
        return f"Ảnh tĩnh + hiệu ứng Ken Burns{extra}"
    return f"Cắt video theo độ dài giọng đọc{extra}"


def _apply_scene_filter(app):
    tree = app.scene_tree
    tree.delete(*tree.get_children())
    want = app.scene_filter.get()
    for row in app.scene_rows:
        if want != "all" and row["mode"] != want:
            continue
        tree.insert("", "end", values=row["values"], tags=(f"m{row['mode']}",))


# --------------------------------------------------------------------------- #
# 2b. Nhạc nền
# --------------------------------------------------------------------------- #
def build_music(app, page):
    page.columnconfigure(0, weight=1)
    page.rowconfigure(1, weight=1)
    th = app.theme

    bar = Card(page, th, padding=14)
    bar.grid_in(row=0, column=0, sticky="ew", pady=(0, 12))
    ttk.Label(bar, text="Intro = mở đầu (to hơn) · Nền = phát xoay vòng suốt video · "
                        "Hệ số nhân với âm lượng gốc.",
              style="SurfaceDim.TLabel").pack(side="left")
    ttk.Button(bar, text="Làm mới", style="Ghost.TButton",
               command=lambda: refresh_music(app)).pack(side="right")
    ttk.Button(bar, text="Mở folder", style="Ghost.TButton",
               command=lambda: _open_folder(app.bgm_folder())).pack(side="right", padx=(0, 6))
    ttk.Button(bar, text="Thêm file nhạc…", style="Secondary.TButton",
               command=lambda: _add_music(app)).pack(side="right", padx=(0, 8))

    card = Card(page, th, padding=14)
    card.grid_in(row=1, column=0, sticky="nsew")
    app.music_scroll = ScrollFrame(card, th)
    app.music_scroll.pack(fill="both", expand=True)
    app.music_wrap = app.music_scroll.inner


def refresh_music(app):
    if not hasattr(app, "music_wrap"):
        return
    old = {r["name"]: {"intro": r["intro"].get(), "bg": r["bg"].get(),
                       "volume": r["volume"].get()} for r in app.music_rows}
    for w in app.music_wrap.winfo_children():
        w.destroy()
    app.music_rows = []
    files = list_bgm_files(app.bgm_folder())
    app.music_wrap.columnconfigure(0, weight=1)

    if not files:
        ttk.Label(app.music_wrap,
                  text="Chưa có file nhạc. Đặt file .mp3/.wav vào folder BGM của kênh, "
                       "hoặc bấm “Thêm file nhạc…”.",
                  style="Dim.TLabel", wraplength=720).grid(row=0, column=0, sticky="w", pady=22)
        return

    for col, w in ((0, 1), (1, 0), (2, 0), (3, 0)):
        app.music_wrap.columnconfigure(col, weight=w, minsize=(0 if w else 82))
    ttk.Label(app.music_wrap, text="Tên file", style="Dim.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 10))
    for i, t in enumerate(("Intro", "Nền", "Hệ số"), start=1):
        ttk.Label(app.music_wrap, text=t, style="Dim.TLabel").grid(
            row=0, column=i, pady=(0, 10))

    for i, f in enumerate(files):
        state = old.get(f.name, {"intro": i == 0, "bg": True, "volume": "1.0"})
        intro = tk.BooleanVar(value=bool(state["intro"]))
        bg = tk.BooleanVar(value=bool(state["bg"]))
        vol = tk.StringVar(value=str(state["volume"]))
        r = i + 1
        ttk.Label(app.music_wrap, text=f.name).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Checkbutton(app.music_wrap, text="", variable=intro,
                        style="Plain.TCheckbutton").grid(row=r, column=1, pady=4)
        ttk.Checkbutton(app.music_wrap, text="", variable=bg,
                        style="Plain.TCheckbutton").grid(row=r, column=2, pady=4)
        ttk.Entry(app.music_wrap, textvariable=vol, width=7, justify="center").grid(
            row=r, column=3, pady=4, padx=(6, 12))
        app.music_rows.append({"name": f.name, "path": f, "intro": intro,
                               "bg": bg, "volume": vol})
    refresh_overview(app)


def _add_music(app):
    src = filedialog.askopenfilename(title="Chọn file nhạc",
                                     filetypes=[("Âm thanh", "*.mp3 *.wav *.m4a *.aac *.flac"),
                                                ("Tất cả", "*.*")])
    if not src:
        return
    dest = app.bgm_folder()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / Path(src).name)
    except OSError as e:
        messagebox.showerror("Lỗi", str(e))
        return
    refresh_music(app)
    app.log(f"[OK] Đã thêm nhạc: {Path(src).name}")


# --------------------------------------------------------------------------- #
# 2c. SFX
# --------------------------------------------------------------------------- #
def build_sfx(app, page):
    page.columnconfigure(0, weight=1)
    page.rowconfigure(1, weight=1)
    th = app.theme

    bar = Card(page, th, padding=14)
    bar.grid_in(row=0, column=0, sticky="ew", pady=(0, 12))
    ttk.Label(bar, text="off = bỏ qua · placed = chèn vào timeline · "
                        "muted = nạp sẵn nhưng tắt tiếng để tự dùng trong CapCut.",
              style="SurfaceDim.TLabel").pack(side="left")
    for text, cmd, style in [("Nhập từ CapCut", lambda: _harvest_sfx(app), "Ghost.TButton"),
                             ("Thêm file…", lambda: _add_sfx(app), "Secondary.TButton"),
                             ("Tất cả placed", lambda: _bulk_sfx(app, "placed"), "Ghost.TButton"),
                             ("Tất cả muted", lambda: _bulk_sfx(app, "muted"), "Ghost.TButton"),
                             ("Tắt hết", lambda: _bulk_sfx(app, "off"), "Ghost.TButton")]:
        ttk.Button(bar, text=text, style=style, command=cmd).pack(side="right", padx=(0, 6))

    card = Card(page, th, padding=14)
    card.grid_in(row=1, column=0, sticky="nsew")
    app.sfx_scroll = ScrollFrame(card, th)
    app.sfx_scroll.pack(fill="both", expand=True)
    app.sfx_wrap = app.sfx_scroll.inner


def refresh_sfx(app):
    if not hasattr(app, "sfx_wrap"):
        return
    from .app import SFX_LIBRARY
    old = {r["name"]: r["role"].get() for r in app.sfx_rows}
    for w in app.sfx_wrap.winfo_children():
        w.destroy()
    app.sfx_rows = []
    ch = app.vars["channel_dir"].get().strip()
    items = list_sfx_items(SFX_LIBRARY, Path(ch) if ch else Path("."))
    app.sfx_wrap.columnconfigure(0, weight=1)

    if not items:
        ttk.Label(app.sfx_wrap,
                  text="Chưa có SFX. Thêm file vào folder SFX của kênh, bấm “Thêm file…”, "
                       "hoặc “Nhập từ CapCut” để lấy SFX từ các draft có sẵn.",
                  style="Dim.TLabel", wraplength=720).grid(row=0, column=0, sticky="w", pady=22)
        return

    app.sfx_wrap.columnconfigure(1, weight=1)
    ttk.Label(app.sfx_wrap, text="Nhóm", style="Dim.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 10))
    ttk.Label(app.sfx_wrap, text="Tên file", style="Dim.TLabel").grid(
        row=0, column=1, sticky="w", pady=(0, 10))
    ttk.Label(app.sfx_wrap, text="Vai trò", style="Dim.TLabel").grid(
        row=0, column=2, pady=(0, 10), padx=(0, 12))
    for i, it in enumerate(items, start=1):
        role = tk.StringVar(value=old.get(it["name"], "off"))
        ttk.Label(app.sfx_wrap, text=it["category"], style="Dim.TLabel", width=16).grid(
            row=i, column=0, sticky="w", pady=4)
        ttk.Label(app.sfx_wrap, text=it["name"]).grid(row=i, column=1, sticky="w", pady=4)
        ttk.Combobox(app.sfx_wrap, textvariable=role, state="readonly", width=10,
                     values=["off", "placed", "muted"]).grid(
            row=i, column=2, pady=4, padx=(10, 12))
        app.sfx_rows.append({"name": it["name"], "path": it["path"], "role": role})


def _bulk_sfx(app, role: str):
    for r in app.sfx_rows:
        r["role"].set(role)


def _add_sfx(app):
    from .app import SFX_LIBRARY
    src = filedialog.askopenfilename(title="Chọn file SFX",
                                     filetypes=[("Âm thanh", "*.mp3 *.wav *.m4a *.aac"),
                                                ("Tất cả", "*.*")])
    if not src:
        return
    dest = SFX_LIBRARY / "added"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / Path(src).name)
    except OSError as e:
        messagebox.showerror("Lỗi", str(e))
        return
    refresh_sfx(app)
    app.log(f"[OK] Đã thêm SFX: {Path(src).name}")


def _harvest_sfx(app):
    from .app import SFX_LIBRARY
    cap = app.vars["capcut_drafts"].get().strip()
    if not cap:
        messagebox.showwarning("Thiếu đường dẫn", "Chọn folder CapCut Drafts ở trang Tổng quan.")
        return
    n = harvest_sfx_from_capcut(SFX_LIBRARY, Path(cap), app.log)
    refresh_sfx(app)
    messagebox.showinfo("SFX", f"Đã nhập {n} file SFX mới từ CapCut.")


# --------------------------------------------------------------------------- #
# 2d. Phụ đề
# --------------------------------------------------------------------------- #
def build_subtitle(app, page):
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    th = app.theme
    scroll = ScrollFrame(page, th)
    scroll.grid(row=0, column=0, sticky="nsew")
    host = scroll.inner
    host.columnconfigure(0, weight=1)

    src = Card(host, th, "Nguồn lời thoại",
               "Tự động = ưu tiên _manifest.json, rồi Excel, rồi Texts/*.txt.",
               accent="settings", icon="✎")
    src.grid_in(row=0, column=0, sticky="ew", pady=(0, 16))
    src.columnconfigure(1, weight=1)
    labeled_combo(src, th, "Nguồn", app.vars["subtitle_source"], SUB_SOURCE_CHOICES,
                  fallback="auto", width=38).grid(row=0, column=0, sticky="w", pady=(0, 14))

    PathPicker(src, th, "File Excel (nếu dùng nguồn Excel)", app.vars["subtitle_file"], "file",
               filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tất cả", "*.*")]).grid(
        row=1, column=0, columnspan=2, sticky="ew")
    ttk.Button(src, text="Đọc cột từ Excel", style="Secondary.TButton",
               command=lambda: _load_excel(app)).grid(row=2, column=0, sticky="w", pady=(12, 14))

    cols = ttk.Frame(src, style="Surface.TFrame")
    cols.grid(row=3, column=0, columnspan=2, sticky="ew")
    for i in range(3):
        cols.columnconfigure(i, weight=1)
    field_row(cols, th, "Sheet", app.vars["excel_sheet"]).grid(
        row=0, column=0, sticky="ew", padx=(0, 14))
    field_row(cols, th, "Cột lời thoại", app.vars["excel_script_col"]).grid(
        row=0, column=1, sticky="ew", padx=(0, 14))
    field_row(cols, th, "Cột số cảnh", app.vars["excel_scene_col"]).grid(
        row=0, column=2, sticky="ew")

    style_card = Card(host, th, "Kiểu chữ & chuyển cảnh",
                      "Nhập style từ các draft CapCut có sẵn rồi áp lại sau khi import SRT.")
    style_card.grid_in(row=1, column=0, sticky="ew", pady=(0, 16))
    style_card.columnconfigure(1, weight=1)
    ttk.Label(style_card, text="Style phụ đề", style="Field.TLabel").grid(
        row=0, column=0, sticky="w")
    app.style_cb = ttk.Combobox(style_card, textvariable=app.vars["subtitle_style"],
                                state="readonly")
    app.style_cb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
    btns = ttk.Frame(style_card, style="Surface.TFrame")
    btns.grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(5, 0))
    ttk.Button(btns, text="Làm mới", style="Ghost.TButton",
               command=lambda: refresh_styles(app)).pack(side="left", padx=(0, 6))
    ttk.Button(btns, text="Nhập từ CapCut", style="Ghost.TButton",
               command=lambda: _harvest_styles(app)).pack(side="left")

    low = ttk.Frame(style_card, style="Surface.TFrame")
    low.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(16, 0))
    for i in range(2):
        low.columnconfigure(i, weight=1)
    field_row(low, th, "Kiểu chuyển cảnh", app.vars["transition_type"],
              hint="Tên hiệu ứng theo pycapcut, mặc định 叠化 (hòa tan).").grid(
        row=0, column=0, sticky="ew", padx=(0, 14))
    field_row(low, th, "Số từ tối đa mỗi dòng", app.vars["sub_max_words"]).grid(
        row=0, column=1, sticky="ew")

    shadow = Card(host, th, "Bóng đổ chữ",
                  "Mặc định BẬT với độ mờ 90% để chữ luôn tách khỏi nền, "
                  "áp cho cả draft CapCut lẫn bản render mp4.", accent="settings")
    shadow.grid_in(row=2, column=0, sticky="ew")
    shadow.columnconfigure(0, weight=1)
    shadow.columnconfigure(1, weight=1)
    ttk.Checkbutton(shadow, text="Bật bóng đổ cho phụ đề",
                    variable=app.boolvars["sub_shadow"]).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
    SliderField(shadow, th, "Độ mờ bóng", app.vars["sub_shadow_alpha"],
                from_=0.0, to=1.0, step=0.05, decimals=2,
                unit="0 = trong suốt · 1 = đen đặc",
                hint="Mặc định 0.90 (90%).").grid(row=1, column=0, sticky="ew", padx=(0, 16))
    SliderField(shadow, th, "Khoảng cách bóng", app.vars["sub_shadow_distance"],
                from_=0.0, to=20.0, step=0.5, decimals=1, unit="điểm",
                hint="Mặc định 5.0 — bóng đổ chéo xuống phải.").grid(
        row=1, column=1, sticky="ew")
    refresh_styles(app)


def refresh_styles(app):
    if not hasattr(app, "style_cb"):
        return
    from .app import SUB_STYLES
    app.style_cb.configure(values=[""] + [p.stem for p in list_sub_styles(SUB_STYLES)])


def _harvest_styles(app):
    from .app import SUB_STYLES
    cap = app.vars["capcut_drafts"].get().strip()
    if not cap:
        messagebox.showwarning("Thiếu đường dẫn", "Chọn folder CapCut Drafts ở trang Tổng quan.")
        return
    n = harvest_sub_styles(SUB_STYLES, Path(cap), app.log)
    refresh_styles(app)
    messagebox.showinfo("Style phụ đề", f"Đã nhập {n} style.")


def _load_excel(app):
    raw = app.vars["subtitle_file"].get().strip()
    if not raw:
        messagebox.showwarning("Thiếu file", "Chọn file Excel trước.")
        return
    try:
        sheets, headers = excel_columns(Path(raw))
    except Exception as e:
        messagebox.showerror("Không đọc được Excel", str(e))
        return
    app.vars["excel_sheet"].set(sheets[0] if sheets else "")
    script = next((h for h in headers if any(
        x in h.lower() for x in ("script", "text", "content", "thoại", "loi", "lời"))), "")
    scene = next((h for h in headers if any(
        x in h.lower() for x in ("scene", "stt", "panel", "cảnh"))), "")
    app.vars["excel_script_col"].set(script)
    app.vars["excel_scene_col"].set(scene)
    app.log(f"[OK] Excel: {len(headers)} cột — {', '.join(headers[:10])}")
    messagebox.showinfo("Excel", f"Đã đọc {len(headers)} cột.\n\n"
                                 f"Cột lời thoại: {script or '(chưa đoán được)'}\n"
                                 f"Cột số cảnh: {scene or '(chưa đoán được)'}")


# --------------------------------------------------------------------------- #
# 2e. Nâng cao
# --------------------------------------------------------------------------- #
def build_advanced(app, page):
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    th = app.theme
    scroll = ScrollFrame(page, th)
    scroll.grid(row=0, column=0, sticky="nsew")
    host = scroll.inner
    host.columnconfigure(0, weight=1)

    pace = Card(host, th, "Nhịp hội thoại",
                "Khoảng nghỉ chèn sau mỗi cảnh để các câu thoại không dính liền nhau. "
                "Hình của cảnh đó được kéo dài để lấp chỗ trống nên không bao giờ đen màn.",
                accent="settings", icon="⚙")
    pace.grid_in(row=0, column=0, sticky="ew", pady=(0, 16))
    pace.columnconfigure(0, weight=1)
    pace.columnconfigure(1, weight=1)
    SliderField(pace, th, "Khoảng nghỉ giữa các cảnh", app.vars["scene_gap"],
                from_=0.0, to=2.0, step=0.05, decimals=2, unit="giây",
                hint="0.00 = nối liền như các bản trước · 0.40 là mặc định.").grid(
        row=0, column=0, sticky="ew", padx=(0, 16))
    SliderField(pace, th, "Âm lượng tiếng gốc của video", app.vars["video_vol"],
                from_=0.0, to=2.0, step=0.05, decimals=2, unit="hệ số",
                hint="0.00 = tắt tiếng video · 1.00 = giữ nguyên như bản gốc.").grid(
        row=0, column=1, sticky="ew")

    over = Card(host, th, "Asset thay thế", "Để trống sẽ dùng asset trong folder kênh.")
    over.grid_in(row=1, column=0, sticky="ew", pady=(0, 16))
    over.columnconfigure(0, weight=1)
    over.columnconfigure(1, weight=1)
    img_types = [("Ảnh", "*.png *.jpg *.jpeg *.webp"), ("Tất cả", "*.*")]
    PathPicker(over, th, "Logo tùy chỉnh", app.vars["logo_path"], "file",
               filetypes=img_types).grid(row=0, column=0, sticky="ew", padx=(0, 16))
    PathPicker(over, th, "Claim tùy chỉnh", app.vars["claim_path"], "file",
               filetypes=img_types).grid(row=0, column=1, sticky="ew")
    PathPicker(over, th, "Folder nhạc BGM riêng", app.vars["bgm_dir"], "dir",
               on_change=lambda *_: refresh_music(app)).grid(
        row=1, column=0, sticky="ew", padx=(0, 16), pady=(14, 0))

    audio = Card(host, th, "Âm lượng", "Hệ số nhân so với âm lượng gốc của file.")
    audio.grid_in(row=2, column=0, sticky="ew", pady=(0, 16))
    _grid_fields(app, audio, th, [
        ("Giọng đọc", "voice_vol", "Mặc định 3.16"),
        ("Nhạc nền (thân bài)", "bgm_body_vol", "Mặc định 0.18"),
        ("Intro to", "bgm_intro_vol_high", ""),
        ("Intro nhỏ", "bgm_intro_vol_low", ""),
        ("Intro giữ to (giây)", "bgm_intro_high_dur", ""),
        ("Intro tối đa (giây)", "bgm_intro_max_dur", ""),
        ("Crossfade (giây)", "crossfade_sec", "Chồng mờ giữa 2 bài"),
    ])

    video = Card(host, th, "Hình ảnh & chuyển cảnh")
    video.grid_in(row=3, column=0, sticky="ew", pady=(0, 16))
    _grid_fields(app, video, th, [
        ("Tốc độ chậm tối thiểu", "min_speed", "Dưới mức này sẽ đổi sang ảnh"),
        ("Thời lượng chuyển cảnh", "trans_dur", "giây"),
        ("Thời lượng claim", "claim_dur", "giây"),
    ])

    logo = Card(host, th, "Vị trí logo", "Toạ độ theo hệ của CapCut: -1 đến 1.")
    logo.grid_in(row=4, column=0, sticky="ew", pady=(0, 16))
    _grid_fields(app, logo, th, [
        ("Logo X", "logo_x", "Dương = sang phải"),
        ("Logo Y", "logo_y", "Âm = xuống dưới"),
        ("Logo scale", "logo_scale", "0.09 ≈ 9% khung hình"),
    ])

    note = Card(host, th, "Cập nhật & bảo mật")
    note.grid_in(row=5, column=0, sticky="ew")
    note.columnconfigure(0, weight=1)
    ttk.Label(note, text="Tool kiểm tra bản mới trên GitHub Releases. File cài đặt tải về "
                         "chỉ được chạy khi mã SHA-256 khớp đúng bảng băm công bố kèm bản "
                         "phát hành — không khớp thì tool tự xoá file.",
              style="SurfaceDim.TLabel", wraplength=860, justify="left").grid(
        row=0, column=0, sticky="w")
    row = ttk.Frame(note, style="Surface.TFrame")
    row.grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Checkbutton(row, text="Tự kiểm tra bản mới khi mở tool",
                    variable=app.boolvars["auto_update_check"]).pack(side="left", padx=(0, 16))
    ttk.Button(row, text="Kiểm tra cập nhật ngay", style="Secondary.TButton",
               command=lambda: app.check_updates(manual=True)).pack(side="left")


def _grid_fields(app, card, th, specs, per_row: int = 4):
    grid = ttk.Frame(card, style="Surface.TFrame")
    grid.pack(fill="x")
    for i in range(per_row):
        grid.columnconfigure(i, weight=1, uniform="adv")
    for i, (label, key, hint) in enumerate(specs):
        r, c = divmod(i, per_row)
        field_row(grid, th, label, app.vars[key], hint=hint).grid(
            row=r, column=c, sticky="new", padx=(0, 16), pady=(0, 16))


# =========================================================================== #
# 3. RENDER VIDEO
# =========================================================================== #
QUEUE_COLS = [
    ("name", "Project", 170, "w"),
    ("state", "Trạng thái", 136, "center"),
    ("pct", "Tiến độ", 80, "center"),
    ("dur", "Thời lượng", 90, "center"),
    ("eta", "Còn lại", 110, "center"),
    ("out", "File xuất ra", 320, "w"),
]


def build_render(app):
    page = app.pages["render"]
    page.columnconfigure(0, weight=1)
    page.rowconfigure(2, weight=1)
    th = app.theme

    # --- cài đặt xuất ---
    opts = Card(page, th, "Cài đặt xuất video",
                "Engine ffmpeg render thẳng trong tool. Engine CapCut nhờ CapCut tự bấm "
                "Export — cho ra bản đúng y CapCut nhưng chỉ chạy trên Windows.",
                accent="render", icon="⚙")
    opts.grid_in(row=0, column=0, sticky="ew", pady=(0, 14))
    for i in range(4):
        opts.columnconfigure(i, weight=1, uniform="ropt")

    engine_cell = ttk.Frame(opts, style="Surface.TFrame")
    engine_cell.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 16), pady=(0, 14))
    labeled_combo(engine_cell, th, "Engine", app.vars["render_engine"], ENGINE_CHOICES,
                  fallback="ffmpeg", width=34).pack(fill="x")
    ttk.Button(engine_cell, text="⚙   Chẩn đoán CapCut", style="Secondary.TButton",
               command=app.diagnose_capcut).pack(anchor="w", pady=(9, 0))
    labeled_combo(opts, th, "Độ phân giải", app.vars["render_res"], render.RES_CHOICES,
                  fallback="source").grid(row=0, column=2, sticky="ew", padx=(0, 16),
                                          pady=(0, 14))
    field_row(opts, th, "FPS khi render", app.vars["render_fps"],
              hint="0 = giữ FPS của project").grid(row=0, column=3, sticky="ew", pady=(0, 14))

    labeled_combo(opts, th, "Định dạng nén", app.vars["render_codec"], render.CODEC_CHOICES,
                  fallback="h264").grid(row=1, column=0, sticky="ew", padx=(0, 16), pady=(0, 14))
    labeled_combo(opts, th, "Chất lượng", app.vars["render_crf"], render.QUALITY_CHOICES,
                  fallback="20").grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=(0, 14))
    labeled_combo(opts, th, "Tốc độ nén", app.vars["render_preset"], render.PRESET_CHOICES,
                  fallback="medium").grid(row=1, column=2, sticky="ew", padx=(0, 16),
                                          pady=(0, 14))
    labeled_combo(opts, th, "Tăng tốc phần cứng", app.vars["render_hw"], HW_CHOICES,
                  fallback="auto").grid(row=1, column=3, sticky="ew", pady=(0, 14))

    PathPicker(opts, th, "Thư mục lưu video", app.vars["render_out_dir"], "dir",
               hint="Để trống sẽ lưu vào thư mục _render bên trong folder VIDEO").grid(
        row=2, column=0, columnspan=3, sticky="ew", padx=(0, 16))
    flags = ttk.Frame(opts, style="Surface.TFrame")
    flags.grid(row=2, column=3, sticky="w")
    ttk.Checkbutton(flags, text="Ghi phụ đề lên hình",
                    variable=app.boolvars["render_burn_subs"]).pack(anchor="w")
    ttk.Checkbutton(flags, text="Tạo lại draft trước khi xuất",
                    variable=app.boolvars["render_rebuild_draft"]).pack(anchor="w")
    ttk.Checkbutton(flags, text="Mở thư mục khi xong",
                    variable=app.boolvars["render_open_when_done"]).pack(anchor="w")

    # --- tiến độ ---
    prog = Card(page, th, padding=16, accent="render")
    prog.grid_in(row=1, column=0, sticky="ew", pady=(0, 14))
    prog.columnconfigure(0, weight=1)
    head = ttk.Frame(prog, style="Surface.TFrame")
    head.grid(row=0, column=0, sticky="ew")
    app.render_job_lbl = ttk.Label(head, text="Chưa có việc nào trong hàng đợi",
                                   style="H2.TLabel")
    app.render_job_lbl.pack(side="left")
    app.render_pct_lbl = ttk.Label(head, text="0%", style="H2.TLabel")
    app.render_pct_lbl.pack(side="right")
    app.render_progress = ttk.Progressbar(prog, style="Render.Horizontal.TProgressbar",
                                          variable=app.render_pct, maximum=100)
    app.render_progress.grid(row=1, column=0, sticky="ew", pady=(10, 8))
    foot = ttk.Frame(prog, style="Surface.TFrame")
    foot.grid(row=2, column=0, sticky="ew")
    app.render_eta_lbl = ttk.Label(foot, text="Thời gian còn lại: —", style="SurfaceDim.TLabel")
    app.render_eta_lbl.pack(side="left")
    app.render_total_lbl = ttk.Label(foot, text="", style="SurfaceDim.TLabel")
    app.render_total_lbl.pack(side="right")

    btns = ttk.Frame(prog, style="Surface.TFrame")
    btns.grid(row=3, column=0, sticky="ew", pady=(16, 0))
    btns.columnconfigure(0, weight=1)
    left = ttk.Frame(btns, style="Surface.TFrame")
    left.grid(row=0, column=0, sticky="w")
    ttk.Button(left, text="＋ Thêm project", style="Secondary.TButton",
               command=lambda: add_current_to_queue(app)).pack(side="left", padx=(0, 8))
    ttk.Button(left, text="＋ Thêm folder…", style="Secondary.TButton",
               command=lambda: _add_folder_batch(app)).pack(side="left", padx=(0, 8))
    ttk.Button(left, text="Bỏ dòng", style="Ghost.TButton",
               command=lambda: _remove_selected(app)).pack(side="left", padx=(0, 8))
    ttk.Button(left, text="Xoá hết", style="Ghost.TButton",
               command=lambda: _clear_queue(app)).pack(side="left")
    right = ttk.Frame(btns, style="Surface.TFrame")
    right.grid(row=0, column=1, sticky="e")
    app.render_stop_btn = ttk.Button(right, text="Dừng render", style="Danger.TButton",
                                     command=app.request_cancel, state="disabled")
    app.render_stop_btn.pack(side="left", padx=(0, 10))
    app.render_btn = ttk.Button(right, text="▶   BẮT ĐẦU RENDER", style="render.Do.TButton",
                                command=app.start_render)
    app.render_btn.pack(side="left")

    # --- hàng đợi ---
    qcard = Card(page, th, padding=1, accent="render")
    qcard.grid_in(row=2, column=0, sticky="nsew")
    wrap = ttk.Frame(qcard, style="Surface.TFrame")
    wrap.pack(fill="both", expand=True)
    tree = ttk.Treeview(wrap, columns=[c[0] for c in QUEUE_COLS], show="headings",
                        selectmode="browse")
    for key, label, width, anchor in QUEUE_COLS:
        tree.heading(key, text=label, anchor=anchor)
        tree.column(key, width=width, minwidth=60, anchor=anchor,
                    stretch=(key in ("name", "out")))
    sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    app.queue_tree = tree
    _configure_queue_tags(app)
    th.on_change(lambda c: _configure_queue_tags(app))
    refresh_queue(app)


def _configure_queue_tags(app):
    th = app.theme
    c = th.c
    t = app.queue_tree
    for state, col in th.state.items():
        t.tag_configure(state, background=th.soft(col, 0.12), foreground=c["text"])
    t.tag_configure("error", background=th.soft(th.state["error"], 0.20),
                    foreground=th.state["error"])
    t.tag_configure("done", background=th.soft(th.state["done"], 0.12),
                    foreground=th.state["done"])


QUEUE_STATE = {"pending": "○ Chờ", "running": "◐ Đang render", "done": "● Xong",
               "error": "✕ Lỗi", "cancelled": "■ Đã dừng"}


def refresh_queue(app):
    if not hasattr(app, "queue_tree"):
        return
    t = app.queue_tree
    t.delete(*t.get_children())
    for i, item in enumerate(app.render_queue):
        t.insert("", "end", iid=str(i), tags=(item["status"],), values=(
            item["name"],
            QUEUE_STATE.get(item["status"], item["status"]),
            f"{item['percent']:.0f}%",
            _fmt_dur(item["duration"]) if item["duration"] else "—",
            render.fmt_eta(item["eta"]) if item["status"] == "running" else "—",
            item["out"] or "—",
        ))
    pend = sum(1 for i in app.render_queue if i["status"] == "pending")
    done = sum(1 for i in app.render_queue if i["status"] == "done")
    app.render_total_lbl.configure(
        text=f"{len(app.render_queue)} việc · {done} xong · {pend} đang chờ")
    if not app.render_queue:
        app.render_job_lbl.configure(text="Chưa có việc nào trong hàng đợi")


def add_current_to_queue(app):
    try:
        s = app.make_settings()
    except Exception as e:
        messagebox.showerror("Thiếu thông tin", str(e))
        app.show("dashboard")
        return
    app.enqueue(s.draft_name, app.snapshot())
    app.log(f"[QUEUE] Đã thêm vào hàng đợi: {s.draft_name}")


def _add_folder_batch(app):
    """Chọn một thư mục cha, thêm mọi thư mục con có Audio/ vào hàng đợi."""
    parent = filedialog.askdirectory(title="Chọn thư mục CHỨA nhiều folder VIDEO")
    if not parent:
        return
    root = Path(parent)
    found = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if any((child / n).is_dir() for n in ("Audio", "audio", "Voice", "Voices")):
            found.append(child)
    if not found:
        messagebox.showinfo(
            "Không thấy project",
            "Không có thư mục con nào chứa folder Audio/.\n\n"
            "Mỗi project phải là một thư mục riêng có Audio/, Videos/, Images/.")
        return
    if not messagebox.askyesno("Thêm hàng loạt",
                               f"Tìm thấy {len(found)} project:\n\n"
                               + "\n".join(f"• {p.name}" for p in found[:12])
                               + ("\n…" if len(found) > 12 else "")
                               + "\n\nThêm tất cả vào hàng đợi với cài đặt hiện tại?"):
        return
    base = app.snapshot()
    for p in found:
        values = dict(base)
        values["input_dir"] = str(p)
        values["draft_name"] = p.name
        app.enqueue(p.name, values)
    app.log(f"[QUEUE] Đã thêm {len(found)} project từ {root}")


def _remove_selected(app):
    if app.running:
        messagebox.showinfo("Đang chạy", "Dừng render trước khi sửa hàng đợi.")
        return
    sel = app.queue_tree.selection()
    if not sel:
        return
    idx = int(sel[0])
    if 0 <= idx < len(app.render_queue):
        app.render_queue.pop(idx)
        refresh_queue(app)


def _clear_queue(app):
    if app.running:
        messagebox.showinfo("Đang chạy", "Dừng render trước khi xoá hàng đợi.")
        return
    app.render_queue.clear()
    refresh_queue(app)


def update_render_progress(app, name: str, percent: float, eta: float, note: str = ""):
    app.render_pct.set(percent)
    app.render_pct_lbl.configure(text=f"{percent:.0f}%")
    app.render_job_lbl.configure(text=note or f"Đang render: {name}")
    app.render_eta_lbl.configure(
        text=f"Thời gian còn lại: {render.fmt_eta(eta)}" if eta else "Thời gian còn lại: —")


# =========================================================================== #
# 4. PRESET KÊNH
# =========================================================================== #
def build_presets(app):
    page = app.pages["presets"]
    page.columnconfigure(0, weight=1)
    page.rowconfigure(1, weight=1)
    th = app.theme

    card = Card(page, th, "Preset kênh",
                "Mỗi preset lưu toàn bộ đường dẫn, âm lượng, vai trò nhạc/SFX, style phụ đề "
                "và cài đặt render.", accent="presets", icon="★")
    card.grid_in(row=0, column=0, sticky="ew", pady=(0, 16))
    card.columnconfigure(0, weight=1)

    top = ttk.Frame(card, style="Surface.TFrame")
    top.grid(row=0, column=0, sticky="ew")
    top.columnconfigure(0, weight=1)
    app.preset_cb = ttk.Combobox(top, textvariable=app.preset_var, state="readonly")
    app.preset_cb.grid(row=0, column=0, sticky="ew", padx=(0, 12))
    ttk.Button(top, text="Nạp", style="Accent.TButton",
               command=lambda: _load_preset(app)).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(top, text="Ghi đè", style="Secondary.TButton",
               command=lambda: _save_preset(app, overwrite=True)).grid(row=0, column=2, padx=(0, 8))
    ttk.Button(top, text="Lưu thành mới…", style="Secondary.TButton",
               command=lambda: _save_preset(app, overwrite=False)).grid(
        row=0, column=3, padx=(0, 8))
    ttk.Button(top, text="Xóa", style="Danger.TButton",
               command=lambda: _delete_preset(app)).grid(row=0, column=4)

    app.preset_info = ttk.Label(card, text="", style="SurfaceDim.TLabel",
                                wraplength=880, justify="left")
    app.preset_info.grid(row=1, column=0, sticky="w", pady=(12, 0))

    rec = Card(page, th, "Project gần đây", "Nhấp đúp để nạp lại đường dẫn.",
                accent="presets")
    rec.grid_in(row=1, column=0, sticky="nsew")
    rec.columnconfigure(0, weight=1)
    rec.rowconfigure(1, weight=1)

    bar = ttk.Frame(rec, style="Surface.TFrame")
    bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    ttk.Button(bar, text="Xóa lịch sử", style="Ghost.TButton",
               command=lambda: (app.recent.clear(), refresh_recent(app))).pack(side="right")

    wrap = ttk.Frame(rec, style="Surface.TFrame")
    wrap.grid(row=1, column=0, sticky="nsew")
    tree = ttk.Treeview(wrap, columns=("name", "input", "channel", "at"),
                        show="headings", selectmode="browse", height=8)
    for key, label, width, stretch in [("name", "Tên project", 180, False),
                                       ("input", "Folder VIDEO", 380, True),
                                       ("channel", "Folder kênh", 300, True),
                                       ("at", "Lần cuối", 130, False)]:
        tree.heading(key, text=label)
        tree.column(key, width=width, stretch=stretch, anchor="w")
    sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.bind("<Double-1>", lambda e: _load_recent(app))
    app.recent_tree = tree

    refresh_presets(app)
    refresh_recent(app)


def refresh_presets(app):
    if not hasattr(app, "preset_cb"):
        return
    names = app.presets.names()
    app.preset_cb.configure(values=names)
    if app.preset_var.get() not in names:
        app.preset_var.set(names[0] if names else "")
    _update_preset_info(app)


def _update_preset_info(app):
    name = app.preset_var.get()
    if not name:
        app.preset_info.configure(text="Chưa có preset nào. Cấu hình xong thì bấm "
                                       "“Lưu thành mới…” để tạo preset đầu tiên.")
        return
    meta = app.presets.meta(name)
    app.preset_info.configure(
        text=f"Lưu lúc {meta.get('_saved_at', '—')}  ·  "
             f"VIDEO: {meta.get('input_dir') or '—'}  ·  "
             f"Kênh: {meta.get('channel_dir') or '—'}")


def _save_preset(app, overwrite: bool):
    from tkinter import simpledialog
    if overwrite:
        name = app.preset_var.get().strip()
        if not name:
            messagebox.showwarning("Chưa chọn", "Chưa có preset nào để ghi đè.")
            return
    else:
        default = Path(app.vars["channel_dir"].get().strip() or "Kênh mới").name
        name = simpledialog.askstring("Preset mới", "Tên preset:", initialvalue=default,
                                      parent=app.root)
        if not name:
            return
    try:
        p = app.presets.save(name, app.current_values())
    except Exception as e:
        messagebox.showerror("Lỗi", str(e))
        return
    app.preset_var.set(name)
    refresh_presets(app)
    app.log(f"[OK] Đã lưu preset '{name}' → {p}")


def _load_preset(app):
    name = app.preset_var.get().strip()
    if not name:
        return
    data = app.presets.load(name)
    if not data:
        messagebox.showwarning("Trống", f"Preset '{name}' không có dữ liệu.")
        return
    app.apply_values(data)
    _update_preset_info(app)
    app.log(f"[OK] Đã nạp preset '{name}' ({len(data)} thiết lập).")
    app.set_status(f"Đang dùng preset: {name}")


def _delete_preset(app):
    name = app.preset_var.get().strip()
    if not name or not messagebox.askyesno("Xóa preset", f"Xóa preset '{name}'?"):
        return
    app.presets.delete(name)
    app.preset_var.set("")
    refresh_presets(app)
    app.log(f"[OK] Đã xóa preset '{name}'.")


def refresh_recent(app):
    if not hasattr(app, "recent_tree"):
        return
    t = app.recent_tree
    t.delete(*t.get_children())
    for item in app.recent.items():
        t.insert("", "end", values=(item.get("draft_name", ""), item.get("input_dir", ""),
                                    item.get("channel_dir", ""), item.get("at", "")))


def _load_recent(app):
    sel = app.recent_tree.selection()
    if not sel:
        return
    name, input_dir, channel_dir, _ = app.recent_tree.item(sel[0], "values")
    app.vars["input_dir"].set(input_dir)
    if channel_dir:
        app.vars["channel_dir"].set(channel_dir)
    if name:
        app.vars["draft_name"].set(name)
    app.refresh_all_lists()
    app.show("dashboard")
    app.log(f"[OK] Đã nạp project gần đây: {input_dir}")


# =========================================================================== #
# 5. HƯỚNG DẪN
# =========================================================================== #
GUIDE = """CẤU TRÚC THƯ MỤC

VIDEO_FOLDER/                 ← chọn ở ô "Folder VIDEO"
  Audio/     1.mp3, 2.mp3, …  ← bắt buộc, quyết định số cảnh
  Videos/    1.mp4, 2.mp4, …  ← tùy chọn
  Images/    1.jpg, 2.jpg, …  ← ảnh dự phòng khi video lỗi/quá ngắn
  Texts/     1.txt, 2.txt, …  ← lời thoại từng cảnh
  _manifest.json              ← tùy chọn, ưu tiên cao nhất cho phụ đề

CHANNEL_FOLDER/               ← chọn ở ô "Folder KÊNH"
  Logo/                       ← file tên logo.png
  Text Claim/                 ← file tên claim.png hoặc "text claim.png"
  BGM/                        ← nhạc nền, file tên impact.* dùng làm impact
  SFX/                        ← hiệu ứng riêng của kênh
  channel-settings.json       ← tạo tự động khi bấm "Lưu cài đặt kênh"

Tên file phải là SỐ thuần (1.mp3, 02.mp4…). Số của audio quyết định
cảnh nào lấy video/ảnh nào.


QUY TRÌNH

1. Tổng quan → chọn Folder VIDEO, Folder KÊNH, Folder CapCut Drafts,
   đặt tên project và chọn khung hình 16:9 hay 9:16.
2. Cài đặt → Nhạc nền: đánh dấu bài nào là Intro, bài nào phát nền.
3. Cài đặt → Hiệu ứng SFX: chọn off / placed / muted cho từng file.
4. Cài đặt → Phụ đề: chọn nguồn lời thoại, kiểu chữ và bóng đổ.
5. Cài đặt → Nâng cao: chỉnh khoảng nghỉ, âm lượng, vị trí logo.
6. Bấm KIỂM TRA → mở Cài đặt → Cảnh quay để soát từng cảnh.
7. Khi không còn cảnh lỗi, bấm TẠO PROJECT để ghi draft cho CapCut.
8. Muốn có luôn file mp4 thì sang trang Render video.


KHOẢNG NGHỈ GIỮA CÁC CẢNH  (Cài đặt → Nâng cao)

Mặc định 0.40 giây. Sau mỗi cảnh tool chèn một quãng lặng để các câu
thoại không dính liền nhau nghe như máy đọc.

Trong quãng lặng đó HÌNH VẪN CHẠY TIẾP: hình/video của cảnh vừa rồi được
kéo dài ra cho đủ, nên không bao giờ bị đen màn.

Lưu ý: khoảng nghỉ làm mỗi cảnh dài thêm, nên một video vốn vừa khít có
thể phải làm chậm hơn một chút, hoặc chuyển sang dùng ảnh. Đặt về 0.00
là quay lại đúng cách dựng của các bản trước.


RENDER VIDEO  (trang Render video)

Engine ffmpeg  — tool tự ghép video, không cần mở CapCut, chạy được hàng
                 loạt, có phần trăm và thời gian còn lại thật. Hình gần
                 giống CapCut nhưng hiệu ứng chuyển cảnh và kiểu chữ là
                 bản mô phỏng, không giống 100%.
Engine CapCut  — nhờ chính CapCut bấm Export nên giống 100%, nhưng CHỈ
                 chạy trên Windows và không được đụng chuột trong lúc chạy.

                 Tool tự tìm CapCut.exe, TỰ ĐÓNG CapCut nếu đang mở rồi mở
                 lại — bắt buộc phải vậy thì CapCut mới thấy draft vừa tạo.
                 Nếu bạn đang sửa dở project khác trong CapCut thì nhớ lưu
                 trước khi bấm render.

                 Không chạy được thì bấm "Chẩn đoán CapCut" ở trang Render:
                 tool liệt kê mọi cửa sổ đang mở và chép vào clipboard để
                 bạn gửi đi nhờ sửa.

Render hàng loạt: bấm "Thêm nhiều folder…" rồi chọn thư mục CHA chứa
nhiều folder VIDEO. Mỗi thư mục con có Audio/ sẽ thành một việc trong
hàng đợi, dùng chung cài đặt hiện tại.


CÁCH TOOL CHỌN CHẾ ĐỘ CHO MỖI CẢNH

Cắt    — video dài hơn hoặc bằng giọng đọc + nghỉ → cắt bớt phần thừa.
Chậm   — video ngắn hơn nhưng vẫn ≥ "Tốc độ chậm tối thiểu" → làm chậm.
Ảnh    — video quá ngắn hoặc lỗi → dùng ảnh cùng số + hiệu ứng Ken Burns.
Nhanh  — khi tắt "Cắt video", video dài sẽ bị tăng tốc cho vừa giọng đọc.


HIỆU ỨNG ẢNH (ô "Hiệu ứng ảnh" ở trang Tổng quan)

Chỉ áp dụng cho cảnh dùng ẢNH TĨNH, không ảnh hưởng cảnh dùng video.

Ngẫu nhiên   — mỗi cảnh bốc một hiệu ứng bất kỳ, nhưng không bao giờ
               trùng với cảnh ngay trước đó.
Luân phiên   — chạy vòng lần lượt qua đủ 8 hiệu ứng theo thứ tự.
Một hiệu ứng — chọn đích danh thì mọi cảnh ảnh đều dùng hiệu ứng đó.
Tắt hiệu ứng — ảnh đứng yên hoàn toàn.

Các hiệu ứng có trượt đều được phóng nhẹ 1.12 lần trong suốt cảnh, để ảnh
luôn dư viền mà trượt — không bị lộ mép đen ở rìa khung hình.


PHỤ ĐỀ

Bóng đổ mặc định BẬT với độ mờ 90%, đổ chéo xuống phải. Tool ghi bóng
theo cả hai cách lưu của CapCut nên bản CapCut nào cũng hiện được.


LƯU Ý

• Nên đóng CapCut trong lúc tool ghi draft để tránh hai tiến trình
  cùng sửa metadata. Tool sẽ cảnh báo nếu phát hiện CapCut đang chạy.
• root_meta_info.json luôn được sao lưu trước khi tool ghi đè.
• Bản render bằng ffmpeg là bản dựng lại, không phải bản CapCut xuất ra.
• Tool kiểm tra bản mới trên GitHub và chỉ cài khi mã SHA-256 khớp.
"""


def build_guide(app):
    page = app.pages["guide"]
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    th = app.theme
    card = Card(page, th, padding=16, accent="guide")
    card.grid_in(row=0, column=0, sticky="nsew")
    wrap = ttk.Frame(card, style="Surface.TFrame")
    wrap.pack(fill="both", expand=True)
    c = th.c
    txt = tk.Text(wrap, wrap="word", bd=0, highlightthickness=0, bg=c["surface"],
                  fg=c["text_dim"], font=th.f_mono, padx=18, pady=16,
                  selectbackground=c["select_bg"])
    sb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    txt.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    txt.insert("1.0", GUIDE)
    txt.tag_configure("head", foreground=c["text"], font=th.f_bold)
    for i, line in enumerate(GUIDE.splitlines(), start=1):
        if line and line == line.upper() and not line.startswith((" ", "•")) and len(line) < 60:
            txt.tag_add("head", f"{i}.0", f"{i}.end")
    txt.configure(state="disabled")
    th.on_change(lambda cc: (txt.configure(bg=cc["surface"], fg=cc["text_dim"],
                                           selectbackground=cc["select_bg"]),
                             txt.tag_configure("head", foreground=cc["text"])))
