"""0.6.3: đồ họa chữ theo MỐC THẬT của từng từ trong file giọng (TTS Clone
Studio 3.3+ ghi vào MP3), hiện rõ TRƯỚC khi giọng nói tới, báo cáo khớp giọng."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from capcut_draft_studio import overlays as ov, speech
from capcut_draft_studio.models import Settings

from test_v059 import _project, _real_pycapcut, _segs  # noqa: F401
from test_v062 import _plan, _speechlike, _words, early

FF = shutil.which("ffmpeg")
need_ff = pytest.mark.skipif(not FF, reason="cần ffmpeg")


def _tag(mp3: Path, words, engine="inworld"):
    """Ghi mốc vào MP3 đúng như TTS Clone Studio 3.3 (ffmetadata, ID3v2.3, chép luồng)."""
    payload = json.dumps({"v": 1, "engine": engine, "words": words}, ensure_ascii=False,
                         separators=(",", ":"))
    esc = "".join("\\" + c if c in "=;#\\\n" else c for c in payload)
    meta = mp3.with_suffix(".meta.txt")
    meta.write_text(";FFMETADATA1\nWORD_TIMINGS=" + esc + "\n", encoding="utf-8")
    out = mp3.with_name("tagged_" + mp3.name)
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(mp3), "-i", str(meta), "-map", "0:a",
                    "-map_metadata", "1", "-c", "copy", "-id3v2_version", "3", str(out)], check=True)
    meta.unlink()
    out.replace(mp3)


def _mp3(path: Path, seconds: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=d={seconds}",
                    "-c:a", "libmp3lame", str(path)], check=True)
    return path


# --------------------------------------------------------------------------- #
# đọc mốc
# --------------------------------------------------------------------------- #
@need_ff
@pytest.mark.parametrize("words", [
    [["In", 0.1, 0.2], ["those", 0.25, 0.5], ["days.", 0.55, 0.9]],                    # ASCII → latin-1
    [["Ê-li", 0.1, 0.4], ["“Elect", 0.5, 0.9], ["of", 0.95, 1.0], ["God”", 1.05, 1.4]],  # → UTF-16
])
def test_read_timings_from_mp3_tag(tmp_path, words):
    mp3 = _mp3(tmp_path / "1.mp3", 2.0)
    assert speech.read_timings(mp3) is None
    _tag(mp3, words, "whisper")
    engine, got = speech.read_timings(mp3)
    assert engine == "whisper"
    assert [list(w) for w in got] == words


def test_read_timings_sidecar_and_garbage(tmp_path):
    a = tmp_path / "2.wav"
    a.write_bytes(b"RIFF....")
    assert speech.read_timings(a) is None
    (tmp_path / "2.words.json").write_text(json.dumps({"v": 1, "engine": "x", "words": [["a", 0, 1], "bad",
                                                                                     ["", 1, 2]]}))
    assert speech.read_timings(a) == ("x", [("a", 0.0, 1.0)])
    (tmp_path / "3.mp3").write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x10" + b"\xff" * 40)   # hỏng
    assert speech.read_timings(tmp_path / "3.mp3") is None
    assert speech.read_timings(tmp_path / "missing.mp3") is None


# --------------------------------------------------------------------------- #
# khớp lời thoại với mốc
# --------------------------------------------------------------------------- #
def test_align_takes_exact_times_and_fills_small_gaps():
    timed = [("In", 0.1, 0.2), ("1964,", 0.25, 1.0), ("the", 1.1, 1.2), ("scroll", 1.25, 1.6),
             ("was", 1.7, 1.8), ("found.", 1.85, 2.3)]
    words, cov = speech.align("In nineteen sixty-four the scroll was found.", timed)
    assert [w for w, _, _ in words] == ["in", "nineteen", "sixty", "four", "the", "scroll", "was", "found"]
    assert words[4] == ("the", 1.1, 1.2) and words[7] == ("found", 1.85, 2.3)
    # số đọc khác cách viết: chia trong đúng khoảng của "1964"
    assert words[1][1] == pytest.approx(0.25) and words[3][2] == pytest.approx(1.0)
    assert cov == pytest.approx(5 / 8)
    starts = [s for _, s, _ in words]
    assert starts == sorted(starts)


def test_align_word_missing_from_audio_sits_between_neighbours():
    timed = [("the", 0.0, 0.2), ("light", 0.3, 0.6), ("came", 2.0, 2.3)]
    words, cov = speech.align("the light suddenly came", timed)
    sud = words[2]
    assert sud[0] == "suddenly" and 0.6 <= sud[1] <= sud[2] <= 2.0
    assert cov == pytest.approx(0.75)


def test_scene_timing_prefers_exact_then_estimates(tmp_path):
    a = tmp_path / "1.wav"
    a.write_bytes(b"x")
    # không có mốc → ước lượng theo chữ (không ffmpeg)
    w, how, eng = speech.scene_timing("Alpha beta gamma.", a, 3.0, None)
    assert how == "plain" and eng == "" and len(w) == 3
    (tmp_path / "1.words.json").write_text(json.dumps(
        {"engine": "inworld", "words": [["Alpha", 1.0, 1.4], ["beta", 1.5, 1.9], ["gamma.", 2.0, 2.6]]}))
    speech._read_timings.cache_clear()
    w, how, eng = speech.scene_timing("Alpha beta gamma.", a, 3.0, None)
    assert (how, eng) == ("exact", "inworld")
    assert w[1] == ("beta", 1.5, 1.9)
    # không có lời thoại: dùng thẳng các từ trong mốc
    w, how, _ = speech.scene_timing("", a, 3.0, None)
    assert how == "exact" and [x for x, _, _ in w] == ["alpha", "beta", "gamma"]
    # lời thoại lệch hẳn file giọng (sai số cảnh) → vẫn theo mốc của file
    w, how, _ = speech.scene_timing("totally different words here", a, 3.0, None)
    assert how == "exact" and w[0] == ("alpha", 1.0, 1.4)
    # mốc vượt độ dài file bị kẹp lại
    w, _, _ = speech.scene_timing("", a, 2.2, None)
    assert w[-1][2] == pytest.approx(2.2)


# --------------------------------------------------------------------------- #
# lịch hiện + báo cáo
# --------------------------------------------------------------------------- #
def test_shown_fully_before_spoken_and_report_rows():
    plan = _plan()
    words = ov.WordMap({2: _words("first some words then the reason is strange and more")})
    words.sources[2] = ("exact", "inworld")
    items, _ = ov.parse_overlay_rows([["2", "TITLE", "The reason is strange"],
                                      ["2", "LOWER", "Not spoken at all", "", ""],
                                      ["2", "STAMP", "strange", "", "", "", "0.5"]])
    logs, rows = [], []
    pls = ov.schedule(items, plan, ov.OverlayStyle(), logs.append, words=words, report=rows)
    title = next(p for p in pls if p.frame.item.kind == "TITLE")
    spoken = plan[1].start + 2.0
    assert title.start + title.fade_in == pytest.approx(spoken - ov.SHOW_BEFORE)   # rõ trước tiếng
    by = {r.kind: r for r in rows}
    assert by["TITLE"].spoken == pytest.approx(2.0)
    assert by["TITLE"].ahead == pytest.approx(ov.SHOW_BEFORE)
    assert by["TITLE"].how.startswith("Mốc chính xác") and "inworld" in by["TITLE"].how
    assert by["LOWER"].spoken is None and "Không thấy" in by["LOWER"].how
    assert by["STAMP"].how.startswith("Đặt tay")
    assert any("MỐC CHÍNH XÁC" in m for m in logs)


def test_estimate_only_warns_how_to_get_exact():
    plan = _plan()
    words = ov.WordMap({2: _words("the reason is strange")})
    words.sources[2] = ("silence", "")
    items, _ = ov.parse_overlay_rows([["2", "TITLE", "The reason is strange"]])
    logs = []
    ov.schedule(items, plan, ov.OverlayStyle(), logs.append, words=words, report=[])
    assert any("ƯỚC LƯỢNG" in m and "TTS Clone Studio 3.3" in m for m in logs)


def test_scene_start_word_cannot_go_before_scene():
    plan = _plan()
    words = ov.WordMap({2: _words("strange things", start=0.1)})
    items, _ = ov.parse_overlay_rows([["2", "TITLE", "Strange things"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None, words=words)
    assert pls[0].start == pytest.approx(plan[1].start)


def test_list_rows_reported_once_each():
    plan = _plan(3)
    words = ov.WordMap({1: _words("there are three marks one on the face"),
                        2: _words("the second is one on the forehead and more")})
    items, _ = ov.parse_overlay_rows([["scene", "type", "text", "sub", "label", "until"],
                                      ["1", "LIST", "One on the face", "", "Marks", "3"],
                                      ["2", "LIST", "One on the forehead", "", "Marks", ""]])
    rows = []
    ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None, words=words, report=rows)
    assert [r.text for r in rows] == ["One on the face", "One on the forehead"]


def test_write_report_opens_in_excel(tmp_path):
    rows = [ov.TimingRow(3, "TITLE", "Ba dấu ấn", 2.5, 2.05, "Mốc chính xác từ file giọng (inworld)"),
            ov.TimingRow(1, "LOWER", "Ê-nóc", None, 0.35, "Không thấy")]
    p = ov.write_report(rows, tmp_path / "x" / ov.REPORT_NAME, lambda m: None)
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                        # BOM → Excel đọc đúng tiếng Việt
    lines = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert lines[0][0] == "Cảnh" and lines[1][:3] == ["1", "LOWER", "Ê-nóc"] and lines[1][3] == ""
    assert lines[2][3:6] == ["2,50", "2,05", "0,10"]


# --------------------------------------------------------------------------- #
# dựng draft thật với MP3 có mốc
# --------------------------------------------------------------------------- #
@need_ff
def test_draft_uses_exact_timings_from_mp3(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=2, sec=2.0)
    wav = tmp_path / "Audio" / "1.wav"
    _speechlike(wav, [(0.2, False), (1.8, True), (0.9, False), (2.0, True), (0.3, False)])
    mp3 = tmp_path / "Audio" / "1.mp3"
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libmp3lame", str(mp3)], check=True)
    wav.unlink()
    text = "In those days the kings ruled the land. Then the light appeared on their faces."
    # mốc "thật": câu 2 bắt đầu ở 3.37 s (khác hẳn ước lượng theo quãng lặng ~2.9 s)
    toks = text.split()
    times = [[w, round(0.2 + k * 0.2, 3), round(0.38 + k * 0.2, 3)] for k, w in enumerate(toks[:8])]
    times += [[w, round(3.37 + k * 0.2, 3), round(3.55 + k * 0.2, 3)] for k, w in enumerate(toks[8:])]
    _tag(mp3, times)
    (tmp_path / "Texts" / "1.txt").write_text(text, encoding="utf-8")
    (tmp_path / "overlay.csv").write_text('1,TITLE,"Then the light appeared on their faces"', encoding="utf-8")
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_claim=False, enable_subtitles=False, enable_bgm=False)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    logs = []
    d = json.loads((build(s, assets, plan, logs.append) / "draft_content.json").read_text(encoding="utf-8"))
    st = _segs({t["name"]: t for t in d["tracks"]}["chu_main"])[0][0]
    assert st == pytest.approx(3.37 - early("TITLE"), abs=0.002), st
    assert any("1 cảnh theo mốc chính xác" in m for m in logs)
    rep = tmp_path / "_capcut_draft_studio" / ov.REPORT_NAME
    assert rep.is_file()
    row = list(csv.reader(rep.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))[1]
    assert row[3] == "3,37" and row[5] == "0,10" and row[6].startswith("Mốc chính xác")
    # report không bị nhận nhầm là file đồ họa chữ ở lần dựng sau
    assert ov.find_overlay_file(tmp_path).name == "overlay.csv"


def test_align_edges_use_only_the_nearest_timings():
    timed = [("intro", 0.0, 0.4), ("music", 0.5, 0.9), ("b", 1.0, 1.2), ("then", 1.3, 1.5), ("light", 1.6, 2.0),
             ("x", 5.0, 6.0), ("y", 7.0, 8.0), ("z", 9.0, 10.0)]
    words, _ = speech.align("well so then light came", timed)
    assert words[0][1] >= 0.5 and words[1][2] <= 1.2          # 2 từ đầu: chỉ trong 2 mốc ngay trước "then"
    assert words[-1][0] == "came" and words[-1][2] <= 6.0     # từ cuối: chỉ trong 1 mốc ngay sau "light"
