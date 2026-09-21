"""Dựng draft thật bằng pycapcut rồi đọc lại JSON để kiểm chứng keyframe."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")

from capcut_draft_studio import animations as an          # noqa: E402
from capcut_draft_studio.capcut_engine import build       # noqa: E402
from capcut_draft_studio.media import scan_assets, validate  # noqa: E402
from capcut_draft_studio.models import Settings           # noqa: E402

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082")

SCENES = 12
QUIET = lambda _m: None  # noqa: E731


@pytest.fixture()
def project(tmp_path: Path):
    src, channel, drafts = tmp_path / "video", tmp_path / "channel", tmp_path / "drafts"
    (src / "Audio").mkdir(parents=True)
    (src / "Images").mkdir(parents=True)
    (channel / "BGM").mkdir(parents=True)
    drafts.mkdir()
    for i in range(1, SCENES + 1):
        with wave.open(str(src / "Audio" / f"{i}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\0\0" * int(8000 * 3))
        (src / "Images" / f"{i}.png").write_bytes(PNG)

    def make(anim: str) -> Path:
        s = Settings(src, channel, f"draft-{anim}", drafts, image_anim=anim,
                     enable_bgm=False, enable_subtitles=False, enable_logo=False,
                     enable_claim=False, enable_transition=False,
                     register_root_meta=False)
        assets = scan_assets(s, QUIET)
        plan = validate(s, assets, QUIET)
        return build(s, assets, plan, QUIET)

    return make


def _image_segment_keyframes(draft_path: Path) -> list[dict[str, list[float]]]:
    """Trả về, theo thứ tự cảnh, dict {tên thuộc tính: [giá trị đầu, cuối]}."""
    data = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    main = next(t for t in data["tracks"]
                if t.get("type") == "video" and t.get("name") == "main")
    segments = sorted(main["segments"], key=lambda s: s["target_timerange"]["start"])
    out = []
    for seg in segments:
        props: dict[str, list[float]] = {}
        for kf_list in seg.get("common_keyframes") or []:
            values = [kf["values"][0] for kf in kf_list["keyframe_list"]]
            props[kf_list["property_type"]] = values
        out.append(props)
    return out


def test_random_mode_writes_keyframes_on_every_image(project):
    frames = _image_segment_keyframes(project("random"))
    assert len(frames) == SCENES
    for i, props in enumerate(frames, start=1):
        assert props, f"cảnh {i} không có keyframe nào"
        for name, values in props.items():
            assert len(values) == 2, f"cảnh {i}/{name} phải có đúng 2 keyframe"


def test_random_mode_actually_varies_between_scenes(project):
    frames = _image_segment_keyframes(project("random"))
    signatures = [json.dumps(p, sort_keys=True) for p in frames]
    assert len(set(signatures)) > 1, "random mà 12 cảnh ra hiệu ứng y hệt nhau"
    for i, (a, b) in enumerate(zip(signatures, signatures[1:]), start=1):
        assert a != b, f"cảnh {i} và {i+1} trùng hiệu ứng"


def test_explicit_mode_is_identical_on_every_scene(project):
    frames = _image_segment_keyframes(project("pan_left"))
    signatures = {json.dumps(p, sort_keys=True) for p in frames}
    assert len(signatures) == 1


def test_pan_scene_carries_the_zoom_that_hides_black_borders(project):
    frames = _image_segment_keyframes(project("pan_left"))
    props = frames[0]
    # uniform_scale được pycapcut ghi ra dưới tên KFTypeScaleX
    scale = props.get("KFTypeScaleX") or props.get("UNIFORM_SCALE")
    assert scale == [an.PAN_ZOOM, an.PAN_ZOOM]
    assert props["KFTypePositionX"] == [0.10, -0.10]


def test_off_mode_writes_no_keyframes(project):
    for props in _image_segment_keyframes(project("off")):
        assert not props


def test_variety_mode_cycles_through_catalog(project):
    frames = _image_segment_keyframes(project("variety"))
    signatures = [json.dumps(p, sort_keys=True) for p in frames]
    # 12 cảnh / 8 hiệu ứng → 8 chữ ký khác nhau, cảnh 9 lặp lại cảnh 1
    assert len(set(signatures)) == len(an.EFFECT_KEYS)
    assert signatures[0] == signatures[len(an.EFFECT_KEYS)]
