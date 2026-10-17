"""0.5.8: mã QR đầu video, nhạc CID nằm sau điểm kết thúc video."""
from __future__ import annotations

import importlib
import json
import sys
import wave
from pathlib import Path

import pytest

from capcut_draft_studio import config
from capcut_draft_studio.models import Settings


def test_qr_file_only_when_enabled(tmp_path):
    qr = tmp_path / "qr.png"
    qr.write_bytes(b"x")
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="t",
                 capcut_drafts=tmp_path, qr_path=qr)
    assert s.qr_file() is None
    s.enable_qr = True
    assert s.qr_file() == qr
    for key in ("enable_qr", "qr_path", "qr_x", "qr_y", "qr_scale", "qr_dur"):
        assert key in config.DEFAULT_CHANNEL_KEYS


def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


def test_draft_cid_after_video_and_qr(tmp_path, monkeypatch):
    pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")
    Image = pytest.importorskip("PIL.Image")
    fake = sys.modules.get("pycapcut")
    if fake is not None and getattr(fake, "__file__", None) is None:
        monkeypatch.delitem(sys.modules, "pycapcut")
        importlib.import_module("pycapcut")
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    for i in range(1, 3):
        _wav(tmp_path / "Audio" / f"{i}.wav", 6)
        (tmp_path / "Images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 36)).save(tmp_path / "Images" / f"{i}.png")
    _wav(tmp_path / "CH" / "BGM" / "1.wav", 30)
    _wav(tmp_path / "CID" / "song.wav", 9)
    Image.new("RGB", (30, 30), "white").save(tmp_path / "qr.png")
    (tmp_path / "drafts").mkdir()
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", enable_subtitles=False,
                 register_root_meta=False, enable_cid=True, cid_dir=tmp_path / "CID",
                 cid_vol=0.7, enable_qr=True, qr_path=tmp_path / "qr.png", qr_dur=4.0)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    tracks = {t["name"]: t for t in d["tracks"]}
    end = plan[-1].end
    cid = tracks["cid"]["segments"][0]
    assert cid["target_timerange"]["start"] / 1e6 == pytest.approx(end, abs=1e-3)
    assert cid["volume"] == pytest.approx(0.7)
    bgm_end = max((x["target_timerange"]["start"] + x["target_timerange"]["duration"]) / 1e6
                  for n, t in tracks.items() if n.startswith("bgm") for x in t["segments"])
    assert bgm_end == pytest.approx(end, abs=1e-3)      # nhạc nền chạy hết video như thường
    qr = tracks["qr"]["segments"][0]
    assert qr["target_timerange"]["start"] == 0
    assert qr["target_timerange"]["duration"] / 1e6 == pytest.approx(4.0, abs=1e-3)
    assert qr["clip"]["transform"]["x"] == pytest.approx(0.84)
    assert qr["clip"]["transform"]["y"] == pytest.approx(-0.74)
