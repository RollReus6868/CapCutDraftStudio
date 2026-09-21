"""Test cho preset manager, progress callback và cờ hủy."""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

from capcut_draft_studio.media import Cancelled, scan_assets, validate
from capcut_draft_studio.models import Settings
from capcut_draft_studio.presets import PresetStore, RecentStore, slugify

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082")


def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))


@pytest.fixture()
def project(tmp_path: Path) -> Settings:
    src = tmp_path / "video"
    channel = tmp_path / "channel"
    drafts = tmp_path / "drafts"
    for d in (channel / "BGM", channel / "Logo", drafts):
        d.mkdir(parents=True)
    for i in range(1, 6):
        _wav(src / "Audio" / f"{i}.wav", 2.0)
        (src / "Images").mkdir(parents=True, exist_ok=True)
        (src / "Images" / f"{i}.png").write_bytes(PNG)
    return Settings(src, channel, "demo", drafts)


# --------------------------------------------------------------------------- #
# preset
# --------------------------------------------------------------------------- #
def test_slugify_strips_unsafe_characters():
    assert slugify("Kênh: Phim / Hài?") == "Kênh-Phim-Hài"
    assert slugify("   ") == "preset"


def test_preset_roundtrip(tmp_path: Path):
    store = PresetStore(tmp_path / "presets")
    store.save("Kênh A", {"input_dir": "D:/a", "voice_vol": 2.5, "rác": 1})
    assert store.names() == ["Kênh A"]
    data = store.load("Kênh A")
    assert data["input_dir"] == "D:/a"
    assert data["voice_vol"] == 2.5
    assert "rác" not in data          # key lạ bị loại
    assert "_name" not in data        # metadata không lọt vào settings


def test_preset_rename_and_delete(tmp_path: Path):
    store = PresetStore(tmp_path / "presets")
    store.save("Cũ", {"draft_name": "x"})
    assert store.rename("Cũ", "Mới")
    assert store.names() == ["Mới"]
    assert store.delete("Mới")
    assert store.names() == []


def test_preset_empty_name_rejected(tmp_path: Path):
    store = PresetStore(tmp_path / "presets")
    with pytest.raises(ValueError):
        store.save("  ", {})


def test_recent_dedupes_and_caps(tmp_path: Path):
    rec = RecentStore(tmp_path / "recent.json")
    for i in range(20):
        rec.add(f"D:/p{i}", f"draft{i}")
    rec.add("D:/p19", "lại lần nữa")
    items = rec.items()
    assert len(items) <= 12
    assert items[0]["input_dir"] == "D:/p19"
    assert sum(1 for x in items if x["input_dir"] == "D:/p19") == 1
    rec.clear()
    assert rec.items() == []


# --------------------------------------------------------------------------- #
# progress / cancel
# --------------------------------------------------------------------------- #
def test_validate_reports_progress(project: Settings):
    seen = []
    assets = scan_assets(project, lambda _m: None)
    plan = validate(project, assets, lambda _m: None,
                    progress=lambda phase, done, total: seen.append((phase, done, total)))
    assert len(plan) == 5
    assert seen[0] == ("validate", 0, 5)
    assert seen[-1] == ("validate", 5, 5)


def test_validate_can_be_cancelled(project: Settings):
    assets = scan_assets(project, lambda _m: None)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2

    with pytest.raises(Cancelled):
        validate(project, assets, lambda _m: None, cancel=cancel)


def test_collect_errors_returns_plan_with_errors(project: Settings):
    # xóa 1 ảnh -> cảnh đó thiếu asset
    (project.input_dir / "Images" / "3.png").unlink()
    assets = scan_assets(project, lambda _m: None)
    plan = validate(project, assets, lambda _m: None, collect_errors=True)
    assert len(plan) == 4
    assert len(plan.errors) == 1
    assert "0003" in plan.errors[0]


def test_strict_mode_still_raises(project: Settings):
    from capcut_draft_studio.media import BuildError
    (project.input_dir / "Images" / "2.png").unlink()
    assets = scan_assets(project, lambda _m: None)
    with pytest.raises(BuildError):
        validate(project, assets, lambda _m: None)
