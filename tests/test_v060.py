"""0.6.0: đồ họa chữ (overlay) — thẻ chương, trích dẫn đánh máy, câu chốt, dấu
mộc, danh sách cộng dần, ô số liệu — dựng vào draft CapCut và vào mp4."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from capcut_draft_studio import config, overlays as ov
from capcut_draft_studio.models import ScenePlan, Settings

from test_v059 import _mp4, _project, _real_pycapcut, _raw_starts, _segs  # noqa: F401


def _plan(n=6, dur=3.0, gap=0.4):
    out, t = [], 0.0
    for i in range(1, n + 1):
        g = gap if i < n else 0.0
        out.append(ScenePlan(i, Path(f"{i}.mp3"), dur, "IMAGE", Path(f"{i}.png"), start=t, gap=g))
        t += dur + g
    return out


ROWS = [["scene", "type", "text", "sub", "label", "until"],
        ["1", "chapter", "When the righteous are revealed", "1 Enoch 38", "", ""],
        ["2", "QUOTE", "They shall not be able to behold the face of the holy", "1 ENOCH 38:4", "", ""],
        ["3", "LIST", "One on the face", "", "Three marks", "5"],
        ["4", "danh sach", "One on the forehead", "", "Three marks", ""],
        ["4", "mộc", "His light", "", "", ""],
        ["6", "TITLE", "The one who carries it does not know", "Other people see it.", "", ""]]


# --------------------------------------------------------------------------- #
# đọc file
# --------------------------------------------------------------------------- #
def test_parse_rows_aliases_and_errors():
    items, err = ov.parse_overlay_rows(ROWS)
    assert err == []
    assert [i.kind for i in items] == ["CHAPTER", "QUOTE", "LIST", "LIST", "STAMP", "TITLE"]
    assert items[2].until == 5 and items[2].label == "Three marks" and items[2].row == 4
    # không có dòng tiêu đề: cột mặc định scene, type, text, sub
    items, err = ov.parse_overlay_rows([["0007", "TRICH", "Abc def", "Gen 1:1"]])
    assert err == [] and items[0].scene == 7 and items[0].sub == "Gen 1:1"
    items, err = ov.parse_overlay_rows([["scene", "type", "text"], ["x", "QUOTE", "a"],
                                        ["2", "WHATEVER", "a"], ["3", "QUOTE", "ok"]])
    assert len(items) == 1 and len(err) == 2
    assert "dòng 2" in err[0] and "WHATEVER" in err[1]


def test_check_items_against_project():
    items, _ = ov.parse_overlay_rows(ROWS + [["9", "QUOTE", "x", "", "", ""],
                                             ["2", "LOWER", "", "", "", ""],
                                             ["3", "LOWER", "a b c d e f g h i j k", "", "", ""]])
    errors, warns = ov.check_items(items, range(1, 7))
    assert any("không có cảnh 9" in e for e in errors)
    assert any("chưa có chữ" in e for e in errors)
    assert len(errors) == 2
    assert any("11 từ" in w for w in warns)


def test_find_overlay_file(tmp_path):
    assert ov.find_overlay_file(tmp_path) is None
    (tmp_path / "notes.xlsx").write_bytes(b"x")
    (tmp_path / "My video_overlay.csv").write_text("1,QUOTE,a", encoding="utf-8")
    assert ov.find_overlay_file(tmp_path).name == "My video_overlay.csv"
    (tmp_path / "overlay.xlsx").write_bytes(b"x")
    assert ov.find_overlay_file(tmp_path).name == "overlay.xlsx"     # .xlsx trước .csv
    (tmp_path / "~$overlay.xlsx").write_bytes(b"x")                   # file khoá của Excel
    assert ov.find_overlay_file(tmp_path).name == "overlay.xlsx"


def test_settings_keys_persisted():
    for k in ("enable_overlays", "overlay_accent", "overlay_stamp", "overlay_box_alpha",
              "overlay_scale", "overlay_typewriter"):
        assert k in config.DEFAULT_CHANNEL_KEYS
    s = Settings(input_dir=Path("."), channel_dir=Path("."), draft_name="x", capcut_drafts=Path("."))
    assert s.enable_overlays and s.overlay_typewriter


# --------------------------------------------------------------------------- #
# lập lịch
# --------------------------------------------------------------------------- #
def test_schedule_windows_typewriter_and_list():
    plan = _plan()
    items, _ = ov.parse_overlay_rows(ROWS)
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    by = lambda kind: [p for p in pls if p.frame.item.kind == kind]
    ch = by("CHAPTER")[0]
    assert ch.start == pytest.approx(plan[0].start + ov.DELAY)
    assert ch.end == pytest.approx(plan[0].end - ov.TAIL)
    assert ch.fade_in == ov.FADE_IN and ch.fade_out == ov.FADE_OUT
    # trích dẫn: hộp rỗng → các bước tăng dần → bước cuối đủ câu, nối liền không hở
    q = by("QUOTE")
    assert q[0].frame.words == 0 and q[-1].frame.words is None
    words = [p.frame.words for p in q[1:-1]]
    assert words == sorted(words) and len(q) <= ov.MAX_STEPS + 1
    for a, b in zip(q, q[1:]):
        assert a.end == pytest.approx(b.start, abs=1e-6)
    assert q[0].start == pytest.approx(plan[1].start + ov.DELAY)
    assert q[-1].end == pytest.approx(plan[1].end - ov.TAIL)
    assert q[0].fade_in and not q[1].fade_in and q[-1].fade_out and not q[0].fade_out
    # danh sách: 1 mục từ cảnh 3, 2 mục từ cảnh 4, giữ tới hết cảnh 5 (until)
    li = by("LIST")
    assert [p.frame.list_items for p in li] == [("One on the face",),
                                                ("One on the face", "One on the forehead")]
    assert li[0].start == pytest.approx(plan[2].start + ov.DELAY)
    assert li[1].start == pytest.approx(plan[3].start + ov.DELAY)
    assert li[0].end == pytest.approx(li[1].start)
    assert li[1].end == pytest.approx(plan[4].end - ov.TAIL)
    assert {p.layer for p in li} == {"list"} and by("STAMP")[0].layer == "stamp"
    # không chữ nào cùng lớp + cùng track chồng giờ nhau
    groups = {}
    for p in pls:
        groups.setdefault((p.layer, p.track), []).append(p)
    for g in groups.values():
        g.sort(key=lambda p: p.start)
        for a, b in zip(g, g[1:]):
            assert a.end <= b.start + 1e-6


def test_schedule_overlap_goes_to_second_track_and_warns():
    plan = _plan(3)
    items, _ = ov.parse_overlay_rows([["2", "QUOTE", "aa bb"], ["2", "LOWER", "cc"]])
    logs = []
    pls = ov.schedule(items, plan, ov.OverlayStyle(typewriter=False), logs.append)
    assert sorted(p.track for p in pls) == [0, 1]
    assert any("cảnh 2" in m for m in logs)


def test_schedule_start_dur_overrides():
    plan = _plan(3)
    items, _ = ov.parse_overlay_rows([["scene", "type", "text", "start", "dur"],
                                      ["2", "STAMP", "x", "1.0", "1.5"]])
    p = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)[0]
    assert p.start == pytest.approx(plan[1].start + 1.0) and p.length == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# vẽ
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", list(ov.KINDS))
def test_every_kind_renders_inside_frame(kind):
    it = ov.OverlayItem(1, kind, "Ánh sáng trên mặt họ the light", "Sub dòng phụ 38:4", "Nhãn")
    fr = ov.Frame(it, list_items=("Một", "Hai"), list_label="Ba dấu") if kind == "LIST" else ov.Frame(it)
    img = ov.render_frame(fr, 1920, 1080, ov.OverlayStyle())
    assert img.size == (1920, 1080) and img.mode == "RGBA"
    box = img.getchannel("A").getbbox()
    assert box is not None, "không vẽ gì"
    x0, y0, x1, y1 = box
    assert x0 >= 0 and y0 >= 0 and x1 <= 1920 and y1 <= 1080
    if kind not in ("TITLE", "CHAPTER"):        # hai loại này phủ tối cả/ nửa khung
        assert (x1 - x0) * (y1 - y0) < 1920 * 1080 * 0.5


def test_fonts_bundled():
    assert ov.fonts_ok(), "thiếu font trong assets/overlay-fonts"


def test_quote_words_reveal_in_place():
    it = ov.OverlayItem(1, "QUOTE", "one two three four five six seven", "REF")
    st = ov.OverlayStyle()
    full = ov.render_frame(ov.Frame(it), 960, 540, st)
    part = ov.render_frame(ov.Frame(it, words=3), 960, 540, st)
    empty = ov.render_frame(ov.Frame(it, words=0), 960, 540, st)
    # hộp đứng yên: bbox giống nhau ở mọi bước
    assert full.getchannel("A").getbbox() == part.getchannel("A").getbbox() == \
        empty.getchannel("A").getbbox()
    # số điểm ảnh sáng tăng dần theo số từ đã hiện
    bright = lambda im: sum(1 for px in im.convert("L").tobytes() if px > 200)
    assert bright(empty) < bright(part) < bright(full)


def test_write_pngs_dedup_and_cleanup(tmp_path):
    (tmp_path / "ov_old.png").write_bytes(b"x")
    plan = _plan(4)
    items, _ = ov.parse_overlay_rows([["1", "STAMP", "Same"], ["3", "STAMP", "Same"]])
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    n = ov.write_pngs(pls, tmp_path, 320, 180, ov.OverlayStyle())
    assert n == 1 and pls[0].png == pls[1].png and pls[0].png.is_file()
    assert not (tmp_path / "ov_old.png").exists()


# --------------------------------------------------------------------------- #
# draft CapCut thật
# --------------------------------------------------------------------------- #
def _write_csv(path: Path, rows):
    path.write_text("\n".join(",".join(f'"{c}"' for c in r) for r in rows), encoding="utf-8")


def test_draft_has_overlay_tracks_in_time_order(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=6, sec=2.5)
    _write_csv(tmp_path / "overlay.csv", ROWS)
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_claim=False, enable_subtitles=False, gap_mode="fixed")
    assets = scan_assets(s, lambda m: None)
    logs = []
    plan = validate(s, assets, logs.append, collect_errors=True)
    assert plan.errors == [] and plan.overlays[4] == ["LIST", "STAMP"]
    assert any("Đồ họa chữ: 6 mục" in m for m in logs)
    d = json.loads((build(s, assets, plan, logs.append) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    tracks = {t["name"]: t for t in d["tracks"]}
    assert {"chu_list", "chu_main", "chu_stamp"} <= set(tracks)
    for name in ("chu_list", "chu_main", "chu_stamp"):
        starts = _raw_starts(tracks[name])
        assert starts == sorted(starts)
        assert tracks[name]["type"] == "video"
    # đồ họa nằm trên mọi track hình khác
    order = {t["name"]: t["segments"][0]["render_index"] for t in d["tracks"] if t["segments"]}
    others = [v for k, v in order.items() if not k.startswith("chu_")
              and tracks[k]["type"] == "video"]
    assert min(order[n] for n in ("chu_list", "chu_main", "chu_stamp")) > max(others)
    assert order["chu_list"] < order["chu_main"] < order["chu_stamp"]
    # ảnh PNG có thật, đúng cỡ khung project
    mats = {m["id"]: m for m in d["materials"]["videos"]}
    from PIL import Image
    pngs = {mats[x["material_id"]]["path"] for n in ("chu_main",) for x in tracks[n]["segments"]}
    for p in pngs:
        assert Path(p).is_file() and Image.open(p).size == (1920, 1080)
    # có hiệu ứng hiện dần / mờ dần
    anims = json.dumps(d["materials"].get("material_animations", []), ensure_ascii=False)
    assert "渐显" in anims and "渐隐" in anims
    # trích dẫn bắt đầu đúng lúc cảnh 2 + DELAY, kết thúc trước cảnh 3
    q = [x for x in _segs(tracks["chu_main"]) if plan[1].start <= x[0] < plan[2].start]
    assert q[0][0] == pytest.approx(plan[1].start + ov.DELAY, abs=1e-3)
    assert q[-1][0] + q[-1][1] == pytest.approx(plan[1].end - ov.TAIL, abs=2e-3)


def test_draft_overlay_split_around_ad(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=4, sec=2.0)
    ad = _mp4(tmp_path / "ad.mp4", 2.0)
    _write_csv(tmp_path / "overlay.csv", [["1", "LIST", "Mot", "", "Ba", "4"]])
    from capcut_draft_studio.capcut_engine import build, clip_len
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_claim=False, enable_subtitles=False, enable_ad=True, ad_path=ad,
                 ad_after="2")
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    li = _segs({t["name"]: t for t in d["tracks"]}["chu_list"])
    at, ln = plan[1].end, clip_len(ad, "quảng cáo")
    assert len(li) == 2
    assert li[0][0] + li[0][1] == pytest.approx(at, abs=1e-3)
    assert li[1][0] == pytest.approx(at + ln, abs=1e-3)


def test_validate_reports_bad_overlay_and_build_refuses(tmp_path, monkeypatch):
    _project(tmp_path, n=3)
    _write_csv(tmp_path / "overlay.csv", [["9", "QUOTE", "x"]])
    from capcut_draft_studio.media import BuildError, scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts")
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None, collect_errors=True)
    assert any("Đồ họa chữ" in e and "cảnh 9" in e for e in plan.errors)
    with pytest.raises(BuildError):
        validate(s, assets, lambda m: None)
    s.enable_overlays = False
    assert validate(s, assets, lambda m: None, collect_errors=True).errors == []


def test_no_overlay_file_draft_unchanged(tmp_path, monkeypatch):
    """Không có file overlay → không có track chu_* nào (hành vi cũ)."""
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=2)
    from capcut_draft_studio.capcut_engine import build
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False)
    assets = scan_assets(s, lambda m: None)
    d = json.loads((build(s, assets, validate(s, assets, lambda m: None), lambda m: None)
                    / "draft_content.json").read_text(encoding="utf-8"))
    assert not [t for t in d["tracks"] if t["name"].startswith("chu_")]
    assert not (tmp_path / "_capcut_draft_studio" / "overlays").exists()


# --------------------------------------------------------------------------- #
# render ffmpeg
# --------------------------------------------------------------------------- #
def test_scene_args_overlay_chain_and_plain_path_unchanged(tmp_path):
    from capcut_draft_studio import render

    class R:
        scene_args = render.Renderer.scene_args
        scene_overlays = render.Renderer.scene_overlays
        _scene_len = render.Renderer._scene_len
        _xfade_after = render.Renderer._xfade_after

        def __init__(self, plan, ovl):
            self.job = type("J", (), {"plan": plan})()
            self.trans, self._hard, self._ovl = 0.0, set(), ovl
            self.fps, self.w, self.h, self.zoom = 30, 320, 180, 1.0
            self.encoder = "libx264"
            self.s = type("S", (), {"render_crf": 20, "render_preset": "medium",
                                    "image_anim": "off"})()

    plan = _plan(3)
    plain = R(plan, []).scene_args(1, plan[1], Path("o.mp4"))
    assert "-vf" in plain and "-filter_complex" not in plain
    pl = ov.Placement(ov.Frame(ov.OverlayItem(2, "STAMP", "x")), plan[1].start + 0.5, 1.0,
                      "stamp", 0.3, 0.3, 2, png=tmp_path / "a.png")
    span = ov.Placement(ov.Frame(ov.OverlayItem(1, "LIST", "x")), plan[0].start + 1.0,
                        plan[2].start - plan[0].start, "list", 0.3, 0.3, 1, png=tmp_path / "b.png")
    args = R(plan, [pl, span]).scene_args(1, plan[1], Path("o.mp4"))
    chain = args[args.index("-filter_complex") + 1]
    # STAMP: nằm trọn trong cảnh → có fade vào và ra
    assert "fade=t=in:st=0.5000:d=0.3000:alpha=1" in chain
    assert "fade=t=out:st=1.2000:d=0.3000:alpha=1" in chain
    # LIST: bắt đầu ở cảnh trước, kết thúc cuối cảnh này → không fade vào, phủ từ 0
    assert "enable='between(t,0.0000," in chain
    assert chain.count("fade=t=in") == 1
    assert args[args.index("-map") + 1] == "[b2]"


def _ffmpeg():
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("cần ffmpeg")
    return ff


def test_render_burns_overlay_into_mp4(tmp_path, monkeypatch):
    """Render thật: khung giữa cảnh 2 có hộp trích dẫn tối ở giữa, cảnh 1 thì không."""
    ff = _ffmpeg()
    Image = _project(tmp_path, n=3, sec=2.0)
    for i in range(1, 4):
        Image.new("RGB", (64, 36), (230, 230, 230)).save(tmp_path / "Images" / f"{i}.png")
    _write_csv(tmp_path / "overlay.csv", [["2", "QUOTE", "Light upon their faces", "REF 1:1"]])
    from capcut_draft_studio import render
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", width=320, height=180, fps=10,
                 enable_claim=False, enable_logo=False, enable_bgm=False,
                 enable_subtitles=False, enable_transition=False, image_anim="off",
                 gap_mode="fixed", scene_gap=0.0, render_preset="veryfast")
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    out = tmp_path / "out.mp4"
    job = render.RenderJob("t", s, assets, plan, out)
    render.Renderer(job, log=lambda m: None).run()
    assert out.is_file()

    def luma_center(t):
        raw = subprocess.run([ff, "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(out),
                              "-frames:v", "1", "-vf", "crop=60:20:130:80,scale=1:1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        return raw[0]

    assert luma_center(1.0) > 180            # cảnh 1: ảnh sáng, không có chữ
    assert luma_center(plan[1].start + 1.6) < 120   # cảnh 2: hộp trích dẫn tối ở giữa
    assert luma_center(plan[2].start + 1.0) > 180


# --------------------------------------------------------------------------- #
# chạy không giao diện
# --------------------------------------------------------------------------- #
def test_cli_check_build_preview(tmp_path, monkeypatch, capsys):
    pytest.importorskip("tkinter")
    _real_pycapcut(monkeypatch)
    _project(tmp_path, n=3)
    _write_csv(tmp_path / "overlay.csv", [["2", "QUOTE", "Light on their faces", "REF 1:1"]])
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"channel_dir": str(tmp_path / "CH"),
                               "capcut_drafts": str(tmp_path / "drafts"),
                               "register_root_meta": False, "enable_claim": False}),
                   encoding="utf-8")
    from capcut_draft_studio import cli
    base = ["--input", str(tmp_path), "--config", str(cfg)]
    assert cli.main(["check"] + base) == 0
    assert cli.main(["build"] + base + ["--name", "Tap1"]) == 0
    d = json.loads((tmp_path / "drafts" / "Tap1" / "draft_content.json").read_text(encoding="utf-8"))
    assert any(t["name"] == "chu_main" for t in d["tracks"])
    assert cli.main(["overlay-preview"] + base) == 0
    assert (tmp_path / "_capcut_draft_studio" / "overlay-preview.jpg").is_file()
    # file overlay sai → check trả 1 và in lý do
    _write_csv(tmp_path / "overlay.csv", [["9", "QUOTE", "x"]])
    assert cli.main(["check"] + base) == 1
    assert "cảnh 9" in capsys.readouterr().out
    assert cli.main(["overlay-template", "--input", str(tmp_path)]) == 0
    assert cli.main(["overlay-template", "--input", str(tmp_path)]) == 1   # không ghi đè


# --------------------------------------------------------------------------- #
# 0.6.0: cỡ phụ đề khi render mp4 (trước đây to gấp ~3,75 lần, nằm giữa khung)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("h", [720, 1080])
def test_burned_subtitle_size_and_position(tmp_path, h):
    ff = _ffmpeg()
    from capcut_draft_studio import render
    w = h * 16 // 9
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHELLO WORLD\n", encoding="utf-8")
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="x",
                 capcut_drafts=tmp_path, sub_shadow=False)
    style = render.subtitle_force_style(s, h)
    raw = subprocess.run(
        [ff, "-loglevel", "error", "-f", "lavfi", "-i", f"color=black:s={w}x{h}:d=1",
         "-vf", f"subtitles=filename='{render.ass_escape(srt)}':force_style='{style}'",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True).stdout
    rows = [y for y in range(h) if max(raw[y * w:(y + 1) * w]) > 128]
    assert rows, "không thấy phụ đề"
    top, bottom = min(rows), max(rows)
    # một dòng chữ in hoa cao khoảng 3–5% khung, đáy cách mép dưới ~10%
    assert 0.025 * h < bottom - top < 0.06 * h
    assert 0.85 * h < bottom < 0.93 * h


# --------------------------------------------------------------------------- #
# 0.6.0 sửa lỗi: SegmentOverlap khi dựng draft (bước đánh máy chồng nhau 1 µs)
# --------------------------------------------------------------------------- #
def _random_plan(rng, n=120, off=0.0):
    out, t = [], off
    for i in range(1, n + 1):
        d = round(rng.uniform(2.5, 9.0), 3)
        g = rng.choice([0.0, 0.2, 0.4, 0.64]) if i < n else 0.0
        out.append(ScenePlan(i, Path(f"{i}.mp3"), d, "IMAGE", Path("x.png"), start=t, gap=g))
        t += d + g
    return out


def _random_rows(rng, n):
    kinds = ["QUOTE", "QUOTE", "QUOTE", "TITLE", "LOWER", "STAMP", "CHAPTER", "NAME", "STAT"]
    rows = []
    for sc in rng.sample(range(1, n + 1), min(64, n)):
        k = rng.choice(kinds)
        words = rng.randint(2, 50 if k == "QUOTE" else 6)
        row = [str(sc), k, " ".join(f"w{j}" for j in range(words)), "REF 1:1", "", "", "", ""]
        if rng.random() < 0.15:
            row[5] = str(min(n, sc + rng.randint(1, 3)))          # until
        if rng.random() < 0.1:
            row[6], row[7] = f"{rng.uniform(0, 2):.3f}", f"{rng.uniform(0.2, 9):.3f}"
        rows.append(row)
    for i, sc in enumerate(sorted(rng.sample(range(1, n - 6), 4))):
        rows.append([str(sc), "LIST", f"item {i}", "", "Marks", str(sc + 6) if i == 0 else "", "", ""])
    return rows


@pytest.mark.parametrize("seed", range(25))
def test_overlays_never_overlap_in_capcut_tracks(tmp_path, monkeypatch, seed):
    """Lịch đồ họa ngẫu nhiên (trích dẫn dài, until, start/dur, chồng giờ, quảng
    cáo) phải dựng được vào track pycapcut thật mà không SegmentOverlap."""
    _real_pycapcut(monkeypatch)
    import random

    import pycapcut as cc
    from capcut_draft_studio import inserts
    from capcut_draft_studio.capcut_engine import add_overlays
    rng = random.Random(seed)
    plan = _random_plan(rng, off=rng.choice([0.0, 5.0, 3.7]))
    items, err = ov.parse_overlay_rows([["scene", "type", "text", "sub", "label", "until",
                                         "start", "dur"]] + _random_rows(rng, len(plan)))
    assert err == []
    pls = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    png = tmp_path / "x.png"
    pytest.importorskip("PIL.Image").new("RGBA", (8, 8)).save(png)
    for p in pls:
        p.png = png
    breaks = []
    if seed % 2:
        nums = sorted(rng.sample([p.number for p in plan[:-1]], 2))
        breaks = inserts.plan_breaks(plan, nums, 7.5)
    (tmp_path / "d").mkdir()
    script = cc.DraftFolder(str(tmp_path / "d")).create_draft("t", 1920, 1080, 60)
    logs = []
    n = add_overlays(script, cc, pls, inserts.TimeMap(breaks), logs.append)
    assert n >= len(pls)
    for name, tr in script.tracks.items():
        if not name.startswith("chu_"):
            continue
        spans = sorted((x.target_timerange.start, x.target_timerange.end) for x in tr.segments)
        for (s0, e0), (s1, e1) in zip(spans, spans[1:]):
            assert e0 <= s1, f"{name}: {s0}-{e0} chồng {s1}-{e1}"


def test_typewriter_steps_are_exactly_contiguous():
    plan = _plan(3, dur=7.123)
    items, _ = ov.parse_overlay_rows([["2", "QUOTE", " ".join(f"w{i}" for i in range(37)), "R"]])
    q = ov.schedule(items, plan, ov.OverlayStyle(), lambda m: None)
    spans = [ov.us_span(p.start, p.length) for p in q]
    for (_, e0), (s1, _) in zip(spans, spans[1:]):
        assert e0 == s1
