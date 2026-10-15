"""0.5.5: bài nhạc mà độ dài cả file (General) dài hơn luồng âm thanh không được
làm pycapcut báo "超出了素材时长", và nhạc nền nằm dưới giọng đọc."""
from __future__ import annotations

import importlib
import json
import sys
import wave
from pathlib import Path

import pytest

pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")
Image = pytest.importorskip("PIL.Image")

import capcut_draft_studio.capcut_engine as eng  # noqa: E402
from capcut_draft_studio import media  # noqa: E402
from capcut_draft_studio.media import scan_assets, validate  # noqa: E402
from capcut_draft_studio.models import Settings  # noqa: E402


def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


def test_bgm_longer_on_paper_than_its_audio_stream(tmp_path, monkeypatch):
    fake = sys.modules.get("pycapcut")
    if fake is not None and getattr(fake, "__file__", None) is None:
        monkeypatch.delitem(sys.modules, "pycapcut")
        importlib.import_module("pycapcut")
    for i in range(1, 4):
        _wav(tmp_path / "Audio" / f"{i}.wav", 12)
        (tmp_path / "Images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 36)).save(tmp_path / "Images" / f"{i}.png")
    _wav(tmp_path / "CH" / "BGM" / "song.wav", 20)
    (tmp_path / "drafts").mkdir()

    real = media.media_duration_sec

    def general_longer(p):                       # như mp3 "180s" chỉ có 178.67s tiếng
        d = real(p)
        return d + 1.5 if "BGM" in str(p) else d

    monkeypatch.setattr(eng, "media_duration_sec", general_longer)
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", enable_subtitles=False,
                 register_root_meta=False)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    path = eng.build(s, assets, plan, lambda m: None)    # 0.5.4: ValueError 超出了素材时长
    content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {t["name"]: t for t in content["tracks"] if t.get("segments")}
    assert "voice" in tracks and "bgm_a" in tracks
    voice_idx = tracks["voice"]["segments"][0]["render_index"]
    for name, t in tracks.items():
        if name.startswith("bgm"):
            assert t["segments"][0]["render_index"] < voice_idx, "nhạc nền phải dưới giọng đọc"
    order = [t["name"] for t in content["tracks"]]
    assert order.index("bgm_a") < order.index("voice")
