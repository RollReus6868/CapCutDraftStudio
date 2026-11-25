"""0.6.2: đồ họa chữ hiện đúng lúc giọng đọc nói tới (khớp theo lời thoại +
quãng lặng trong file giọng)."""
from __future__ import annotations

import json
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from capcut_draft_studio import config, overlays as ov, speech
from capcut_draft_studio.models import ScenePlan, Settings

from test_v059 import _project, _real_pycapcut, _segs  # noqa: F401


# --------------------------------------------------------------------------- #
# so khớp chữ
# --------------------------------------------------------------------------- #
def test_num_words_and_variants():
    assert speech.num_words(11) == [["eleven"]]
    assert speech.num_words(72) == [["seventy", "two"]]
    assert ["nineteen", "sixty", "four"] in speech.num_words(1964)
    assert ["nineteen", "fifty", "two"] in speech.num_words(1952)
    assert speech.num_words(1000000) == []
    v = speech.item_variants("~11 copies")
    assert ["11", "copies"] in v and ["eleven", "copies"] in v
    assert speech.norm_words("Noah’s father, “Elect of God”—seventy-two!") == \
        ["noah", "father", "elect", "of", "god", "seventy", "two"]


def test_locate_exact_partial_and_none():
    seq = "and then it gives the reason and the reason is strange".split()
    assert speech.locate("the reason is strange".split(), seq) == (7, 0, 4)
    # khớp một phần: chữ trên hình thêm từ không được đọc
    assert speech.locate("why the reason is strange".split(), seq) == (7, 1, 4)
    assert speech.locate("completely different words".split(), seq) is None
    # một từ ngắn không đủ tin
    assert speech.locate("the".split(), seq) is None
    assert speech.locate("strange".split(), seq) == (10, 0, 1)


# --------------------------------------------------------------------------- #
# thời gian từng từ
# --------------------------------------------------------------------------- #
def test_word_times_skip_silences():
    text = "One two three. Four five six."
    # 0–0.2 lặng, nói 0.2–1.7, lặng 1.7–2.5 (chấm câu), nói 2.5–4.0, lặng tới 4.3
    quiet = [(0.0, 0.2), (1.7, 2.5), (4.0, 4.3)]
    wt = speech.word_times(text, 4.3, quiet)
    assert [w for w, _, _ in wt] == ["one", "two", "three", "four", "five", "six"]
    assert wt[0][1] == pytest.approx(0.2, abs=1e-6)
    four = wt[3][1]
    assert 2.45 <= four <= 2.6, four          # câu sau quãng lặng bắt đầu đúng chỗ
    starts = [s for _, s, _ in wt]
    assert starts == sorted(starts)
    assert wt[-1][2] == pytest.approx(4.0, abs=1e-6)


def test_word_times_without_ffmpeg_uses_punctuation():
    wt = speech.word_times("Alpha beta. Gamma delta", 4.0, None)
    gap = wt[2][1] - wt[1][2]
    assert gap > 0.4                         # chỗ chấm câu được dành thời gian nghỉ


# --------------------------------------------------------------------------- #
# lập lịch theo giọng
# --------------------------------------------------------------------------- #
def _plan(n=3, dur=6.0, gap=0.4):
    out, t = [], 0.0
    for i in range(1, n + 1):
        g = gap if i < n else 0.0
        out.append(ScenePlan(i, Path(f"{i}.mp3"), dur, "IMAGE", Path(f"{i}.png"), start=t, gap=g))
        t += dur + g
    return out


# 0.6.3: chữ bắt đầu mờ dần FADE_IN + SHOW_BEFORE giây trước tiếng → đã rõ trước tiếng
EARLY = ov.FADE_IN + ov.SHOW_BEFORE


def _words(text, start=0.0, step=0.5):
    return [(w, start + k * step, start + (k + 1) * step)
            for k, w in enumerate(speech.norm_words(text))]


def test_schedule_follows_voice_and_falls_back():
    plan = _plan()
    words = {2: _words("first some words then the reason is strange and more")}
    items, _ = ov.parse_overlay_rows([["2", "TITLE", "The reason is strange"],
                                      ["2", "LOWER", "Not spoken at all", "", ""],
                                      ["2", "STAMP", "strange", "", "", "", "0.5"]])
    logs = []
    pls = ov.schedule(items, plan, ov.OverlayStyle(), logs.append, words=words)
    by = {p.frame.item.kind: p for p in pls}
    # "the" là từ thứ 5 (chỉ số 4) → 2.0 s sau đầu cảnh
    assert by["TITLE"].start == pytest.approx(plan[1].start + 2.0 - EARLY)
    assert by["LOWER"].start == pytest.approx(plan[1].start + ov.DELAY)   # không khớp
    assert by["STAMP"].start == pytest.approx(plan[1].start + 0.5)       # 'start' thắng
    assert any("khớp giọng đọc: 1/2" in m for m in logs)


def test_quote_reveals_word_by_word_with_voice():
    plan = _plan(2, dur=9.0)
    quote = "They shall not be able to behold the face of the holy"
    words = {1: _words("And it says " + quote + " that is all", step=0.4)}
    items, _ = ov.parse_overlay_rows([["1", "QUOTE", quote, "1 Enoch 38:4"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None, words=words)
    first_word = plan[0].start + 3 * 0.4          # "they" là từ thứ 4
    assert pls[0].frame.words == 0                 # hộp rỗng hiện trước
    assert pls[0].start <= first_word - ov.TYPE_LEAD - ov.FADE_IN
    for p in pls[1:]:
        wc = p.frame.words or len(quote.split())
        spoken = plan[0].start + (3 + wc - 1) * 0.4
        assert p.start == pytest.approx(max(spoken - ov.TYPE_LEAD, p.start), abs=0.05)
        assert p.start <= spoken
    for a, b in zip(pls, pls[1:]):
        assert ov.us_span(a.start, a.length)[1] == ov.us_span(b.start, b.length)[0]


def test_list_items_follow_voice_across_scenes():
    plan = _plan(3)
    words = {1: _words("there are three marks one on the face"),
             2: _words("the second is one on the forehead and more")}
    items, _ = ov.parse_overlay_rows([["scene", "type", "text", "sub", "label", "until"],
                                      ["1", "LIST", "One on the face", "", "Marks", "3"],
                                      ["2", "LIST", "One on the forehead", "", "Marks", ""]])
    li = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None, words=words)
    assert li[0].start == pytest.approx(plan[0].start + 4 * 0.5 - EARLY)
    assert li[1].start == pytest.approx(plan[1].start + 3 * 0.5 - EARLY)
    assert li[-1].end == pytest.approx(plan[2].end - ov.TAIL)


def test_settings_key():
    assert "overlay_sync" in config.DEFAULT_CHANNEL_KEYS
    s = Settings(input_dir=Path("."), channel_dir=Path("."), draft_name="x", capcut_drafts=Path("."))
    assert s.overlay_sync


# --------------------------------------------------------------------------- #
# file giọng thật: hai "câu" tách nhau bởi một quãng lặng
# --------------------------------------------------------------------------- #
def _speechlike(path: Path, parts, rate=16000):
    """parts = [(giây, có tiếng?)] — tiếng là sóng 220 Hz biến điệu."""
    frames = bytearray()
    t = 0
    for sec, loud in parts:
        for i in range(int(sec * rate)):
            v = int(9000 * math.sin(2 * math.pi * 220 * t / rate)
                    * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * t / rate))) if loud else 0
            frames += struct.pack("<h", v)
            t += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def test_draft_overlay_starts_when_sentence_is_spoken(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("cần ffmpeg để đo quãng lặng")
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=2, sec=2.0)
    # cảnh 1: lặng 0.2 s, câu 1 (1.8 s), lặng 0.9 s, câu 2 (2.0 s), lặng 0.3 s
    _speechlike(tmp_path / "Audio" / "1.wav", [(0.2, False), (1.8, True), (0.9, False),
                                               (2.0, True), (0.3, False)])
    (tmp_path / "Texts" / "1.txt").write_text(
        "In those days the kings ruled the land. Then the light appeared on their faces.",
        encoding="utf-8")
    (tmp_path / "overlay.csv").write_text('1,TITLE,"Then the light appeared on their faces"',
                                          encoding="utf-8")
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_claim=False, enable_subtitles=False, enable_bgm=False)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    logs = []
    d = json.loads((build(s, assets, plan, logs.append) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    st = _segs({t["name"]: t for t in d["tracks"]}["chu_main"])[0][0]
    # "Then" bắt đầu câu 2 ở 2.9 s; chữ bắt đầu hiện sớm hơn EARLY (ước lượng: ±0,15 s)
    assert 2.9 - EARLY - 0.2 <= st <= 2.9 - ov.FADE_IN + 0.15, st
    assert any("khớp giọng đọc: 1/1" in m for m in logs)
    # tắt khớp giọng → về kiểu cũ (đầu cảnh + DELAY)
    s.overlay_sync = False
    s.draft_name = "d2"
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    st2 = _segs({t["name"]: t for t in d["tracks"]}["chu_main"])[0][0]
    assert st2 == pytest.approx(ov.DELAY, abs=1e-3)
