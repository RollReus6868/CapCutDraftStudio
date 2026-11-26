"""0.6.4: chữ to hơn 30 %, chuyển động mượt bằng keyframe có gia tốc, trích dẫn
đánh máy từng ký tự, 9 kiểu đồ họa mới."""
from __future__ import annotations

import math
import re

import pytest

from capcut_draft_studio import motion as mo
from capcut_draft_studio import overlay_draw as od
from capcut_draft_studio import overlays as ov

from test_v062 import _plan, _words

W, H = 1920, 1080


# --------------------------------------------------------------------------- #
# chuyển động
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", [n for n in mo.PRESETS if n not in ("none", "bar_top", "bar_bottom")])
def test_motion_starts_from_offset_and_settles(name):
    m = mo.PRESETS[name]
    L = 4.0
    a0, dx0, dy0, s0 = mo.state(m, 0.0, L)
    assert a0 == pytest.approx(0.0)
    assert (dx0, dy0, s0) == pytest.approx((m.dx, m.dy, m.s0))
    a, dx, dy, s = mo.state(m, m.din, L)
    assert a == pytest.approx(1.0) and dx == pytest.approx(0) and dy == pytest.approx(0)
    assert s == pytest.approx(1.0 + m.drift * m.din / L, abs=1e-6)
    assert mo.state(m, L, L)[0] == pytest.approx(0.0)                # tắt hẳn ở cuối


def test_ease_out_is_smooth_and_front_loaded():
    m = mo.PRESETS["rise"]
    ys = [mo.state(m, t, 5.0)[2] for t in [i * m.din / 20 for i in range(21)]]
    steps = [abs(b - a) for a, b in zip(ys, ys[1:])]
    assert all(b <= a + 1e-12 for a, b in zip(steps, steps[1:]))      # chậm dần đều, không giật
    assert steps[0] > steps[-1] * 5


def test_slam_overshoots_then_lands():
    m = mo.PRESETS["slam"]
    ss = [mo.state(m, t, 3.0)[3] for t in [i * m.din / 40 for i in range(41)]]
    assert ss[0] == pytest.approx(m.s0) and min(ss) < 0.99 and ss[-1] == pytest.approx(1.0)


def test_short_segment_squeezes_motion():
    din, ain, dout = mo.durations(mo.PRESETS["settle"], 1.0)
    assert din == pytest.approx(0.45) and dout == pytest.approx(0.40) and ain < din


def test_keyframes_scale_around_graphic_centre():
    m = mo.PRESETS["pop"]
    anchor = (1500.0, 300.0)
    k = mo.keyframes(m, 3.0, (W, H), anchor)
    assert k["alpha"][0] == (0.0, 0.0) and k["alpha"][-1][1] == pytest.approx(0.0)
    for (t, x), (_, y), (_, s) in zip(k["x"], k["y"], k["scale"]):
        # tâm đồ họa đứng yên: vị trí bù đúng (1 - s)·(tâm đồ họa − tâm khung)
        assert x * W / 2 == pytest.approx((1 - s) * (anchor[0] - W / 2), abs=0.05)
        assert -y * H / 2 == pytest.approx((1 - s) * (anchor[1] - H / 2), abs=0.05)
    assert len(k["alpha"]) >= 12                                   # lấy mẫu dày → mượt


def test_keyframes_drop_unchanged_properties_and_follow_ad_pieces():
    k = mo.keyframes(mo.PRESETS["fade"], 3.0, (W, H), (W / 2, H / 2))
    assert k["x"] == [] and k["y"] == [] and k["scale"] == [] and k["alpha"]
    whole = mo.keyframes(mo.PRESETS["rise"], 3.0, (W, H), (W / 2, H / 2))
    p2 = mo.keyframes(mo.PRESETS["rise"], 3.0, (W, H), (W / 2, H / 2), piece=(1.0, 2.0))
    assert p2["alpha"][0] == (0.0, 1.0) and p2["y"] == []   # mẩu 2: đã hiện xong, không trượt nữa
    assert p2["alpha"][-1] == (2.0, 0.0) and whole["alpha"][-1][1] == 0.0


def _eval(expr: str, t: float) -> float:
    py = expr.replace("pow(", "_pow(").replace("clip(", "_clip(")
    return eval(py, {"t": t, "_pow": pow, "_clip": lambda v, a, b: max(a, min(b, v))})


@pytest.mark.parametrize("name", ["rise", "pop", "settle", "slam", "slide_right"])
def test_ffmpeg_expressions_match_python_motion(name):
    m = mo.PRESETS[name]
    a, L = 0.7, 3.2
    ex = mo.ffmpeg_exprs(m, a, L)
    for t in [a + i * L / 37 for i in range(38)]:
        _, dx, dy, s = mo.state(m, t - a, L)
        assert _eval(ex["s"], t) == pytest.approx(s, abs=1e-4)
        assert _eval(ex["dx"], t) == pytest.approx(dx, abs=1e-5)
        assert _eval(ex["dy"], t) == pytest.approx(dy, abs=1e-5)


def test_cinema_bars_slide_from_frame_edges():
    top = ov.Placement(ov.Frame(ov.OverlayItem(1, "CINEMA", "")), 0, 5, motion="bar_top", fade_in=0.7,
                       fade_out=0.55)
    m, fi, fo = ov.placement_motion(top, W, H)
    bar = od.cinema_bar(W, H) / H
    a, _, dy, _ = mo.state(m, 0.0, 5.0)
    assert a == 1.0 and dy == pytest.approx(-(bar + 0.004))        # nằm hẳn ngoài khung
    assert mo.state(m, 5.0, 5.0)[2] == pytest.approx(-(bar + 0.004)) and fi and fo


# --------------------------------------------------------------------------- #
# chữ to hơn 30 %
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", ["LOWER", "STAT", "QUOTE"])
def test_text_is_thirty_percent_bigger(kind, monkeypatch):
    it = ov.OverlayItem(1, kind, "The kings and the powerful", "copies found")

    def text_h(base):
        monkeypatch.setattr(od, "BASE_SIZE", base)
        part = "text" if kind == "QUOTE" else ""
        box = od.render_frame(od.Frame(it, part=part), W, H, ov.OverlayStyle()).getchannel("A").getbbox()
        return box[3] - box[1]

    assert text_h(1.3) / text_h(1.0) == pytest.approx(1.3, rel=0.08)


# --------------------------------------------------------------------------- #
# đánh máy từng ký tự
# --------------------------------------------------------------------------- #
def test_marks_highlight_and_plain():
    p, hi = od.marks("for *a greater than Solomon* is here")
    assert p == "for a greater than Solomon is here"
    assert {p[i] for i in hi} == set("a greater than Solomon") and min(hi) == 4
    assert od.marks("a * b")[1] == frozenset()               # dấu sao lẻ không làm lệch chữ


def test_typed_frames_grow_by_characters_in_place():
    it = ov.OverlayItem(1, "QUOTE", "The queen of the south shall *rise up* in the judgment", "Matthew 12:42")
    full = od.render_frame(od.Frame(it, part="text"), W, H, ov.OverlayStyle())
    n = len(od.plain(it.text))
    same = od.render_frame(od.Frame(it, part="text", chars=n), W, H, ov.OverlayStyle())
    assert full.tobytes() == same.tobytes()       # gõ hết = chữ đầy đủ, không xê dịch
    prev = 0
    for c in (1, 5, 17, 30, n - 1):
        img = od.render_frame(od.Frame(it, part="text", chars=c), W, H, ov.OverlayStyle())
        ink = sum(img.getchannel("A").histogram()[129:])
        assert ink > prev
        prev = ink
    caret = od.render_frame(od.Frame(it, part="text", chars=10, caret=True), W, H, ov.OverlayStyle())
    plain_ = od.render_frame(od.Frame(it, part="text", chars=10), W, H, ov.OverlayStyle())
    assert caret.tobytes() != plain_.tobytes()


def test_char_times_follow_words_and_type_marks_respect_frame_rate():
    text = "one two three"
    toks = [10.0, 10.5, 11.0]
    t = ov.char_times(text, toks, 0, 22, 9)
    assert len(t) == len(text) and t == sorted(t)
    assert t[0] == pytest.approx(10.0 - ov.TYPE_LEAD)
    assert t[4] == pytest.approx(10.5 - ov.TYPE_LEAD)          # "t" của two
    assert t[3] == t[4]                                        # dấu cách đi cùng chữ sau
    assert t[-1] < 11.0 + 0.5
    marks_ = ov.type_marks(t)
    assert marks_[-1][1] == len(text)
    assert all(b[0] - a[0] >= ov.MIN_TYPE_STEP - 1e-9 for a, b in zip(marks_, marks_[1:]))
    long_ = ov.type_marks([i * 0.001 + i * ov.MIN_TYPE_STEP for i in range(2000)])
    assert len(long_) <= ov.MAX_TYPE_FRAMES and long_[-1][1] == 2000


def test_quote_typed_with_voice_box_first_then_ref():
    plan = _plan(2, dur=12.0)
    quote = "They shall not be able to behold the face of the holy"
    words = {1: _words("and it says " + quote + " and that is all", step=0.4)}
    items, _ = ov.parse_overlay_rows([["1", "QUOTE", quote, "1 Enoch 38:4"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None, words=words)
    parts = {p.frame.part for p in pls}
    assert parts == {"box", "text", "ref"}
    box = next(p for p in pls if p.frame.part == "box")
    text = sorted([p for p in pls if p.frame.part == "text"], key=lambda p: p.start)
    ref = next(p for p in pls if p.frame.part == "ref")
    typed_ = [p for p in text if p.frame.chars]
    first = plan[0].start + 3 * 0.4
    assert box.start + mo.get("pop").din <= first - ov.TYPE_LEAD + 1e-6
    assert typed_[0].start == pytest.approx(first - ov.TYPE_LEAD, abs=0.04)
    assert ref.start >= text[-1].start and ref.stacked and ref.motion == "rise"
    assert box.end == pytest.approx(text[-1].end) == pytest.approx(ref.end)


def test_typewriter_off_draws_whole_quote_once():
    plan = _plan(2)
    items, _ = ov.parse_overlay_rows([["1", "QUOTE", "One two three four", "R"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(typewriter=False), lambda m: None)
    assert len(pls) == 1 and pls[0].frame.part == "" and pls[0].motion == "pop"


# --------------------------------------------------------------------------- #
# kiểu mới
# --------------------------------------------------------------------------- #
NEW = ["PLACE", "TERM", "VS", "TIMELINE", "KEYWORD", "SOURCE", "NOTE", "CINEMA", "SUBSCRIBE"]


def test_new_kinds_and_aliases_parse():
    rows = [["1", "Dateline", "Qumran", "1947"], ["1", "từ gốc", "Logos | λόγος", "word"],
            ["1", "so sánh", "A", "B"], ["1", "dòng thời gian", "1 BC | 2 AD"],
            ["1", "từ khóa", "Betrayal"], ["1", "nguồn", "Josephus"], ["1", "giấy cổ", "text"],
            ["1", "letterbox", ""], ["1", "đăng ký", ""]]
    items, errs = ov.parse_overlay_rows(rows)
    assert errs == [] and [i.kind for i in items] == NEW
    e, _ = ov.check_items(items, [1])
    assert e == []


def test_new_kinds_validation():
    items, _ = ov.parse_overlay_rows([["1", "VS", "Only left"], ["1", "TIMELINE", "1947"],
                                      ["1", "TERM", ""]])
    e, _ = ov.check_items(items, [1])
    assert any("sub" in x for x in e) and any("2 mốc" in x for x in e) and any("chưa có chữ" in x for x in e)


SAMPLE = {
    "PLACE": ("Qumran, Judean Desert", "Spring 1947", ""),
    "TERM": ("Nephilim | נְפִילִים", "the fallen ones", "Hebrew"),
    "VS": ("What the church taught", "What the scroll says", "Two readings"),
    "TIMELINE": ("1446 BC | 1010 BC | *586 BC* | 70 AD", "", "The exile"),
    "KEYWORD": ("*Betrayal*", "Thirty pieces of silver", "Chapter three"),
    "SOURCE": ("Josephus, Antiquities 18.3", "", ""),
    "NOTE": ("I have seen the city of the dead and *no one* returns unchanged.", "Aristeas", ""),
    "CINEMA": ("Jerusalem · 33 AD", "", ""),
    "SUBSCRIBE": ("Subscribe", "New study every week", ""),
}
PARTS = {"PLACE": ["box", "text"], "TERM": [""], "VS": ["left", "right", "mid"],
         "TIMELINE": ["bg", "line"], "KEYWORD": ["word", "line"], "SOURCE": [""],
         "NOTE": ["card", "text", "ref"], "CINEMA": ["top", "bottom"], "SUBSCRIBE": [""]}


@pytest.mark.parametrize("kind", NEW)
def test_new_kind_parts_render_and_add_up(kind):
    text, sub, label = SAMPLE[kind]
    it = ov.OverlayItem(1, kind, text, sub, label)
    whole = od.render_frame(od.Frame(it), W, H, ov.OverlayStyle()).getchannel("A")
    assert whole.getbbox() is not None
    for part in PARTS[kind]:
        img = od.render_frame(od.Frame(it, part=part), W, H, ov.OverlayStyle()).getchannel("A")
        box = img.getbbox()
        assert box is not None, part
        x0, y0, x1, y1 = box
        assert x0 >= 0 and y0 >= 0 and x1 <= W and y1 <= H
    if len(PARTS[kind]) > 1:
        from PIL import ImageChops
        acc = None
        for part in PARTS[kind]:
            a = od.render_frame(od.Frame(it, part=part), W, H, ov.OverlayStyle()).getchannel("A")
            acc = a if acc is None else ImageChops.lighter(acc, a)
        assert acc.getbbox() == whole.getbbox()                 # các phần ghép lại đúng bằng cả đồ họa


@pytest.mark.parametrize("kind", NEW)
def test_new_kinds_schedule_and_never_overlap_unexpectedly(kind):
    text, sub, label = SAMPLE[kind]
    plan = _plan(3, dur=6.0)
    items, _ = ov.parse_overlay_rows([["2", kind, text, sub, label]])
    logs = []
    pls = ov.schedule(items, plan, ov.OverlayStyle(), logs.append)
    assert pls and not any("cùng lúc" in m for m in logs)
    for p in pls:
        assert p.motion in mo.PRESETS
        assert plan[1].start - 1e-6 <= p.start and p.end <= plan[1].end + 1e-6
    groups = {}
    for p in pls:
        groups.setdefault((p.layer, p.track), []).append(p)
    for g in groups.values():
        g.sort(key=lambda p: p.start)
        for a, b in zip(g, g[1:]):
            assert ov.us_span(a.start, a.length)[1] <= ov.us_span(b.start, b.length)[0]


def test_cinema_starts_with_scene_and_bars_cover_letterbox():
    plan = _plan(3)
    items, _ = ov.parse_overlay_rows([["scene", "type", "text", "sub", "label", "until"],
                                      ["1", "CINEMA", "", "", "", "3"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    assert {p.frame.part for p in pls} == {"top", "bottom"} and {p.layer for p in pls} == {"frame"}
    assert pls[0].start == pytest.approx(plan[0].start) and pls[0].end == pytest.approx(plan[2].end - ov.TAIL)
    img = od.render_frame(od.Frame(items[0], part="top"), W, H, ov.OverlayStyle())
    assert img.getchannel("A").getbbox() == (0, 0, W, math.ceil(od.cinema_bar(W, H)) + 1) or \
        img.getchannel("A").getbbox()[3] >= od.cinema_bar(W, H)


def test_timeline_points_and_progress():
    assert od.timeline_points("1 | *2* | 3") == [("1", False), ("2", True), ("3", False)]
    assert od.timeline_points("1 | 2") == [("1", False), ("2", True)]
    it = ov.OverlayItem(1, "TIMELINE", "1446 BC | 586 BC | 70 AD")
    widths = []
    for p in (0.1, 0.5, 1.0):
        box = od.render_frame(od.Frame(it, part="line", progress=p), W, H, ov.OverlayStyle())
        a = box.getchannel("A")
        widths.append(sum(a.histogram()[201:]))
    assert widths == sorted(widths) and widths[0] < widths[-1]


def test_hebrew_drawn_right_to_left_with_marks_on_letters():
    assert od.visual_rtl("אב") == "בא"
    assert od.visual_rtl("נְפִ") == "פִנְ"                    # dấu đi theo chữ gốc
    f = od.font("hebrew", 60)
    from PIL import Image, ImageDraw
    img = Image.new("L", (400, 120), 0)
    od.draw_hebrew(ImageDraw.Draw(img), (10, 10), "נְ", f, 255)
    base = Image.new("L", (400, 120), 0)
    ImageDraw.Draw(base).text((10, 10), "נ", font=f, fill=255)
    bb, mb = base.getbbox(), img.getbbox()
    assert mb[1] == bb[1] and mb[3] > bb[3]                   # dấu nằm dưới chữ
    assert bb[0] - 2 <= mb[0] and mb[2] <= bb[2] + 2          # không lệch ra ngoài chữ


def test_list_rows_slide_in_separately():
    plan = _plan(3)
    items, _ = ov.parse_overlay_rows([["scene", "type", "text", "sub", "label", "until"],
                                      ["1", "LIST", "One", "", "Marks", "3"],
                                      ["2", "LIST", "Two", "", "Marks", ""]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    lab = [p for p in pls if p.frame.part == "label"]
    rows = sorted([p for p in pls if p.frame.part == "row"], key=lambda p: p.frame.index)
    assert len(lab) == 1 and [r.frame.index for r in rows] == [1, 2]
    assert all(p.motion == "slide_left" for p in pls) and rows[1].stacked
    # dòng 2 vẽ đúng chỗ của nó trong danh sách đầy đủ
    from PIL import ImageChops
    whole = od.render_frame(od.Frame(items[0], list_items=("One", "Two"), list_label="Marks"),
                            W, H, ov.OverlayStyle()).getchannel("A")
    acc = None
    for p in pls:
        a = od.render_frame(p.frame, W, H, ov.OverlayStyle()).getchannel("A")
        acc = a if acc is None else ImageChops.lighter(acc, a)
    assert acc.getbbox() == whole.getbbox()


def test_template_and_guide_mention_every_kind(tmp_path):
    from openpyxl import load_workbook
    path = ov.write_template(tmp_path / "overlay.xlsx")
    wb = load_workbook(path)
    kinds = {r[1] for r in wb["OVERLAY"].iter_rows(min_row=2, values_only=True)}
    assert set(ov.KINDS) <= kinds
    guide = " ".join(str(c) for r in wb["HUONG DAN"].iter_rows(values_only=True) for c in r if c)
    for k in ov.KINDS:
        assert re.search(rf"\b{k}\b", guide), k
    items, errs = ov.load_overlays(path)
    assert errs == []
    e, _ = ov.check_items(items, range(1, 60))
    assert e == []
