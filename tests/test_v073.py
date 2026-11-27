"""0.7.3: đồ họa chữ không che nhau; danh sách trùng tên tách riêng và tự ẩn khi lời đọc
chuyển ý; clip Remotion cắt gọn (nhẹ khi phát) và nền dòng thời gian là ảnh tĩnh."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from capcut_draft_studio import overlays as ov, remotion as rm
from capcut_draft_studio.models import Settings

from test_v060 import _plan
from test_v070 import _fake_clip, _fake_render, _ffmpeg

ST = ov.OverlayStyle()


def _row(scene, text, label="Tres lugares del texto", until=None, row=0):
    return ov.OverlayItem(scene, "LIST", text, "", label, until=until, row=row)


def _span(pls, kind):
    xs = [p for p in pls if p.frame.item.kind == kind]
    return min(p.start for p in xs), max(p.end for p in xs)


# --------------------------------------------------------------------------- #
# danh sách
# --------------------------------------------------------------------------- #
def test_same_name_lists_are_separate():
    """TBN_16: 'Tres lugares del texto' ở cảnh 14–18 và lại ở cảnh 377 — trước đây gộp làm một."""
    items = [_row(2, "la casa", until=4, row=2), _row(3, "Éfeso", row=3), _row(4, "Pablo", row=4),
             _row(9, "Loida y Eunice", until=10, row=5), _row(10, "Priscila", row=6)]
    plan = _plan(10, dur=4.0)
    groups = ov.list_groups({"X": items}, ["X"], [p.number for p in plan])
    assert [[i.scene for i in g] for g in groups] == [[2, 3, 4], [9, 10]]
    for hold in (None, ov.LIST_HOLD):
        pls = ov.schedule(items, plan, ST, lambda m: None, list_hold=hold)
        labels = sorted((p.start, p.end) for p in pls if p.frame.part == "label")
        assert labels[0][1] <= plan[3].end and labels[-1][0] >= plan[8].start
        rows9 = [p for p in pls if p.frame.part == "row" and p.start >= plan[8].start]
        assert sorted(p.frame.index for p in rows9) == [1, 2]       # danh sách mới đánh số lại


def test_list_windows():
    assert ov.list_windows([0.0, 2.0, 5.0], 40.0, None) == [(0.0, 40.0)]       # kiểu cũ
    assert ov.list_windows([0.0, 2.0, 5.0], 40.0, 10.0) == [(0.0, 15.0)]       # nhắc gần nhau: liền
    assert ov.list_windows([0.0, 30.0, 60.0], 100.0, 10.0) == [(0.0, 10.0), (30.0, 40.0), (60.0, 70.0)]
    assert ov.list_windows([0.0, 30.0], 42.0, 10.0) == [(0.0, 10.0), (30.0, 42.0)]  # gần cuối: tới cuối


def test_long_list_hides_between_mentions_and_returns_whole():
    """'Tres preguntas' (cảnh 293 → 314): hiện quanh mỗi lần nhắc, giữa chừng ẩn đi."""
    plan = _plan(20, dur=5.0)
    items = [_row(2, "La verdad", "Tres preguntas", until=19), _row(9, "el fruto", "Tres preguntas"),
             _row(16, "el propósito", "Tres preguntas")]
    pls = ov.schedule(items, plan, ST, lambda m: None, list_hold=ov.LIST_HOLD)
    labels = sorted((round(p.start, 2), round(p.end, 2)) for p in pls if p.frame.part == "label")
    assert len(labels) == 3
    for a, b in labels:
        assert b - a <= ov.LIST_HOLD + 0.5          # tính từ lần nhắc cuối trong khoảng
    # lần hiện thứ ba có đủ 3 dòng (2 dòng cũ hiện lại cùng danh sách)
    last = labels[-1][0]
    assert sorted(p.frame.index for p in pls if p.frame.part == "row" and p.start >= last - 1e-6) == [1, 2, 3]
    # tắt (list_hold=None) = như trước: một khoảng liền
    old = ov.schedule(items, plan, ST, lambda m: None)
    assert len([p for p in old if p.frame.part == "label"]) == 1


# --------------------------------------------------------------------------- #
# tránh che nhau
# --------------------------------------------------------------------------- #
def _overlaps(pls, thr=ov.HANDOFF + 0.02):
    reg, out = {}, []
    spans = {}
    for p in pls:
        k = id(p.frame.item)
        a, b = spans.get(k, (p.start, p.end))
        spans[k] = (min(a, p.start), max(b, p.end))
        if k not in reg:
            reg[k] = (p.frame.item, ov._solid_box(ov.Frame(p.frame.item), ST))
    keys = list(spans)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            (ia, ra), (ib, rb) = reg[a], reg[b]
            t = min(spans[a][1], spans[b][1]) - max(spans[a][0], spans[b][0])
            if t > thr and ra and rb and ra[0] < rb[2] and rb[0] < ra[2] and ra[1] < rb[3] and rb[1] < ra[3]:
                out.append((ia.kind, ib.kind, round(t, 2)))
    return out


def test_term_and_quote_in_one_scene_take_turns():
    plan = _plan(3, dur=8.0)
    items = [ov.OverlayItem(2, "TERM", "Logos | λόγος", "word", "Greek", start=0.5),
             ov.OverlayItem(2, "QUOTE", "In the beginning was the Word", "John 1:1", start=4.0)]
    pls = ov.schedule(items, plan, ST, lambda m: None, warn_overlap=False)
    assert _overlaps(pls)                                    # trước: che nhau tới hết cảnh
    logs = []
    out = ov.avoid_overlap(pls, ST, logs.append)
    assert _overlaps(out) == []
    t0, t1 = _span(out, "TERM")
    q0, q1 = _span(out, "QUOTE")
    assert q0 == pytest.approx(plan[1].start + 4.0, abs=0.6)  # trích dẫn vẫn hiện đúng lúc
    assert t1 == pytest.approx(q0 + ov.HANDOFF, abs=1e-6)    # TERM tắt khi trích dẫn hiện
    assert q1 == pytest.approx(plan[1].end - ov.TAIL, abs=1e-3)
    term = [p for p in out if p.frame.item.kind == "TERM"]
    assert term[-1].fade_out > 0                             # tắt mờ, không biến mất cụt
    assert any("TERM nhường QUOTE" in m for m in logs)


def test_too_close_splits_time_and_typing_still_finishes():
    plan = _plan(3, dur=6.0)
    items = [ov.OverlayItem(2, "TERM", "Logos | λόγος", "word", "Greek"),
             ov.OverlayItem(2, "QUOTE", "In the beginning was the Word", "John 1:1")]
    pls = ov.schedule(items, plan, ST, lambda m: None, warn_overlap=False)
    q_end = _span(pls, "QUOTE")[1]
    text_before = [p for p in pls if p.frame.item.kind == "QUOTE" and p.frame.part == "text"]
    out = ov.avoid_overlap(pls, ST, lambda m: None)
    assert _overlaps(out) == []
    qs = sorted((p for p in out if p.frame.item.kind == "QUOTE" and p.frame.part == "text"),
                key=lambda p: p.start)
    assert len(qs) == len(text_before)                       # không mất bước đánh máy nào
    assert qs[-1].frame.chars is None                        # câu vẫn gõ xong trọn
    assert _span(out, "QUOTE")[1] == pytest.approx(q_end, abs=1e-6)
    for a, b in zip(qs, qs[1:]):                             # chuỗi đánh máy vẫn liền nhau
        assert b.start == pytest.approx(a.end, abs=1e-6)


def test_separate_corners_are_untouched():
    plan = _plan(2, dur=6.0)
    items = [ov.OverlayItem(1, "PLACE", "Kidron Valley", "east of Jerusalem"),
             ov.OverlayItem(1, "TERM", "Logos | λόγος", "word", "Greek", start=1.0)]
    pls = ov.schedule(items, plan, ST, lambda m: None)
    before = [(p.frame.key(), p.start, p.length) for p in pls]
    out = ov.avoid_overlap(pls, ST, lambda m: None)
    assert sorted((p.frame.key(), p.start, p.length) for p in out) == sorted(before)


def test_prepare_setting_off_is_old_behaviour(tmp_path):
    from test_v060 import _write_csv
    from test_v059 import _project
    _project(tmp_path, n=4, sec=3.0)
    _write_csv(tmp_path / "overlay.csv", [["scene", "type", "text", "sub", "label", "until"],
                                          ["1", "LIST", "One", "", "Two marks", "4"],
                                          ["3", "LIST", "Two", "", "Two marks", ""],
                                          ["2", "TERM", "Logos | λόγος", "word", "Greek", ""],
                                          ["2", "QUOTE", "Light upon their faces", "REF", "", ""]])
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", gap_mode="fixed", enable_subtitles=False,
                 overlay_avoid_overlap=False, overlay_sync=False)
    plan = validate(s, scan_assets(s, lambda m: None), lambda m: None)
    got = ov.prepare(s, plan, tmp_path / "o1", lambda m: None)
    items, _ = ov.load_overlays(tmp_path / "overlay.csv")
    ref = ov.schedule(items, plan, ov.OverlayStyle.from_settings(s), lambda m: None)
    assert [(p.frame.key(), round(p.start, 6), round(p.length, 6)) for p in got] == \
           [(p.frame.key(), round(p.start, 6), round(p.length, 6)) for p in ref]


def test_settings_key_persisted():
    from capcut_draft_studio import config
    from capcut_draft_studio.ui.app import OTHER_BOOLS
    assert "overlay_avoid_overlap" in config.DEFAULT_CHANNEL_KEYS
    assert OTHER_BOOLS["overlay_avoid_overlap"] is True


# --------------------------------------------------------------------------- #
# clip Remotion nhẹ hơn
# --------------------------------------------------------------------------- #
def test_crop_clip_shrinks_and_records_position(tmp_path):
    p = {"width": 320, "height": 180, "fps": 10, "frames": 12}
    clip = _fake_clip(tmp_path / "rm_term_x.mov", p)       # hộp ở giữa: 160×90 tại (80, 45)
    box = rm.crop_clip(clip, 320, 180, lambda m: None)
    assert box and box["W"] == 320 and box["H"] == 180
    assert box["x"] <= 80 <= box["x"] + 8 and box["y"] <= 45 <= box["y"] + 8
    assert box["w"] < 200 and box["h"] < 110 and box["w"] % 2 == 0 and box["h"] % 2 == 0
    v = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,pix_fmt", "-of", "json", str(clip)],
                                  capture_output=True, text=True).stdout)["streams"][0]
    assert (v["width"], v["height"]) == (box["w"], box["h"]) and v["pix_fmt"].startswith("yuva")
    assert rm.clip_box(clip) == box and rm.crop_clip(clip, 320, 180) == box   # làm một lần
    assert not list(tmp_path.glob("*.crop.mov"))


def test_full_frame_clip_is_left_alone(tmp_path):
    ff = _ffmpeg()
    clip = tmp_path / "rm_full.mov"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x36:r=10", "-frames:v", "5",
                    "-vf", "format=rgba", "-c:v", "prores_ks", "-profile:v", "4444",
                    "-pix_fmt", "yuva444p10le", str(clip)], check=True)
    assert rm.crop_clip(clip, 64, 36, lambda m: None) is None and rm.clip_box(clip) is None


def test_clip_placement_in_capcut_units(monkeypatch):
    from test_v059 import _real_pycapcut
    _real_pycapcut(monkeypatch)
    import pycapcut as cc
    from capcut_draft_studio.capcut_engine import clip_placement
    cs = clip_placement(cc, {"x": 1302, "y": 264, "w": 618, "h": 514, "W": 1920, "H": 1080}, (1920, 1080))
    fit = min(1920 / 618, 1080 / 514)
    assert cs.scale_x == pytest.approx(1 / fit) and cs.scale_y == pytest.approx(1 / fit)
    assert cs.transform_x == pytest.approx((1302 + 309 - 960) / 960)
    assert cs.transform_y == pytest.approx((540 - (264 + 257)) / 540)
    assert clip_placement(cc, None, (1920, 1080)) is None


def test_timeline_background_stays_static_png_under_clip(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    plan = _plan(3, dur=6.0)
    items = [ov.OverlayItem(2, "TIMELINE", "1446 BC | *586 BC* | 70 AD", "", "Key dates")]
    pls = ov.schedule(items, plan, ST, lambda m: None)
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="d", capcut_drafts=tmp_path,
                 enable_remotion=True)
    out = ov.use_remotion(s, pls, ST, (320, 180), 10, lambda m: None)
    bg = [p for p in out if p.frame.part == "bg"]
    clip = [p for p in out if p.clip is not None]
    assert len(bg) == 1 and bg[0].clip is None and len(clip) == 1
    assert clip[0].stacked and (bg[0].layer, bg[0].track) < (clip[0].layer, clip[0].track) or \
        out.index(bg[0]) < out.index(clip[0])                  # clip nằm trên nền
    props = rm.make_props(items[0], ST, (1920, 1080), 30, 4.0)
    assert props["background"] is False
