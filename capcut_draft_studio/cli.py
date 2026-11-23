"""Chạy tool không cần giao diện (0.6.0) — dùng khi nhờ Claude dựng/sửa video từ xa
hoặc dựng hàng loạt bằng script.

    python -m capcut_draft_studio.cli check  --input D:/Video/Tap12
    python -m capcut_draft_studio.cli build  --input D:/Video/Tap12 --name Tap12
    python -m capcut_draft_studio.cli render --input D:/Video/Tap12 --name Tap12
    python -m capcut_draft_studio.cli overlay-template --input D:/Video/Tap12
    python -m capcut_draft_studio.cli overlay-preview  --input D:/Video/Tap12

Mặc định lấy ĐÚNG cấu hình đang lưu của giao diện (tool-config.json trong thư
mục dữ liệu của app: folder KÊNH, folder CapCut Drafts, âm lượng, phụ đề, đồ họa
chữ…), chỉ thay những gì truyền trên dòng lệnh. `--config` để chỉ file khác.
Mã thoát: 0 = ổn, 1 = lỗi dữ liệu (đã in lý do), 2 = sai tham số.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def _log(msg: str) -> None:
    print(msg, flush=True)


def _progress(phase, done, total):
    pass


def _gui_config_path() -> Path | None:
    try:
        from .ui.app import CONFIG
        return Path(CONFIG)
    except Exception:
        return None


def load_values(args) -> dict:
    """Cấu hình giao diện + tham số dòng lệnh → dict giống App.snapshot()."""
    cfg_path = Path(args.config) if args.config else _gui_config_path()
    # giá trị mặc định y như giao diện lúc mới cài, rồi đè bằng cấu hình đã lưu
    from .ui.app import BOOL_LABELS, OTHER_BOOLS, STR_DEFAULTS
    data: dict = {k: str(v) for k, v in STR_DEFAULTS.items()}
    data.update({k: True for k in BOOL_LABELS})
    data.update(OTHER_BOOLS)
    if cfg_path and cfg_path.is_file():
        try:
            data.update(json.loads(cfg_path.read_text(encoding="utf-8")))
            _log(f"[OK] Dùng cấu hình: {cfg_path}")
        except Exception as e:
            _log(f"[WARN] Không đọc được {cfg_path}: {e}")
    elif args.config:
        raise SystemExit(f"[FAIL] Không thấy file cấu hình {args.config}")
    for key in ("input", "channel", "drafts", "name"):
        val = getattr(args, key, None)
        if val:
            data[{"input": "input_dir", "channel": "channel_dir", "drafts": "capcut_drafts",
                  "name": "draft_name"}[key]] = str(val)
    if getattr(args, "overlay", None):
        data["overlay_file"] = str(args.overlay)
    for flag in ("no_overlays", "no_subtitles"):
        if getattr(args, flag, False):
            data["enable_overlays" if flag == "no_overlays" else "enable_subtitles"] = False
    if not data.get("draft_name") and data.get("input_dir"):
        data["draft_name"] = Path(data["input_dir"]).name
    # vai trò nhạc / SFX được lưu trong channel-settings.json của folder KÊNH
    ch = data.get("channel_dir")
    if ch and Path(ch).is_dir():
        from .config import load_channel_settings
        cs = load_channel_settings(Path(ch), lambda m: None)
        data.setdefault("_music_roles", cs.get("music_roles") or {})
        data.setdefault("_sfx_roles", cs.get("sfx_roles") or {})
    data.setdefault("_music_roles", {})
    data.setdefault("_sfx_roles", {})
    return data


def make_settings(data: dict):
    """Dựng Settings bằng CHÍNH logic của giao diện (App.make_settings) để CLI và
    giao diện cho cùng một kết quả."""
    from .ui.app import App
    fake = SimpleNamespace(_num=App._num, log=_log)
    return App.make_settings(fake, data, log=_log)


def _plan(s, collect: bool):
    from .media import scan_assets, validate
    assets = scan_assets(s, _log)
    plan = validate(s, assets, _log, _progress, collect_errors=collect)
    return assets, plan


def cmd_check(args) -> int:
    s = make_settings(load_values(args))
    _, plan = _plan(s, collect=True)
    errs = getattr(plan, "errors", [])
    _log(f"[DONE] {len(plan)} cảnh, {len(errs)} lỗi")
    return 1 if errs else 0


def cmd_build(args) -> int:
    from .capcut_engine import build
    s = make_settings(load_values(args))
    assets, plan = _plan(s, collect=False)
    build(s, assets, plan, _log, progress=_progress)
    return 0


def cmd_render(args) -> int:
    from . import render
    s = make_settings(load_values(args))
    assets, plan = _plan(s, collect=False)
    out = Path(args.out) if args.out else render.default_out_path(s, s.draft_name)
    srt = None
    if s.enable_subtitles and s.subtitle_source != "off":
        from .subtitles import build_srt
        srt = out.parent / f".{out.stem}.srt"
        if not build_srt(s, plan, srt, _log):
            srt = None
    job = render.RenderJob(s.draft_name, s, assets, plan, out, srt_path=srt)
    render.Renderer(job, log=_log).run()
    return 0


def cmd_overlay_template(args) -> int:
    from . import overlays
    dest = Path(args.input) / "overlay.xlsx"
    if dest.exists():
        _log(f"[WARN] Đã có {dest} — không ghi đè")
        return 1
    overlays.write_template(dest)
    _log(f"[OK] Đã tạo {dest}")
    return 0


def cmd_overlay_preview(args) -> int:
    from . import overlays
    from .models import Settings
    s = Settings(input_dir=Path(args.input), channel_dir=Path(args.input), draft_name="x",
                 capcut_drafts=Path(args.input),
                 overlay_file=Path(args.overlay) if args.overlay else None)
    if args.config or _gui_config_path():
        try:
            full = make_settings(load_values(args))
            s = full
        except Exception as e:
            _log(f"[WARN] Dùng kiểu chữ mặc định ({e})")
    path = overlays.overlay_file(s)
    if not path:
        _log("[FAIL] Không thấy file overlay trong folder VIDEO")
        return 1
    items, errors = overlays.load_overlays(path)
    for e in errors:
        _log(f"[FAIL] {e}")
    if errors:
        return 1
    out = Path(args.out) if args.out else Path(s.input_dir) / "_capcut_draft_studio" / "overlay-preview.jpg"
    overlays.preview_file(items, s, out)
    _log(f"[OK] {len(items)} mục → {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="capcut_draft_studio.cli",
                                 description="CapCut Draft Studio — chạy không cần giao diện")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_name=False):
        p.add_argument("--input", required=True, help="Folder VIDEO (Audio/, Images/…)")
        p.add_argument("--channel", help="Folder KÊNH (mặc định: như giao diện)")
        p.add_argument("--drafts", help="Folder CapCut Drafts (mặc định: như giao diện)")
        p.add_argument("--name", help="Tên project (mặc định: tên folder VIDEO)")
        p.add_argument("--config", help="File cấu hình khác tool-config.json")
        p.add_argument("--overlay", help="File đồ họa chữ (mặc định: tự tìm)")
        p.add_argument("--no-overlays", action="store_true", help="Tắt đồ họa chữ")
        p.add_argument("--no-subtitles", action="store_true", help="Tắt phụ đề")
        p.add_argument("--out", help="File/ảnh đầu ra (render, overlay-preview)")

    for name in ("check", "build", "render", "overlay-preview"):
        common(sub.add_parser(name))
    t = sub.add_parser("overlay-template")
    t.add_argument("--input", required=True)
    args = ap.parse_args(argv)
    fn = {"check": cmd_check, "build": cmd_build, "render": cmd_render,
          "overlay-template": cmd_overlay_template,
          "overlay-preview": cmd_overlay_preview}[args.cmd]
    from .media import BuildError
    try:
        return fn(args)
    except BuildError as e:
        _log(f"[FAIL] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
