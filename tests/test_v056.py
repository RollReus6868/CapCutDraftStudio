"""0.5.6: phóng to hình/video, thứ tự nhạc nền, logo tên tuỳ ý, mức "Intro nhỏ",
nhạc nền dưới giọng đọc."""
from __future__ import annotations

import importlib
import json
import random
import sys
import wave
from pathlib import Path

import pytest

from capcut_draft_studio import config, render
from capcut_draft_studio.capcut_engine import resolve_music_roles
from capcut_draft_studio.media import first_image, natural_key
from capcut_draft_studio.models import Settings


def _s(tmp_path, **kw):
    return Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="t",
                    capcut_drafts=tmp_path, **kw)


def test_bgm_number_order_is_natural(tmp_path):
    files = [Path(f"{n}.mp3") for n in (10, 2, 1, 14, 3)]
    roles = resolve_music_roles(_s(tmp_path), files)
    assert [r[0].name for r in roles] == ["1.mp3", "2.mp3", "3.mp3", "10.mp3", "14.mp3"]
    assert roles[0][1] is True and not any(r[1] for r in roles[1:])   # bài đầu = intro


def test_bgm_random_order_shuffles(tmp_path):
    files = [Path(f"{n}.mp3") for n in range(1, 15)]
    s = _s(tmp_path, bgm_order="random")
    a = [r[0].name for r in resolve_music_roles(s, files, random.Random(1))]
    b = [r[0].name for r in resolve_music_roles(s, files, random.Random(2))]
    assert sorted(a, key=natural_key) == [f.name for f in files]
    assert a != b


def test_explicit_roles_follow_number_order(tmp_path):
    files = [Path("10.mp3"), Path("2.mp3"), Path("1.mp3")]
    s = _s(tmp_path, music_roles={"10.mp3": {"intro": False, "bg": True},
                                  "1.mp3": {"intro": True, "bg": False},
                                  "2.mp3": {"intro": False, "bg": True}})
    assert [r[0].name for r in resolve_music_roles(s, files)] == ["1.mp3", "2.mp3", "10.mp3"]


def test_logo_folder_accepts_any_image_name(tmp_path):
    (tmp_path / "Logo").mkdir()
    (tmp_path / "Logo" / "WM.png").write_bytes(b"x")
    assert first_image(tmp_path / "Logo") == tmp_path / "Logo" / "WM.png"
    assert first_image(tmp_path / "missing") is None


def test_render_zoom_scales_before_crop():
    f = render.video_scene_filter(1.0, 30, 1920, 1080, zoom=1.02)
    assert f.startswith("scale=1958:1102:") and "crop=1920:1080" in f
    assert render.video_scene_filter(1.0, 30, 1920, 1080) == \
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30"
    plain = render.kenburns_filter("off", 3.0, 30, 1920, 1080, zoom=1.02)
    assert "crop=1920:1080" in plain and "scale=1958:1102" in plain


def test_new_settings_are_persisted():
    for key in ("visual_zoom", "bgm_order"):
        assert key in config.DEFAULT_CHANNEL_KEYS


def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


def test_draft_zoom_layers_and_intro_volume(tmp_path, monkeypatch):
    pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")
    Image = pytest.importorskip("PIL.Image")
    fake = sys.modules.get("pycapcut")
    if fake is not None and getattr(fake, "__file__", None) is None:
        monkeypatch.delitem(sys.modules, "pycapcut")
        importlib.import_module("pycapcut")
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    for i in range(1, 4):
        _wav(tmp_path / "Audio" / f"{i}.wav", 12)
        (tmp_path / "Images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 36)).save(tmp_path / "Images" / f"{i}.png")
    _wav(tmp_path / "CH" / "BGM" / "1.wav", 30)
    (tmp_path / "CH" / "Logo").mkdir(parents=True)
    Image.new("RGB", (20, 10)).save(tmp_path / "CH" / "Logo" / "WM.png")
    (tmp_path / "drafts").mkdir()
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", enable_subtitles=False,
                 register_root_meta=False, visual_zoom=102.0, image_anim="off")
    assets = scan_assets(s, lambda m: None)
    assert assets.logo is not None and assets.logo.name == "WM.png"
    plan = validate(s, assets, lambda m: None)
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    tracks = {t["name"]: t for t in d["tracks"]}
    assert tracks["main"]["segments"][0]["clip"]["scale"]["x"] == pytest.approx(1.02)
    assert "logo" in tracks
    names = [t["name"] for t in d["tracks"] if t["type"] == "audio"]
    assert names.index("voice") < names.index("bgm_a"), "nhạc nền phải nằm dưới giọng đọc"
    kf = tracks["bgm_a"]["segments"][0]["common_keyframes"][0]["keyframe_list"]
    vals = [k["values"][0] for k in kf]
    assert vals[0] == pytest.approx(s.bgm_intro_vol_high)
    assert vals[-1] == pytest.approx(s.bgm_intro_vol_low)
