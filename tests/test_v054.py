"""0.5.4: nhạc intro dài hơn bgm_intro_high_dur không được làm SegmentOverlap,
và tiến trình chờ cài bản cập nhật không được dùng DETACHED_PROCESS."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")
Image = pytest.importorskip("PIL.Image")

from capcut_draft_studio import updater  # noqa: E402
from capcut_draft_studio.capcut_engine import build  # noqa: E402
from capcut_draft_studio.media import scan_assets, validate  # noqa: E402
from capcut_draft_studio.models import Settings  # noqa: E402


def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


def _project(tmp_path: Path) -> Path:
    for i in range(1, 5):
        _wav(tmp_path / "Audio" / f"{i}.wav", 12)
        (tmp_path / "Images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 36), (40 * i, 80, 120)).save(tmp_path / "Images" / f"{i}.png")
    _wav(tmp_path / "CH" / "BGM" / "a_intro.wav", 40)     # dài hơn 12s giữ to
    _wav(tmp_path / "CH" / "BGM" / "b_body.wav", 20)
    (tmp_path / "drafts").mkdir()
    return tmp_path


@pytest.mark.parametrize("roles", [
    {},                                                    # mặc định: bài đầu vừa intro vừa nền
    {"a_intro.wav": {"intro": True, "bg": False}, "b_body.wav": {"intro": False, "bg": True}},
])
def test_long_intro_music_does_not_overlap(tmp_path, monkeypatch, roles):
    # test_engine_mock.py thay sys.modules["pycapcut"] bằng bản giả và không trả
    # lại — test này cần pycapcut THẬT để đọc draft_content.json.
    import importlib
    import sys
    fake = sys.modules.get("pycapcut")
    if fake is not None and getattr(fake, "__file__", None) is None:
        monkeypatch.delitem(sys.modules, "pycapcut")
        importlib.import_module("pycapcut")
    root = _project(tmp_path)
    s = Settings(input_dir=root, channel_dir=root / "CH", draft_name="bgm",
                 capcut_drafts=root / "drafts", enable_subtitles=False,
                 register_root_meta=False, music_roles=roles)
    assets = scan_assets(s, lambda m: None)
    assert assets.bgm_files, "phải thấy nhạc nền"
    plan = validate(s, assets, lambda m: None)
    path = build(s, assets, plan, lambda m: None)          # 0.5.3: SegmentOverlap
    content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))
    bgm = [t for t in content["tracks"] if t.get("name", "").startswith("bgm")]
    assert bgm
    for track in bgm:
        spans = sorted((x["target_timerange"]["start"],
                        x["target_timerange"]["start"] + x["target_timerange"]["duration"])
                       for x in track["segments"])
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert start >= end, track["name"]
        assert all(e - s >= 500_000 for s, e in spans), "không còn mẩu nhạc vụn < 0.5s"


def test_update_helper_never_uses_detached_process():
    import inspect
    src = inspect.getsource(updater._windows_deferred_launch)
    code = "\n".join(l.split("#")[0] for l in src.splitlines())
    assert "DETACHED_PROCESS" not in code
