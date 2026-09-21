from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Literal

LogFn = Callable[[str], None]
Mode = Literal["CUT", "SLOW", "SPEEDUP", "IMAGE"]

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SFX_EXTS = AUDIO_EXTS
FORBIDDEN = '<>:"/\\|?*'

@dataclass
class Settings:
    input_dir: Path
    channel_dir: Path
    draft_name: str
    capcut_drafts: Path
    sfx_library_dir: Path = Path("assets/sfx-library")
    sub_styles_dir: Path = Path("assets/sub-styles")
    logo_path: Path | None = None
    claim_path: Path | None = None
    bgm_dir: Path | None = None
    subtitle_file: Path | None = None
    width: int = 1920
    height: int = 1080
    fps: int = 30
    claim_dur: float = 1.1
    min_speed: float = 0.75
    trans_dur: float = 0.47
    voice_vol: float = 3.16
    bgm_intro_vol_high: float = 1.0
    bgm_intro_vol_low: float = 0.56
    bgm_body_vol: float = 0.18
    bgm_intro_high_dur: float = 12.0
    bgm_intro_max_dur: float = 59.0
    impact_times: list[float] = field(default_factory=list)
    impact_vol: float = 1.48
    logo_x: float = 0.949
    logo_y: float = -0.91
    logo_scale: float = 0.09
    sub_max_words: int = 12
    sub_target_sec: float = 3.0
    hook_overrides: dict[str, int] = field(default_factory=dict)
    crossfade_sec: float = 1.5
    # Khoảng lặng chèn sau mỗi cảnh để hội thoại không dính liền nhau.
    # Hình của cảnh đó được kéo dài để lấp khoảng lặng (không bao giờ đen màn).
    # Đặt 0.0 để quay lại đúng hành vi các bản trước 0.4.0.
    scene_gap: float = 0.4
    video_vol: float = 1.0
    image_anim: str = "variety"
    # --- bóng đổ phụ đề (mặc định bật, độ mờ 90%) ---
    sub_shadow: bool = True
    sub_shadow_alpha: float = 0.9
    sub_shadow_angle: float = -45.0
    sub_shadow_distance: float = 5.0
    sub_shadow_smoothing: float = 0.45
    sub_shadow_color: str = "#000000"
    # --- render video ---
    render_engine: str = "ffmpeg"      # ffmpeg | capcut
    render_out_dir: Path | None = None
    render_res: str = "source"          # source | 2160 | 1440 | 1080 | 720 | 480
    render_fps: int = 0                 # 0 = dùng fps của project
    render_crf: int = 20
    render_preset: str = "medium"
    render_codec: str = "h264"          # h264 | h265
    render_audio_kbps: int = 192
    render_burn_subs: bool = True
    render_hw: str = "auto"             # auto | cpu
    music_roles: dict[str, dict] = field(default_factory=dict)
    sfx_roles: dict[str, str] = field(default_factory=dict)
    subtitle_source: str = "auto"
    subtitle_style: str = ""
    excel_script_col: str = ""
    excel_scene_col: str = ""
    excel_sheet: str = ""
    transition_type: str = "叠化"
    logo_choice: str = ""
    claim_choice: str = ""
    enable_subtitles: bool = True
    enable_logo: bool = True
    enable_claim: bool = True
    enable_bgm: bool = True
    enable_impact: bool = True
    enable_voice: bool = True
    enable_transition: bool = True
    enable_slow: bool = True
    enable_cut: bool = True
    register_root_meta: bool = True

    def jsonable(self) -> dict:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Path): d[k] = str(v)
        return d

@dataclass
class Assets:
    audios: dict[int, Path] = field(default_factory=dict)
    videos: dict[int, Path] = field(default_factory=dict)
    images: dict[int, Path] = field(default_factory=dict)
    texts: dict[int, Path] = field(default_factory=dict)
    claim: Path | None = None
    logo: Path | None = None
    bgm_files: list[Path] = field(default_factory=list)
    impact: Path | None = None
    sfx_items: list[dict] = field(default_factory=list)

@dataclass
class ScenePlan:
    number: int
    audio_path: Path
    audio_duration: float
    mode: Mode
    visual_path: Path
    video_duration: float | None = None
    speed: float = 1.0
    start: float = 0.0
    gap: float = 0.0
    """Khoảng lặng sau giọng đọc của cảnh này (cảnh cuối luôn bằng 0)."""

    @property
    def slot_duration(self) -> float:
        """Độ dài HÌNH của cảnh: giọng đọc + khoảng lặng."""
        return self.audio_duration + self.gap

    @property
    def audio_end(self) -> float:
        """Thời điểm giọng đọc kết thúc — phụ đề phải dừng ở đây."""
        return self.start + self.audio_duration

    @property
    def end(self) -> float:
        """Thời điểm cảnh (hình) kết thúc trên timeline."""
        return self.start + self.audio_duration + self.gap
