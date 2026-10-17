"""0.5.7: nhạc CID cuối video, độ dài video intro theo luồng hình."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from capcut_draft_studio import config
from capcut_draft_studio import capcut_engine as eng
from capcut_draft_studio.media import BuildError
from capcut_draft_studio.models import Settings


def _s(tmp_path, **kw):
    return Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="t",
                    capcut_drafts=tmp_path, **kw)


def test_cid_window_ends_with_last_scene():
    assert eng.cid_window(100.0, 0.0, 30.0) == (70.0, 30.0)
    assert eng.cid_window(100.0, 20.0, 30.0) == (70.0, 30.0)     # sau video intro
    assert eng.cid_window(50.0, 20.0, 45.0) == (20.0, 30.0)      # bài dài hơn nội dung


def test_pick_cid_random_from_folder(tmp_path):
    d = tmp_path / "CID"
    d.mkdir()
    for n in ("a.mp3", "b.mp3", "c.wav", "note.txt"):
        (d / n).write_bytes(b"x")
    s = _s(tmp_path, enable_cid=True, cid_dir=d)
    picks = {eng.pick_cid(s, random.Random(i)).name for i in range(30)}
    assert picks <= {"a.mp3", "b.mp3", "c.wav"} and len(picks) > 1
    assert eng.pick_cid(_s(tmp_path, cid_dir=d)) is None          # chưa bật
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BuildError):
        eng.pick_cid(_s(tmp_path, enable_cid=True, cid_dir=empty))


def test_intro_length_uses_video_stream(monkeypatch, tmp_path):
    f = tmp_path / "intro.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(eng, "media_duration_sec", lambda p: 26.053)

    class Mat:
        duration = 26_050_000

    class CC:
        @staticmethod
        def VideoMaterial(p):
            return Mat()

    monkeypatch.setattr(eng, "_cc", lambda: CC)
    eng._VIDEO_MATERIALS.clear()
    assert eng.clip_len(f, "intro") == pytest.approx(26.05, abs=1e-5)
    assert eng.clip_len(f, "intro") <= 26.05


def test_cid_settings_persisted():
    for key in ("enable_cid", "cid_dir", "cid_vol"):
        assert key in config.DEFAULT_CHANNEL_KEYS
