"""CapCut Draft Studio — giao diện chính (sidebar + trang nội dung)."""
from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .. import capcut_export, render, updater
from ..capcut_engine import build
from ..config import (detect_capcut_drafts, load_channel_settings, load_json,
                      save_channel_settings, save_json)
from ..media import BuildError, Cancelled, capcut_running, scan_assets, validate
from ..models import Settings
from ..presets import PresetStore, RecentStore
from ..subtitles import build_srt
from . import pages
from .theme import Theme
from .widgets import LogView

APP_NAME = "CapCut Draft Studio"
APP_VERSION = "0.4.1"

NAV = [
    ("dashboard", "Tổng quan"),
    ("settings", "Cài đặt"),
    ("render", "Render video"),
    ("presets", "Preset kênh"),
    ("guide", "Hướng dẫn"),
]


def app_dir() -> Path:
    """Thư mục chứa tool — hoạt động cả khi đã đóng gói PyInstaller."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # macOS: .app/Contents/MacOS/<exe> -> ghi dữ liệu cạnh file .app
        if sys.platform == "darwin" and exe.parent.name == "MacOS":
            return exe.parents[3] if len(exe.parents) >= 4 else exe.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent.parent


def bundled_dir() -> Path:
    """Thư mục chứa dữ liệu đi kèm (assets) khi chạy từ bản đóng gói."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else app_dir()


APP_SLUG = "CapCutDraftStudio"


def user_data_dir() -> Path:
    """Thư mục dữ liệu riêng của người dùng, luôn ghi được."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SLUG
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_SLUG


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """Nơi ghi cấu hình, preset, assets người dùng thêm vào.

    Bản cài đặt nằm trong `C:\\Program Files` (hoặc `/Applications`) là thư mục
    CHỈ ĐỌC với tài khoản thường — ghi vào đó là app chết ngay lúc khởi động.
    Nên: thư mục cài ghi được (bản portable, chạy từ mã nguồn) thì dùng luôn cho
    tiện; không ghi được thì chuyển sang thư mục dữ liệu riêng của người dùng.
    """
    base = app_dir()
    if _is_writable(base):
        return base
    target = user_data_dir()
    if _is_writable(target):
        return target
    # Máy bị khoá chặt tới mức cả thư mục người dùng cũng không ghi được:
    # thà dùng thư mục tạm còn hơn để app chết lúc khởi động.
    import tempfile
    fallback = Path(tempfile.gettempdir()) / APP_SLUG
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return fallback


def _ensure_assets(dst_root: Path) -> None:
    """Bung assets đi kèm ra thư mục dữ liệu trong lần chạy đầu tiên.

    Nhờ vậy người dùng có thể copy thêm SFX / style vào thư mục assets mà
    vẫn giữ được sau khi tắt app (thư mục tạm _MEIPASS bị xóa khi thoát).
    """
    src = bundled_dir() / "assets"
    dst = dst_root / "assets"
    if src == dst or not src.is_dir():
        return
    import shutil
    for sub in ("sfx-library", "sub-styles"):
        target = dst / sub
        if target.exists():
            continue
        source = src / sub
        try:
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    for name in ("icon.ico", "icon.png"):
        icon = src / name
        if icon.is_file() and not (dst / name).is_file():
            try:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(icon, dst / name)
            except OSError:
                pass


APP_DIR = app_dir()          # nơi đặt file chạy (có thể chỉ đọc)
DATA_DIR = data_dir()        # nơi ghi dữ liệu (luôn ghi được)
_ensure_assets(DATA_DIR)

CONFIG = DATA_DIR / "tool-config.json"
RECENT = DATA_DIR / "recent-projects.json"
PRESET_DIR = DATA_DIR / "presets"
SFX_LIBRARY = DATA_DIR / "assets" / "sfx-library"
SUB_STYLES = DATA_DIR / "assets" / "sub-styles"
DOWNLOADS = DATA_DIR / "updates"

STR_DEFAULTS = {
    "input_dir": "", "channel_dir": "", "draft_name": "my-video", "capcut_drafts": "",
    "fps": 30, "aspect": "landscape", "image_anim": "variety", "subtitle_source": "auto",
    "subtitle_file": "", "excel_sheet": "", "excel_script_col": "", "excel_scene_col": "",
    "subtitle_style": "", "transition_type": "叠化", "logo_path": "", "claim_path": "",
    "bgm_dir": "", "voice_vol": 3.16, "bgm_body_vol": 0.18, "crossfade_sec": 1.5,
    "logo_x": 0.949, "logo_y": -0.91, "logo_scale": 0.09, "min_speed": 0.75,
    "trans_dur": 0.47, "claim_dur": 1.1, "sub_max_words": 12,
    "bgm_intro_vol_high": 1.0, "bgm_intro_vol_low": 0.56, "bgm_intro_high_dur": 12.0,
    "bgm_intro_max_dur": 59.0,
    # --- 0.4.0 ---
    "scene_gap": 0.4, "video_vol": 1.0,
    "sub_shadow_alpha": 0.9, "sub_shadow_distance": 5.0,
    "render_engine": "ffmpeg", "render_res": "source", "render_fps": 0,
    "render_crf": 20, "render_preset": "medium", "render_codec": "h264",
    "render_hw": "auto", "render_audio_kbps": 192, "render_out_dir": "",
}

#: Ô tích ở thẻ "Chức năng" của trang Tổng quan
BOOL_LABELS = {
    "enable_subtitles": "Phụ đề", "enable_logo": "Logo", "enable_claim": "Claim",
    "enable_bgm": "Nhạc nền", "enable_voice": "Giọng đọc", "enable_transition": "Chuyển cảnh",
    "enable_slow": "Làm chậm video", "enable_cut": "Cắt video",
    "enable_impact": "Impact SFX", "register_root_meta": "Đăng ký draft vào CapCut",
}

#: Ô tích nằm ở các trang khác nhưng vẫn cần lưu lại
OTHER_BOOLS = {
    "sub_shadow": True,
    "render_burn_subs": True,
    "render_rebuild_draft": True,
    "render_open_when_done": True,
    "auto_update_check": True,
}

PERSIST_KEYS = list(STR_DEFAULTS.keys())


class App:
    # ------------------------------------------------------------------ #
    # khởi tạo
    # ------------------------------------------------------------------ #
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("1400x900")
        root.minsize(1180, 740)
        self._set_icon()

        self.q: queue.Queue = queue.Queue()
        self.running = False
        self.mode = ""                     # "" | "check" | "build" | "render"
        self.cancel_flag = threading.Event()
        self.music_rows: list[dict] = []
        self.sfx_rows: list[dict] = []
        self.last_plan: list = []
        self.last_errors: list[str] = []
        self.render_queue: list[dict] = []
        self.pages: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.current = "dashboard"
        self._update_info = None

        cfg = load_json(CONFIG, {})
        if not isinstance(cfg, dict):
            cfg = {}
        self.theme = Theme(root, cfg.get("theme", "dark"))

        self.presets = PresetStore(PRESET_DIR)
        self.recent = RecentStore(RECENT)

        if not cfg.get("capcut_drafts"):
            cfg["capcut_drafts"] = str(detect_capcut_drafts() or "")

        self.vars = {k: tk.StringVar(value=str(cfg.get(k, v)))
                     for k, v in STR_DEFAULTS.items()}
        self.boolvars = {k: tk.BooleanVar(value=bool(cfg.get(k, True)))
                         for k in BOOL_LABELS}
        self.boolvars.update({k: tk.BooleanVar(value=bool(cfg.get(k, d)))
                              for k, d in OTHER_BOOLS.items()})
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.render_pct = tk.DoubleVar(value=0.0)
        self.preset_var = tk.StringVar(value="")

        self._build_shell()
        self.show("dashboard")
        self.refresh_all_lists()
        self.root.after(100, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log(f"[OK] {APP_NAME} {APP_VERSION} đã sẵn sàng.")
        if DATA_DIR != APP_DIR:
            self.log(f"[OK] Cấu hình và preset được lưu tại: {DATA_DIR}")
        if not self.vars["capcut_drafts"].get().strip():
            self.log("[WARN] Chưa tìm thấy folder CapCut Drafts — hãy chọn thủ công ở Tổng quan.")
        if not render.ffmpeg_ready():
            self.log("[WARN] Chưa thấy ffmpeg — trang Render video sẽ báo cách cài.")
        if self.boolvars["auto_update_check"].get():
            self.root.after(1500, lambda: self.check_updates(manual=False))

    def _set_icon(self):
        """Windows dùng .ico, macOS/Linux phải dùng ảnh PNG qua iconphoto."""
        for folder in (bundled_dir() / "assets", DATA_DIR / "assets", APP_DIR / "assets"):
            ico = folder / "icon.ico"
            if os.name == "nt" and ico.is_file():
                try:
                    self.root.iconbitmap(str(ico))
                    return
                except tk.TclError:
                    pass
            png = folder / "icon.png"
            if png.is_file():
                try:
                    self._icon_image = tk.PhotoImage(file=str(png))
                    self.root.iconphoto(True, self._icon_image)
                    return
                except tk.TclError:
                    pass

    # ------------------------------------------------------------------ #
    # khung giao diện
    # ------------------------------------------------------------------ #
    def _build_shell(self):
        root = self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # ---- sidebar ----
        side = ttk.Frame(root, style="Sidebar.TFrame", width=248)
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        side.grid_propagate(False)
        side.rowconfigure(2, weight=1)

        brand = ttk.Frame(side, style="Sidebar.TFrame", padding=(20, 24, 20, 20))
        brand.grid(row=0, column=0, sticky="ew")
        ttk.Label(brand, text="CapCut", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text="Draft Studio", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"phiên bản {APP_VERSION}", style="BrandDim.TLabel").pack(
            anchor="w", pady=(5, 0))

        navbox = ttk.Frame(side, style="Sidebar.TFrame")
        navbox.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        navbox.columnconfigure(0, weight=1)
        for i, (key, label) in enumerate(NAV):
            b = ttk.Button(navbox, text=f"   {label}", style="Nav.TButton",
                           command=lambda k=key: self.show(k))
            b.grid(row=i, column=0, sticky="ew", padx=12, pady=2)
            self.nav_buttons[key] = b

        foot = ttk.Frame(side, style="Sidebar.TFrame", padding=(16, 16))
        foot.grid(row=3, column=0, sticky="ew")
        self.update_btn = ttk.Button(foot, text="   Kiểm tra cập nhật", style="Nav.TButton",
                                     command=lambda: self.check_updates(manual=True))
        self.update_btn.pack(fill="x", pady=(0, 4))
        self.theme_btn = ttk.Button(foot, text="Giao diện sáng", style="Nav.TButton",
                                    command=self.toggle_theme)
        self.theme_btn.pack(fill="x")
        self._sync_theme_btn()

        # ---- vùng nội dung ----
        body = ttk.Frame(root, padding=(26, 22, 26, 0))
        body.grid(row=0, column=1, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        head = ttk.Frame(body)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        head.columnconfigure(0, weight=1)
        self.title_lbl = ttk.Label(head, text="Tổng quan", style="H1.TLabel")
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.subtitle_lbl = ttk.Label(head, text="", style="Dim.TLabel")
        self.subtitle_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.container = ttk.Frame(body)
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        for key, _ in NAV:
            frame = ttk.Frame(self.container)
            frame.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = frame

        # ---- thanh hành động dưới cùng ----
        bar = ttk.Frame(root, padding=(26, 14, 26, 18))
        bar.grid(row=1, column=1, sticky="ew")
        bar.columnconfigure(0, weight=1)

        prog_wrap = ttk.Frame(bar)
        prog_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 22))
        prog_wrap.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(prog_wrap, style="Thin.Horizontal.TProgressbar",
                                        variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(prog_wrap, textvariable=self.status_var, style="Status.TLabel").grid(
            row=1, column=0, sticky="w", pady=(7, 0))

        self.stop_btn = ttk.Button(bar, text="Dừng", style="Danger.TButton",
                                   command=self.request_cancel, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=(0, 10))
        self.check_btn = ttk.Button(bar, text="KIỂM TRA", style="Secondary.TButton",
                                    command=lambda: self.start(False))
        self.check_btn.grid(row=0, column=2, padx=(0, 10))
        self.build_btn = ttk.Button(bar, text="TẠO PROJECT", style="Primary.TButton",
                                    command=lambda: self.start(True))
        self.build_btn.grid(row=0, column=3)

        # ---- dựng từng trang ----
        pages.build_dashboard(self)
        pages.build_settings(self)
        pages.build_render(self)
        pages.build_presets(self)
        pages.build_guide(self)

    # ------------------------------------------------------------------ #
    # điều hướng & theme
    # ------------------------------------------------------------------ #
    PAGE_SUBTITLES = {
        "dashboard": "Chọn thư mục nguồn, bật/tắt chức năng và theo dõi nhật ký.",
        "settings": "Cảnh quay, nhạc nền, SFX, phụ đề và tinh chỉnh nâng cao — gộp một chỗ.",
        "render": "Xuất file mp4 ngay trong tool, có hàng đợi và thời gian dự kiến.",
        "presets": "Lưu nhiều bộ cài đặt kênh và mở lại project gần đây.",
        "guide": "Cấu trúc thư mục chuẩn và quy trình sử dụng.",
    }

    def show(self, key: str):
        self.current = key
        self.pages[key].tkraise()
        label = dict(NAV)[key]
        self.title_lbl.configure(text=label)
        self.subtitle_lbl.configure(text=self.PAGE_SUBTITLES.get(key, ""))
        for k, btn in self.nav_buttons.items():
            btn.configure(style="NavActive.TButton" if k == key else "Nav.TButton")

    def show_settings_tab(self, key: str):
        self.show("settings")
        pages.show_setting_tab(self, key)

    def toggle_theme(self):
        self.theme.toggle()
        self._sync_theme_btn()
        self.show(self.current)
        self.persist()

    def _sync_theme_btn(self):
        dark = self.theme.c["name"] == "dark"
        self.theme_btn.configure(text="   Giao diện sáng" if dark else "   Giao diện tối")

    # ------------------------------------------------------------------ #
    # làm mới danh sách asset
    # ------------------------------------------------------------------ #
    def bgm_folder(self) -> Path:
        raw = self.vars["bgm_dir"].get().strip()
        if raw:
            return Path(raw)
        ch = self.vars["channel_dir"].get().strip()
        return Path(ch) / "BGM" if ch else Path("BGM")

    def refresh_all_lists(self):
        pages.refresh_music(self)
        pages.refresh_sfx(self)
        pages.refresh_styles(self)
        pages.refresh_overview(self)

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def current_values(self) -> dict:
        out = {k: v.get() for k, v in self.vars.items()}
        out.update({k: v.get() for k, v in self.boolvars.items()})
        return out

    def snapshot(self) -> dict:
        """current_values() + vai trò nhạc/SFX — đủ để dựng lại Settings ở luồng nền."""
        data = self.current_values()
        data["_music_roles"] = {
            r["name"]: {"intro": r["intro"].get(), "bg": r["bg"].get(),
                        "volume": _safe_float(r["volume"].get(), 1.0)}
            for r in self.music_rows
        }
        data["_sfx_roles"] = {r["name"]: r["role"].get() for r in self.sfx_rows}
        return data

    def apply_values(self, data: dict):
        for k, v in data.items():
            if k in self.vars:
                self.vars[k].set("" if v is None else str(v))
            elif k in self.boolvars:
                self.boolvars[k].set(bool(v))
        self.refresh_all_lists()

    @staticmethod
    def _num(data: dict, key: str, cast=float, default=None):
        raw = str(data.get(key, "") or "").strip().replace(",", ".")
        if not raw and default is not None:
            return default
        try:
            return cast(float(raw)) if cast is int else cast(raw)
        except ValueError:
            if default is not None:
                return default
            raise BuildError(f"Giá trị '{key}' không phải số hợp lệ: {raw!r}")

    def make_settings(self, data: dict | None = None, log=None) -> Settings:
        """Dựng Settings từ một bản chụp cấu hình (mặc định: cấu hình đang hiện).

        `log` phải được truyền vào khi gọi từ luồng nền — `self.log` đụng thẳng
        vào widget Tk nên chỉ được gọi trên luồng giao diện.
        """
        d = data if data is not None else self.snapshot()
        log = log or self.log
        ip = Path(str(d.get("input_dir", "")).strip())
        ch = Path(str(d.get("channel_dir", "")).strip())
        cap = Path(str(d.get("capcut_drafts", "")).strip())
        name = str(d.get("draft_name", "")).strip()
        if not str(d.get("input_dir", "")).strip() or not ip.is_dir():
            raise BuildError("Chọn folder VIDEO hợp lệ (chứa Audio/, Videos/, Images/).")
        if not str(d.get("channel_dir", "")).strip() or not ch.is_dir():
            raise BuildError("Chọn folder KÊNH hợp lệ (chứa Logo/, BGM/, Text Claim/).")
        if not str(d.get("capcut_drafts", "")).strip() or not cap.is_dir():
            raise BuildError("Chọn folder CapCut Drafts hợp lệ "
                             "(…/CapCut/User Data/Projects/com.lveditor.draft).")
        if not name:
            raise BuildError("Nhập tên project CapCut.")

        width, height = (1080, 1920) if d.get("aspect") == "portrait" else (1920, 1080)
        kw = dict(load_channel_settings(ch, log))
        kw.update(
            width=width, height=height, fps=self._num(d, "fps", int, 30),
            image_anim=d.get("image_anim", "variety"),
            subtitle_source=d.get("subtitle_source", "auto"),
            subtitle_style=d.get("subtitle_style", ""),
            excel_sheet=d.get("excel_sheet", ""),
            excel_script_col=d.get("excel_script_col", ""),
            excel_scene_col=d.get("excel_scene_col", ""),
            transition_type=d.get("transition_type", "叠化"),
            voice_vol=self._num(d, "voice_vol"), bgm_body_vol=self._num(d, "bgm_body_vol"),
            crossfade_sec=self._num(d, "crossfade_sec"), min_speed=self._num(d, "min_speed"),
            trans_dur=self._num(d, "trans_dur"), claim_dur=self._num(d, "claim_dur"),
            sub_max_words=self._num(d, "sub_max_words", int, 12),
            bgm_intro_vol_high=self._num(d, "bgm_intro_vol_high"),
            bgm_intro_vol_low=self._num(d, "bgm_intro_vol_low"),
            bgm_intro_high_dur=self._num(d, "bgm_intro_high_dur"),
            bgm_intro_max_dur=self._num(d, "bgm_intro_max_dur"),
            logo_x=self._num(d, "logo_x"), logo_y=self._num(d, "logo_y"),
            logo_scale=self._num(d, "logo_scale"),
            # --- 0.4.0 ---
            scene_gap=max(0.0, self._num(d, "scene_gap", float, 0.0)),
            video_vol=max(0.0, self._num(d, "video_vol", float, 1.0)),
            sub_shadow=bool(d.get("sub_shadow", True)),
            sub_shadow_alpha=self._num(d, "sub_shadow_alpha", float, 0.9),
            sub_shadow_distance=self._num(d, "sub_shadow_distance", float, 5.0),
            render_engine=d.get("render_engine", "ffmpeg"),
            render_res=str(d.get("render_res", "source")),
            render_fps=self._num(d, "render_fps", int, 0),
            render_crf=self._num(d, "render_crf", int, 20),
            render_preset=str(d.get("render_preset", "medium")),
            render_codec=str(d.get("render_codec", "h264")),
            render_hw=str(d.get("render_hw", "auto")),
            render_audio_kbps=self._num(d, "render_audio_kbps", int, 192),
            render_burn_subs=bool(d.get("render_burn_subs", True)),
        )
        for k in BOOL_LABELS:
            kw[k] = bool(d.get(k, True))
        kw["music_roles"] = dict(d.get("_music_roles") or {})
        kw["sfx_roles"] = dict(d.get("_sfx_roles") or {})
        out_dir = str(d.get("render_out_dir", "") or "").strip()
        kw["render_out_dir"] = Path(out_dir) if out_dir else None

        def opt(key):
            raw = str(d.get(key, "") or "").strip()
            return Path(raw) if raw else None

        return Settings(ip, ch, name, cap, SFX_LIBRARY, SUB_STYLES,
                        opt("logo_path"), opt("claim_path"), opt("bgm_dir"),
                        opt("subtitle_file"), **kw)

    def persist(self):
        data = {k: self.vars[k].get() for k in PERSIST_KEYS}
        data.update({k: v.get() for k, v in self.boolvars.items()})
        data["theme"] = self.theme.c["name"]
        save_json(CONFIG, data)

    def save_channel(self):
        try:
            s = self.make_settings()
            save_channel_settings(s.channel_dir, s.jsonable(), self.log)
            self.persist()
            self.set_status("Đã lưu cài đặt kênh")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    # ------------------------------------------------------------------ #
    # tạo draft
    # ------------------------------------------------------------------ #
    def start(self, do_build: bool):
        if self.running:
            return
        try:
            s = self.make_settings()
        except Exception as e:
            messagebox.showerror("Thiếu thông tin", str(e))
            self.show("dashboard")
            return
        if do_build and capcut_running() and not messagebox.askyesno(
                "CapCut đang chạy",
                "CapCut đang mở. Ghi metadata khi CapCut đang chạy có thể gây xung đột.\n\n"
                "Vẫn tiếp tục?"):
            return

        self._begin("build" if do_build else "check")
        self.set_status("Đang quét thư mục…")
        self.log("")
        self.log("[BUILD] ───── " + ("TẠO PROJECT" if do_build else "KIỂM TRA") + " ─────")
        threading.Thread(target=self.worker, args=(s, do_build), daemon=True).start()

    def _begin(self, mode: str):
        self.running = True
        self.mode = mode
        self.cancel_flag.clear()
        self.persist()
        self.set_busy(True)
        self.progress.configure(style="Thin.Horizontal.TProgressbar")
        self.progress_var.set(0)

    def request_cancel(self):
        if self.running:
            self.cancel_flag.set()
            self.set_status("Đang dừng…")
            self.log("[WARN] Đã yêu cầu dừng, đang kết thúc bước hiện tại…")

    def worker(self, s: Settings, do_build: bool):
        put = self.q.put
        log = lambda m: put(("log", m))
        prog = lambda phase, done, total: put(("progress", (phase, done, total)))
        cancel = self.cancel_flag.is_set
        try:
            assets = scan_assets(s, log)
            put(("assets", assets))
            plan = validate(s, assets, log, progress=prog, cancel=cancel,
                            collect_errors=not do_build)
            put(("scenes", (list(plan), list(getattr(plan, "errors", [])))))
            if do_build:
                path = build(s, assets, plan, log, progress=prog, cancel=cancel)
                self.recent.add(str(s.input_dir), s.draft_name, str(s.channel_dir))
                put(("done", (f"Đã tạo draft CapCut:\n\n{path}\n\n"
                              "Mở CapCut Desktop để chỉnh sửa tiếp, hoặc sang trang "
                              "Render video để xuất luôn file mp4."), True))
            else:
                errs = list(getattr(plan, "errors", []))
                if errs:
                    put(("done", (f"Kiểm tra xong: {len(plan)} cảnh hợp lệ, "
                                  f"{len(errs)} cảnh có vấn đề.\n\n"
                                  "Xem chi tiết ở Cài đặt → Cảnh quay."), False))
                else:
                    put(("done", (f"KIỂM TRA ĐẠT — {len(plan)} cảnh sẵn sàng.\n\n"
                                  "Bấm TẠO PROJECT để dựng draft."), True))
        except Cancelled as e:
            put(("cancelled", str(e)))
        except BuildError as e:
            put(("error", str(e)))
        except Exception:
            put(("error", traceback.format_exc()))

    # ------------------------------------------------------------------ #
    # render
    # ------------------------------------------------------------------ #
    def enqueue(self, name: str, values: dict):
        self.render_queue.append({
            "name": name, "values": dict(values), "status": "pending",
            "percent": 0.0, "eta": 0.0, "duration": 0.0, "out": "",
        })
        pages.refresh_queue(self)

    def start_render(self):
        if self.running:
            return
        if not self.render_queue:
            pages.add_current_to_queue(self)
            if not self.render_queue:
                return
        engine = self.vars["render_engine"].get()
        if engine == "capcut":
            ok, why = capcut_export.available()
            if not ok:
                messagebox.showerror("Không dùng được engine CapCut", why)
                return
        elif not render.ffmpeg_ready():
            messagebox.showerror("Thiếu ffmpeg", render.FFMPEG_HINT)
            return
        todo = [i for i in self.render_queue if i["status"] in ("pending", "error", "cancelled")]
        if not todo:
            if not messagebox.askyesno("Hàng đợi đã xong",
                                       "Mọi việc trong hàng đợi đều đã render xong.\n\n"
                                       "Render lại tất cả?"):
                return
            for item in self.render_queue:
                item.update(status="pending", percent=0.0, eta=0.0)
        self._begin("render")
        self.render_pct.set(0)
        self.set_status("Đang render…")
        self.log("")
        self.log(f"[RENDER] ───── BẮT ĐẦU RENDER ({engine}) ─────")
        threading.Thread(target=self.render_worker, args=(engine,), daemon=True).start()

    def render_worker(self, engine: str):
        put = self.q.put
        log = lambda m: put(("log", m))
        cancel = self.cancel_flag.is_set
        total = len(self.render_queue)
        ok_count = 0
        try:
            for idx, item in enumerate(self.render_queue):
                if cancel():
                    raise Cancelled("Đã dừng theo yêu cầu")
                if item["status"] == "done":
                    continue
                name = item["name"]
                put(("qstate", (idx, "running", 0.0, 0.0, "")))
                put(("rnote", f"Việc {idx + 1}/{total}: {name}"))
                try:
                    out = self._render_one(item, engine, log, cancel,
                                           lambda pct, eta, i=idx, n=name:
                                           put(("rprog", (i, n, pct, eta))))
                    item["out"] = str(out)
                    put(("qstate", (idx, "done", 100.0, 0.0, str(out))))
                    ok_count += 1
                except Cancelled:
                    put(("qstate", (idx, "cancelled", item["percent"], 0.0, "")))
                    raise
                except Exception as e:
                    log(f"[FAIL] {name}: {e}")
                    put(("qstate", (idx, "error", 0.0, 0.0, str(e)[:120])))
            put(("rdone", (f"Đã render xong {ok_count}/{total} video.", ok_count == total)))
        except Cancelled as e:
            put(("cancelled", str(e)))
        except Exception:
            put(("error", traceback.format_exc()))

    def _render_one(self, item: dict, engine: str, log, cancel, on_prog) -> Path:
        s = self.make_settings(item["values"], log=log)
        assets = scan_assets(s, log)
        plan = validate(s, assets, log, cancel=cancel)
        item["duration"] = plan[-1].end if plan else 0.0
        out = render.default_out_path(s, item["name"])

        if engine == "capcut":
            if bool(item["values"].get("render_rebuild_draft", True)):
                log(f"[RENDER] Dựng lại draft '{s.draft_name}' trước khi nhờ CapCut xuất…")
                build(s, assets, plan, log, cancel=cancel)
            on_prog(5.0, 0.0)
            return capcut_export.export(
                s.draft_name, out,
                res="" if s.render_res == "source" else str(s.render_res),
                fps=s.render_fps or s.fps, log=log)

        srt = None
        if s.enable_subtitles and s.subtitle_source != "off" and s.render_burn_subs:
            srt = out.parent / f"{out.stem}.srt"
            if not build_srt(s, plan, srt, log):
                srt = None
        job = render.RenderJob(name=item["name"], settings=s, assets=assets,
                               plan=list(plan), out_path=out, srt_path=srt)
        render.Renderer(job, log=log,
                        progress=lambda phase, pct, eta: on_prog(pct, eta),
                        cancel=cancel).run()
        return out

    # ------------------------------------------------------------------ #
    # cập nhật
    # ------------------------------------------------------------------ #
    def check_updates(self, manual: bool = False):
        if getattr(self, "_checking_update", False):
            return
        self._checking_update = True
        if manual:
            self.set_status("Đang kiểm tra bản mới…")

        def work():
            info = None
            try:
                info = updater.check(APP_VERSION)
            except Exception:
                info = None
            self.q.put(("update", (info, manual)))

        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, info, manual: bool):
        self._checking_update = False
        if info is None:
            if manual:
                self.set_status("Đang dùng bản mới nhất")
                messagebox.showinfo(
                    "Cập nhật",
                    f"Bạn đang dùng bản mới nhất ({APP_VERSION}).\n\n"
                    "Nếu vừa phát hành bản mới mà chưa thấy, hãy kiểm tra lại sau vài phút "
                    "— hoặc mở trang phát hành:\n" + updater.releases_url())
            return
        self._update_info = info
        self.log(f"[UPDATE] Có bản mới {info.version} ({info.size_mb:.1f} MB)")
        notes = (info.notes or "").strip()
        if len(notes) > 600:
            notes = notes[:600] + "…"
        if not messagebox.askyesno(
                "Có bản mới",
                f"Bản mới {info.version} đã sẵn sàng (bạn đang dùng {APP_VERSION}).\n\n"
                f"{notes}\n\nTải về và cài ngay? "
                f"({info.size_mb:.1f} MB)"):
            return
        self.set_status("Đang tải bản cập nhật…")

        def work():
            try:
                path = updater.download(info, DOWNLOADS,
                                        progress=lambda p: self.q.put(("dlprog", p)),
                                        cancel=self.cancel_flag.is_set)
                self.q.put(("updone", path))
            except Exception as e:
                self.q.put(("uperr", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ #
    # hàng đợi & trạng thái
    # ------------------------------------------------------------------ #
    PHASE_LABEL = {"validate": "Kiểm tra cảnh", "build": "Dựng timeline",
                   "subtitles": "Tạo phụ đề", "save": "Ghi draft"}

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                payload = item[1] if len(item) > 1 else None
                if kind == "log":
                    self.log(payload)
                elif kind == "progress":
                    self.on_progress(*payload)
                elif kind == "assets":
                    pages.update_asset_stats(self, payload)
                elif kind == "scenes":
                    plan, errors = payload
                    self.last_plan, self.last_errors = plan, errors
                    pages.fill_scene_table(self, plan, errors)
                    pages.update_plan_stats(self, plan, errors)
                elif kind == "qstate":
                    idx, status, pct, eta, out = payload
                    if 0 <= idx < len(self.render_queue):
                        row = self.render_queue[idx]
                        row.update(status=status, percent=pct, eta=eta)
                        if out:
                            row["out"] = out
                    pages.refresh_queue(self)
                elif kind == "rprog":
                    idx, name, pct, eta = payload
                    if 0 <= idx < len(self.render_queue):
                        self.render_queue[idx].update(percent=pct, eta=eta)
                    pages.update_render_progress(self, name, pct, eta)
                    self.progress_var.set(pct)
                    self.set_status(f"Render {name} — {pct:.0f}%")
                elif kind == "rnote":
                    self.render_note = payload
                    pages.update_render_progress(self, "", self.render_pct.get(), 0, payload)
                elif kind == "rdone":
                    message, ok = payload
                    pages.refresh_queue(self)
                    self.finish(message, ok, render_done=True)
                elif kind == "done":
                    ok = item[2] if len(item) > 2 else True
                    self.finish(payload, ok)
                elif kind == "update":
                    self._on_update(*payload)
                elif kind == "dlprog":
                    self.progress_var.set(payload)
                    self.set_status(f"Đang tải bản cập nhật… {payload:.0f}%")
                elif kind == "updone":
                    self.set_status("Đã tải xong bản cập nhật")
                    if messagebox.askyesno(
                            "Cài đặt bản mới",
                            "Đã tải xong và kiểm tra mã SHA-256 hợp lệ.\n\n"
                            "Đóng tool và chạy bộ cài ngay bây giờ?"):
                        updater.launch_installer(Path(payload))
                        self.root.after(400, self.root.destroy)
                elif kind == "uperr":
                    self._checking_update = False
                    self.set_status("Cập nhật thất bại")
                    messagebox.showerror("Cập nhật thất bại", str(payload))
                elif kind == "cancelled":
                    self.set_busy(False)
                    self.running = False
                    self.mode = ""
                    self.progress_var.set(0)
                    self.set_status("Đã dừng")
                    self.log("[WARN] Tiến trình đã dừng.")
                    pages.refresh_queue(self)
                elif kind == "error":
                    self.set_busy(False)
                    self.running = False
                    self.mode = ""
                    self.progress.configure(style="Err.Horizontal.TProgressbar")
                    self.progress_var.set(100)
                    self.set_status("Có lỗi — xem nhật ký")
                    self.log("[ERROR] " + str(payload))
                    messagebox.showerror("Lỗi", str(payload)[:1800])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def on_progress(self, phase: str, done: int, total: int):
        pct = 100.0 * done / total if total else 0.0
        self.progress_var.set(pct)
        label = self.PHASE_LABEL.get(phase, phase)
        self.set_status(f"{label} — {done}/{total}" if total > 1 else label)

    def finish(self, message: str, ok: bool, render_done: bool = False):
        was_render = self.mode == "render"
        self.running = False
        self.mode = ""
        self.set_busy(False)
        self.progress_var.set(100)
        self.progress.configure(style="Ok.Horizontal.TProgressbar" if ok
                                else "Err.Horizontal.TProgressbar")
        self.set_status("Hoàn thành" if ok else "Hoàn thành — có việc lỗi")
        pages.refresh_recent(self)
        if render_done:
            self.render_pct.set(100)
            self.render_job_lbl.configure(text=message)
            self.render_eta_lbl.configure(text="Thời gian còn lại: —")
            done_items = [i for i in self.render_queue if i["status"] == "done" and i["out"]]
            if ok and done_items and self.boolvars["render_open_when_done"].get():
                pages._open_folder(Path(done_items[-1]["out"]).parent)
        if ok:
            messagebox.showinfo("Hoàn thành", message)
        else:
            messagebox.showwarning("Hoàn thành với cảnh báo", message)
            if not was_render:
                self.show_settings_tab("scenes")

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.check_btn.configure(state=state)
        self.build_btn.configure(state=state)
        self.stop_btn.configure(state="normal" if busy else "disabled")
        if hasattr(self, "render_btn"):
            self.render_btn.configure(state=state)
            self.render_stop_btn.configure(state="normal" if busy else "disabled")

    def set_status(self, text: str):
        self.status_var.set(text)

    def log(self, message: str):
        if hasattr(self, "logview") and isinstance(self.logview, LogView):
            self.logview.append(message)

    def on_close(self):
        if self.running and not messagebox.askyesno(
                "Đang chạy", "Tiến trình chưa xong. Thoát ngay bây giờ?"):
            return
        try:
            self.persist()
        except Exception:
            pass
        self.root.destroy()


def _safe_float(raw, default=1.0) -> float:
    try:
        return float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
