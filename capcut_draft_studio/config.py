from __future__ import annotations
import json, os, sys
from pathlib import Path
from .models import Settings, LogFn

CHANNEL_SETTINGS = "channel-settings.json"
TOOL_CONFIG = "tool-config.json"

DEFAULT_CHANNEL_KEYS = {
    "width", "height", "fps", "claim_dur", "min_speed", "trans_dur", "voice_vol",
    "bgm_intro_vol_high", "bgm_intro_vol_low", "bgm_body_vol", "bgm_intro_high_dur",
    "bgm_intro_max_dur", "impact_times", "impact_vol", "logo_x", "logo_y", "logo_scale",
    "sub_max_words", "sub_target_sec", "hook_overrides", "crossfade_sec", "image_anim",
    "music_roles", "sfx_roles", "subtitle_source", "subtitle_style", "excel_script_col",
    "excel_scene_col", "excel_sheet", "transition_type", "logo_choice", "claim_choice",
    "enable_subtitles", "enable_logo", "enable_claim", "enable_bgm", "enable_impact",
    "enable_voice", "enable_transition", "enable_slow", "enable_cut", "register_root_meta",
    # --- thêm từ 0.4.0 ---
    "scene_gap", "video_vol",
    "sub_shadow", "sub_shadow_alpha", "sub_shadow_angle", "sub_shadow_distance",
    "sub_shadow_smoothing", "sub_shadow_color",
    "render_engine", "render_res", "render_fps", "render_crf", "render_preset",
    "render_codec", "render_audio_kbps", "render_burn_subs", "render_hw",
}

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def load_channel_settings(channel_dir: Path, log: LogFn = print) -> dict:
    p = Path(channel_dir) / CHANNEL_SETTINGS
    raw = load_json(p, {}) if p.is_file() else {}
    if not isinstance(raw, dict):
        log(f"[WARN] {p.name} không phải JSON object; dùng mặc định.")
        return {}
    out = {}
    for k, v in raw.items():
        if k in DEFAULT_CHANNEL_KEYS:
            out[k] = v
        else:
            log(f"[WARN] Bỏ qua key lạ trong settings: {k}")
    return out

def save_channel_settings(channel_dir: Path, updates: dict, log: LogFn = print) -> Path:
    p = Path(channel_dir) / CHANNEL_SETTINGS
    current = load_json(p, {}) if p.is_file() else {}
    if not isinstance(current, dict): current = {}
    current.update({k: v for k, v in updates.items() if k in DEFAULT_CHANNEL_KEYS})
    save_json(p, current)
    log(f"[OK] Đã lưu cài đặt kênh: {p}")
    return p

DRAFT_TAIL = ("User Data", "Projects", "com.lveditor.draft")


def _tail(base: Path, app: str) -> Path:
    return base.joinpath(app, *DRAFT_TAIL)


def detect_capcut_drafts() -> Path | None:
    """Tự tìm thư mục draft của CapCut trên Windows và macOS."""
    candidates: list[Path] = []
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", "") or "~")
        roaming = Path(os.environ.get("APPDATA", "") or "~")
        for app in ("CapCut", "JianyingPro"):
            candidates += [_tail(local, app), _tail(roaming, app)]
    elif sys.platform == "darwin":
        home = Path.home()
        movies = home / "Movies"
        # bản tải từ web
        for app in ("CapCut", "JianyingPro"):
            candidates.append(_tail(movies, app))
        # bản Mac App Store chạy trong sandbox
        for bundle in ("com.lemon.lvoverseas", "com.lemon.lvpro"):
            candidates.append(
                _tail(home / "Library" / "Containers" / bundle / "Data" / "Movies", "CapCut"))
    else:
        return None
    for p in candidates:
        try:
            if p.is_dir():
                return p
        except OSError:
            continue
    return None
