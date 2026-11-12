"""0.5.9: intro dạng ảnh (có số giây) và video quảng cáo chèn sau cảnh chọn.

Giọng đọc phải vẫn khớp cảnh: mọi thứ sau điểm chèn lùi lại đúng bằng độ dài
quảng cáo; nhạc nền / logo đang chạy ngang qua thì bị cắt đôi rồi chạy tiếp.
"""
from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from capcut_draft_studio import config, inserts
from capcut_draft_studio.inserts import Break, TimeMap, envelope_keyframes, parse_scene_list
from capcut_draft_studio.models import Settings

# --------------------------------------------------------------------------- #
# phần thuần
# --------------------------------------------------------------------------- #


def test_parse_scene_list():
    assert parse_scene_list("") == []
    assert parse_scene_list(None) == []
    assert parse_scene_list("5") == [5]
    assert parse_scene_list(" 12, 5;7  5 ") == [5, 7, 12]
    assert parse_scene_list(3) == [3]
    for bad in ("a", "5,x", "0", "-2", "1.5"):
        with pytest.raises(ValueError):
            parse_scene_list(bad)


def test_timemap_start_end_split():
    tm = TimeMap([Break(10.0, 3.0, 2), Break(20.0, 3.0, 4)])
    assert tm.extra == 6.0
    assert tm.start(0) == 0 and tm.end(0) == 0
    assert tm.start(10.0) == 13.0          # bắt đầu đúng điểm chèn → sau quảng cáo
    assert tm.end(10.0) == 10.0            # kết thúc đúng điểm chèn → trước quảng cáo
    assert tm.start(15.0) == 18.0
    assert tm.start(20.0) == 26.0
    assert [(t, b.after_scene) for t, b in tm.timeline_breaks()] == [(10.0, 2), (23.0, 4)]
    # một đoạn chạy ngang cả hai điểm chèn bị cắt làm ba, nối tiếp nguồn liên tục
    pcs = tm.split(5.0, 20.0)
    assert [tuple(round(x, 6) for x in p) for p in pcs] == [
        (5.0, 0.0, 5.0), (13.0, 5.0, 10.0), (26.0, 15.0, 5.0)]
    # đoạn kết thúc đúng điểm chèn thì không bị cắt
    assert tm.split(2.0, 8.0) == [inserts.Piece(2.0, 0.0, 8.0)]
    # mẩu vụn < MIN_PIECE bị bỏ
    assert len(tm.split(9.99, 5.0)) == 1
    assert not TimeMap([]) and TimeMap([]).split(1, 2) == [inserts.Piece(1, 0, 2)]


def test_envelope_keyframes_unsplit_is_unchanged_and_split_is_continuous():
    pts = [(0.0, 1.0), (12.0, 1.0), (13.0, 0.5)]
    assert envelope_keyframes(pts, 0.0, 40.0) == pts
    a = envelope_keyframes(pts, 0.0, 12.5)
    b = envelope_keyframes(pts, 12.5, 27.5)
    assert a[-1] == (12.5, pytest.approx(0.75))
    assert b[0] == (0.0, pytest.approx(0.75))
    assert b[1] == (pytest.approx(0.5), 0.5)
    assert envelope_keyframes(pts, 20.0, 5.0) == [(0.0, 0.5)]
    assert envelope_keyframes([], 0, 5) == []


def test_plan_breaks_reports_every_missing_scene():
    class P:
        def __init__(self, n, end):
            self.number, self.end = n, end
    plan = [P(1, 3.0), P(2, 6.0), P(3, 9.0)]
    assert inserts.plan_breaks(plan, [2], 4.0) == [Break(6.0, 4.0, 2)]
    with pytest.raises(ValueError, match="7, 9"):
        inserts.plan_breaks(plan, [2, 7, 9], 4.0)


def test_settings_helpers_and_persisted_keys(tmp_path):
    img = tmp_path / "intro.png"
    img.write_bytes(b"x")
    ad = tmp_path / "ad.mp4"
    ad.write_bytes(b"x")
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="t",
                 capcut_drafts=tmp_path, intro_path=img, ad_path=ad, ad_after="4, 2")
    assert not s.intro_is_image() and s.ad_file() is None and s.ad_scenes() == []
    s.enable_intro = s.enable_ad = True
    assert s.intro_is_image() and s.ad_scenes() == [2, 4]
    assert s.intro_img_dur == 5.0
    for key in ("intro_img_dur", "enable_ad", "ad_path", "ad_after"):
        assert key in config.DEFAULT_CHANNEL_KEYS


# --------------------------------------------------------------------------- #
# dựng draft thật
# --------------------------------------------------------------------------- #

def _wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))


def _real_pycapcut(monkeypatch):
    pytest.importorskip("pycapcut", reason="cần pycapcut để dựng draft thật")
    fake = sys.modules.get("pycapcut")
    if fake is not None and getattr(fake, "__file__", None) is None:
        monkeypatch.delitem(sys.modules, "pycapcut")
        importlib.import_module("pycapcut")


def _mp4(path: Path, seconds: float) -> Path:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("cần ffmpeg để tạo video quảng cáo mẫu")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=s=160x90:r=30:d={seconds}", "-f", "lavfi", "-i",
                    f"sine=f=440:d={seconds}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def _project(tmp_path: Path, n: int = 4, sec: float = 3.0):
    Image = pytest.importorskip("PIL.Image")
    for i in range(1, n + 1):
        _wav(tmp_path / "Audio" / f"{i}.wav", sec)
        (tmp_path / "Images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 36)).save(tmp_path / "Images" / f"{i}.png")
        (tmp_path / "Texts").mkdir(exist_ok=True)
        (tmp_path / "Texts" / f"{i}.txt").write_text(f"Cau so {i} day.", encoding="utf-8")
    _wav(tmp_path / "CH" / "BGM" / "1.wav", 60)
    (tmp_path / "CH" / "Logo").mkdir(parents=True)
    Image.new("RGB", (20, 20), "white").save(tmp_path / "CH" / "Logo" / "logo.png")
    Image.new("RGB", (64, 36), "red").save(tmp_path / "intro.png")
    (tmp_path / "drafts").mkdir()
    return Image


def _segs(track):
    return sorted(((x["target_timerange"]["start"] / 1e6,
                    x["target_timerange"]["duration"] / 1e6, x) for x in track["segments"]),
                  key=lambda t: t[0])


def test_draft_with_image_intro_and_ad_keeps_voice_on_its_scene(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _project(tmp_path)
    ad = _mp4(tmp_path / "ad.mp4", 3.0)
    from capcut_draft_studio.capcut_engine import build, clip_len
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 scene_gap=0.4, gap_mode="fixed", enable_claim=False,
                 enable_intro=True, intro_path=tmp_path / "intro.png", intro_img_dur=2.0,
                 enable_ad=True, ad_path=ad, ad_after="2")
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    ad_len = clip_len(ad, "quảng cáo")
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    tracks = {t["name"]: t for t in d["tracks"]}
    off = 2.0
    ad_at = off + plan[1].end
    # TOÀN BỘ chuỗi bắt đầu của giọng đọc, không chỉ một cảnh
    expect = [off + p.start + (ad_len if p.number > 2 else 0.0) for p in plan]
    voice = [st for st, _, _ in _segs(tracks["voice"])]
    assert voice == pytest.approx(expect, abs=1e-3)
    # hình: intro ảnh → cảnh 1, 2 → quảng cáo → cảnh 3, 4, nối liền không hở không chồng
    main = _segs(tracks["main"])
    assert [round(st, 3) for st, _, _ in main] == pytest.approx(
        [0.0, expect[0], expect[1], ad_at, expect[2], expect[3]], abs=1e-3)
    assert main[0][1] == pytest.approx(off, abs=1e-3)
    assert main[3][1] == pytest.approx(ad_len, abs=1e-3)
    for (s0, d0, _), (s1, _, _) in zip(main, main[1:]):
        assert s0 + d0 == pytest.approx(s1, abs=2e-3)
    # mỗi cảnh: hình bắt đầu cùng lúc với giọng đọc
    assert [main[i][0] for i in (1, 2, 4, 5)] == pytest.approx(voice, abs=1e-3)
    # cảnh 2 (ngay trước quảng cáo) không có chuyển cảnh, cảnh 1 và 3 thì có
    trans_ids = {m["id"] for m in d["materials"].get("transitions", [])}
    has_trans = [bool(trans_ids & set(x["extra_material_refs"])) for _, _, x in main]
    assert has_trans == [False, True, False, False, True, False]
    # logo không phủ lên quảng cáo: 2 mẩu, nối nhau qua lỗ quảng cáo
    logo = _segs(tracks["logo"])
    assert len(logo) == 2
    assert logo[0][0] == pytest.approx(off, abs=1e-3)
    assert logo[0][0] + logo[0][1] == pytest.approx(ad_at, abs=1e-3)
    assert logo[1][0] == pytest.approx(ad_at + ad_len, abs=1e-3)
    # nhạc nền: im trong lúc quảng cáo, phần sau đọc tiếp đúng chỗ đã dừng
    bgm = [x for n, t in tracks.items() if n.startswith("bgm") for x in _segs(t)]
    for st, du, _ in bgm:
        assert st + du <= ad_at + 1e-3 or st >= ad_at + ad_len - 1e-3
    before = [x for x in bgm if x[0] < ad_at]
    after = [x for x in bgm if x[0] >= ad_at]
    assert before and after
    cut_before = max(before, key=lambda x: x[0] + x[1])
    cut_after = min(after, key=lambda x: x[0])
    assert cut_after[0] == pytest.approx(ad_at + ad_len, abs=1e-3)
    src = lambda x: x[2]["source_timerange"]["start"] / 1e6
    assert src(cut_after) == pytest.approx(src(cut_before) + cut_before[1], abs=2e-3)
    end_all = off + plan[-1].end + ad_len
    assert max(st + du for st, du, _ in bgm) == pytest.approx(end_all, abs=1e-3)
    # phụ đề lùi theo cảnh: câu của cảnh 3 bắt đầu đúng lúc giọng cảnh 3
    srt = (tmp_path / "_capcut_draft_studio" / "subtitles.srt").read_text(encoding="utf-8")
    starts = [_ts(m) for m in re.findall(r"^(\S+) -->", srt, re.M)]
    assert starts == pytest.approx(expect, abs=2e-3)


def _ts(raw: str) -> float:
    h, m, rest = raw.split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def test_draft_ad_after_last_scene_goes_before_outro(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=2)
    ad = _mp4(tmp_path / "ad.mp4", 2.0)
    outro = _mp4(tmp_path / "outro.mp4", 1.5)
    from capcut_draft_studio.capcut_engine import build, clip_len
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_subtitles=False, enable_bgm=False, enable_claim=False,
                 enable_ad=True, ad_path=ad, ad_after="2",
                 enable_outro=True, outro_path=outro)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    main = _segs({t["name"]: t for t in d["tracks"]}["main"])
    end = plan[-1].end
    ad_len = clip_len(ad, "quảng cáo")
    assert [st for st, _, _ in main] == pytest.approx([0.0, plan[1].start, end, end + ad_len],
                                                      abs=1e-3)


def test_validate_flags_unknown_ad_scene(tmp_path, monkeypatch):
    _project(tmp_path, n=3)
    ad = tmp_path / "ad.mp4"
    ad.write_bytes(b"x")
    from capcut_draft_studio.media import BuildError, scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", enable_ad=True, ad_path=ad,
                 ad_after="2, 9")
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None, collect_errors=True)
    assert len(plan) == 3
    assert any("cảnh số 9" in e for e in plan.errors)
    with pytest.raises(BuildError):
        validate(s, assets, lambda m: None)
    s.ad_after = "2"
    assert validate(s, assets, lambda m: None, collect_errors=True).errors == []


# --------------------------------------------------------------------------- #
# render ffmpeg: chuỗi lệnh
# --------------------------------------------------------------------------- #

def test_render_concat_hard_cut_before_ad():
    from capcut_draft_studio import render
    from capcut_draft_studio.models import ScenePlan

    class R:
        def __init__(self, plan, hard):
            self.job = type("J", (), {"plan": plan, "duration": 0.0})()
            self.trans = 0.5
            self._hard = hard
            self.s = type("S", (), {"render_crf": 20, "render_preset": "medium"})()
            self.encoder = "libx264"
        concat_args = render.Renderer.concat_args
        _xfade_after = render.Renderer._xfade_after
        _scene_len = render.Renderer._scene_len

    plan = [ScenePlan(i + 1, Path(f"{i}.mp3"), 2.0, "IMAGE", Path(f"{i}.jpg"),
                      start=i * 2.4, gap=0.4 if i < 2 else 0.0) for i in range(3)]
    r = R(plan, {0})
    chain = r.concat_args([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")], Path("o.mp4"))
    chain = chain[chain.index("-filter_complex") + 1]
    assert "[n0][n1]concat=n=2:v=1:a=0[x1]" in chain
    assert "[x1][n2]xfade=transition=fade:duration=0.5000:offset=4.8000[vout]" in chain
    assert "settb=AVTB" in chain
    # cảnh trước quảng cáo không có đuôi chờ hoà, cảnh khác thì có
    assert r._scene_len(0, plan[0]) == pytest.approx(2.4)
    assert r._scene_len(1, plan[1]) == pytest.approx(2.9)
    assert r._scene_len(2, plan[2]) == pytest.approx(2.0)
    # không có quảng cáo: chuỗi y như trước 0.5.9
    chain = R(plan, set()).concat_args([Path("a"), Path("b"), Path("c")], Path("o"))
    chain = chain[chain.index("-filter_complex") + 1]
    assert chain == ("[0:v][1:v]xfade=transition=fade:duration=0.5000:offset=2.4000[x1];"
                     "[x1][2:v]xfade=transition=fade:duration=0.5000:offset=4.8000[vout]")
