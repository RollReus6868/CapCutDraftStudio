"""0.7.0: TERM, TIMELINE vẽ bằng Remotion thành clip ProRes 4444 có alpha — dựng vào
draft CapCut và vào mp4; chưa cài / vẽ hỏng thì quay về bản Pillow."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from capcut_draft_studio import config, overlays as ov, remotion as rm
from capcut_draft_studio.models import Settings

from test_v059 import _mp4, _project, _real_pycapcut, _segs  # noqa: F401
from test_v060 import _plan, _write_csv

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "assets" / "remotion-engine"


def _ffmpeg():
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("cần ffmpeg")
    return ff


def _fake_clip(path: Path, props: dict) -> Path:
    """Clip giả giống clip Remotion: ProRes 4444 nền trong suốt, một hộp tối giữa khung."""
    ff = _ffmpeg()
    w, h, fps, n = props["width"], props["height"], props["fps"], props["frames"]
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi",
                    "-i", f"color=c=black:s={w}x{h}:r={fps}",
                    "-frames:v", str(n),
                    "-vf", "format=rgba,geq=r=0:g=0:b=0:"
                           "a='if(between(X,W/4,3*W/4)*between(Y,H/4,3*H/4),217,0)'",
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                    str(path)], check=True)
    # clip giả phải thật sự trong suốt ngoài hộp (như clip Remotion)
    px = subprocess.run([ff, "-v", "error", "-i", str(path), "-frames:v", "1", "-vf",
                         "crop=2:2:0:0,format=rgba", "-f", "rawvideo", "-"],
                        capture_output=True, check=True).stdout
    assert px[3] == 0
    return path


def _fake_render(monkeypatch, fail_kinds=(), calls=None):
    def fake(jobs, base=None, log=print, cancel=None):
        out = {}
        for j in jobs:
            if calls is not None:
                calls.append(j)
            if j.kind in fail_kinds:
                out[j.out] = False
                continue
            if not j.out.is_file():
                _fake_clip(j.out, j.props)
            out[j.out] = True
        return out
    monkeypatch.setattr(rm, "render_jobs", fake)


ITEMS = [ov.OverlayItem(1, "TERM", "Nephilim | נְפִילִים", "the fallen ones", "Hebrew", row=2),
         ov.OverlayItem(2, "TIMELINE", "1446 BC | *586 BC* | 70 AD", "", "Key dates", until=3, row=3),
         ov.OverlayItem(4, "QUOTE", "In the beginning was the Word", "John 1:1", row=4)]


# --------------------------------------------------------------------------- #
# dữ liệu cho Remotion
# --------------------------------------------------------------------------- #
def test_make_props_term_and_timeline():
    st = ov.OverlayStyle(accent="#AABBCC", box_alpha=0.7, scale=1.0, subs_on=True)
    p = rm.make_props(ITEMS[0], st, (1920, 1080), 30, 2.5)
    assert p["term"] == "Nephilim" and p["orig"] == "נְפִילִים" and p["hebrew"] is True
    assert p["label"] == "Hebrew" and p["sub"] == "the fallen ones"
    assert p["frames"] == 76 and p["lengthSec"] == 2.5          # 75 khung + 1 khung dư
    assert p["style"] == {"accent": "#AABBCC", "boxAlpha": 0.7, "k": 1.3}
    g = rm.make_props(ov.OverlayItem(1, "TERM", "Logos | λόγος"), st, (1280, 720), 25, 1.0)
    assert g["hebrew"] is False and g["width"] == 1280 and g["fps"] == 25
    assert g["style"]["k"] == pytest.approx(720 / 1080 * 1.3, abs=1e-4)
    t = rm.make_props(ITEMS[1], st, (1920, 1080), 30, 4.0)
    assert t["points"] == [{"label": "1446 BC", "cur": False}, {"label": "586 BC", "cur": True},
                           {"label": "70 AD", "cur": False}]
    assert t["subsOn"] is True
    # không đánh dấu mốc nào → mốc cuối là mốc đang nói (như bản Pillow)
    t2 = rm.make_props(ov.OverlayItem(1, "TIMELINE", "1 | 2"), st, (1920, 1080), 30, 2.0)
    assert t2["points"][-1]["cur"] is True


def test_frames_cover_length_with_spare_frame():
    for ln in (0.04, 1.0, 2.9, 3.4567, 10.0):
        f = rm.frames_for(ln, 30)
        assert f / 30 >= ln + 1 / 30 - 1e-9
        assert f / 30 < ln + 2 / 30 + 1e-9


def test_clip_name_follows_content_and_engine():
    st = ov.OverlayStyle()
    p = rm.make_props(ITEMS[0], st, (1920, 1080), 30, 2.5)
    a = rm.clip_name("TERM", p, "e1")
    assert a == rm.clip_name("TERM", dict(p), "e1") and a.startswith("rm_term_") and a.endswith(".mov")
    assert a != rm.clip_name("TERM", {**p, "sub": "x"}, "e1")
    assert a != rm.clip_name("TERM", p, "e2")


# --------------------------------------------------------------------------- #
# gộp thành clip / quay về Pillow
# --------------------------------------------------------------------------- #
def _sched(tmp_path, enable=True):
    plan = _plan(5, dur=3.0)
    st = ov.OverlayStyle()
    pls = ov.schedule(list(ITEMS), plan, st, lambda m: None)
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="d", capcut_drafts=tmp_path,
                 enable_remotion=enable, width=320, height=180)
    return plan, st, pls, s


def test_each_item_becomes_one_clip_with_same_span(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    plan, st, pls, s = _sched(tmp_path)
    before = {k: (min(p.start for p in pls if p.frame.item.kind == k),
                  max(p.end for p in pls if p.frame.item.kind == k)) for k in ("TERM", "TIMELINE")}
    n_quote = sum(1 for p in pls if p.frame.item.kind == "QUOTE")
    assert sum(1 for p in pls if p.frame.item.kind == "TIMELINE") > 5      # nền + chuỗi vạch chạy
    logs = []
    out = ov.use_remotion(s, pls, st, (320, 180), 30, logs.append)
    clips = [p for p in out if p.clip is not None]
    assert sorted(p.frame.item.kind for p in clips) == ["TERM", "TIMELINE"]
    for p in clips:
        assert (p.start, p.end) == pytest.approx(before[p.frame.item.kind])
        assert p.layer == "main" and p.motion == "none" and p.fade_in == 0 and p.fade_out == 0
        assert p.clip.parent == tmp_path / "_capcut_draft_studio" / "remotion"
        assert p.clip.is_file()
    assert sum(1 for p in out if p.frame.item.kind == "QUOTE") == n_quote
    assert not [p for p in out if p.frame.item.kind in ("TERM", "TIMELINE") and p.clip is None]
    assert any("2 mục (TERM, TIMELINE) dùng clip Remotion" in m for m in logs)
    # PNG chỉ vẽ cho phần còn lại
    n = ov.write_pngs(out, tmp_path / "ov", 320, 180, st, lambda m: None)
    assert all(p.png is None for p in clips) and n > 0


def test_failed_clip_keeps_pillow_parts(tmp_path, monkeypatch):
    _fake_render(monkeypatch, fail_kinds=("TIMELINE",))
    plan, st, pls, s = _sched(tmp_path)
    n_tl = sum(1 for p in pls if p.frame.item.kind == "TIMELINE")
    out = ov.use_remotion(s, pls, st, (320, 180), 30, lambda m: None)
    assert [p.frame.item.kind for p in out if p.clip is not None] == ["TERM"]
    assert sum(1 for p in out if p.frame.item.kind == "TIMELINE") == n_tl


def test_disabled_never_touches_remotion(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("không được gọi Remotion khi tắt")
    monkeypatch.setattr(rm, "render_jobs", boom)
    monkeypatch.setattr(rm, "status", boom)
    plan, st, pls, s = _sched(tmp_path, enable=False)
    assert ov.use_remotion(s, pls, st, (320, 180), 30) is pls
    assert ov.remotion_kinds(s) == ()


def test_cache_hit_needs_no_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "status", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    p = rm.make_props(ITEMS[0], ov.OverlayStyle(), (64, 36), 10, 1.0)
    clip = tmp_path / "rm_term_x.mov"
    clip.write_bytes(b"x")
    os.utime(clip, (1, 1))
    res = rm.render_jobs([rm.Job("TERM", 1, p, clip)], log=lambda m: None)
    assert res == {clip: True} and clip.stat().st_mtime > 1000     # được 'chạm' để không bị dọn


def test_not_ready_warns_and_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("CDS_REMOTION_HOME", str(tmp_path / "chua-cai"))
    p = rm.make_props(ITEMS[0], ov.OverlayStyle(), (64, 36), 10, 1.0)
    logs = []
    res = rm.render_jobs([rm.Job("TERM", 1, p, tmp_path / "c" / "a.mov")], log=logs.append)
    assert list(res.values()) == [False]
    assert any(m.startswith("[WARN] Remotion chưa sẵn sàng") and "Pillow" in m for m in logs)


def test_status_explains_missing_node_and_install_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("CDS_REMOTION_HOME", str(tmp_path / "h"))
    monkeypatch.setattr(rm, "find_node", lambda: None)
    st = rm.status()
    assert not st.ready and "Node.js" in st.text() and "nodejs.org" in st.text()
    with pytest.raises(RuntimeError, match="nodejs.org"):
        rm.install(log=lambda m: None)


def test_prune_cache_keeps_used_and_recent(tmp_path):
    used, old, part = (tmp_path / n for n in ("rm_a.mov", "rm_b.mov", "rm_c.mov.part.mov"))
    for f in (used, old, part):
        f.write_bytes(b"x")
        os.utime(f, (1, 1))
    assert rm.prune_cache(tmp_path, {used.resolve()}) == 2
    assert used.exists() and not old.exists() and not part.exists()


# --------------------------------------------------------------------------- #
# engine đi kèm
# --------------------------------------------------------------------------- #
def test_engine_bundled_and_pinned():
    assert rm.source_dir() == ENGINE
    pkg = json.loads((ENGINE / "package.json").read_text(encoding="utf-8"))
    for name, ver in pkg["dependencies"].items():
        assert ver[0].isdigit(), f"{name} phải ghim đúng phiên bản"
    lock = json.loads((ENGINE / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    # bộ dựng khung của Remotion cho cả Windows và macOS nằm trong lock
    assert "node_modules/@remotion/compositor-win32-x64-msvc" in lock
    assert "node_modules/@remotion/compositor-darwin-arm64" in lock
    for f in ("render.mjs", "src/index.js", "src/Root.jsx", "src/Term.jsx", "src/Timeline.jsx",
              "src/fonts.js"):
        assert (ENGINE / f).is_file()
    fonts = rm.fonts_dir()
    assert fonts and all((fonts / n).is_file() for n in rm.FONT_FILES)


def test_sync_source_copies_code_and_fonts_once(tmp_path):
    h = tmp_path / "home"
    assert rm.sync_source(h) is True
    for n in rm.FONT_FILES + ("eb-garamond-greek-600-normal.woff2",):
        assert (h / "public" / "fonts" / n).is_file()
    assert (h / "src" / "Term.jsx").is_file() and (h / "package-lock.json").is_file()
    assert rm.sync_source(h) is False                     # không đổi → không chép lại


def test_settings_key_persisted():
    from capcut_draft_studio.ui.app import OTHER_BOOLS
    assert "enable_remotion" in config.DEFAULT_CHANNEL_KEYS
    assert OTHER_BOOLS["enable_remotion"] is False
    assert Settings(input_dir=Path("."), channel_dir=Path("."), draft_name="d",
                    capcut_drafts=Path(".")).enable_remotion is False


# --------------------------------------------------------------------------- #
# draft CapCut + mp4
# --------------------------------------------------------------------------- #
OV_ROWS = [["scene", "type", "text", "sub", "label", "until"],
           ["1", "TERM", "Nephilim | נְפִילִים", "the fallen ones", "Hebrew", ""],
           ["2", "TIMELINE", "1446 BC | *586 BC* | 70 AD", "", "Key dates", "3"]]


def test_draft_places_clip_on_chu_main_and_splits_around_ad(tmp_path, monkeypatch):
    _real_pycapcut(monkeypatch)
    _fake_render(monkeypatch)
    _project(tmp_path, n=4, sec=2.0)
    ad = _mp4(tmp_path / "ad.mp4", 2.0)
    _write_csv(tmp_path / "overlay.csv", OV_ROWS)
    from capcut_draft_studio.capcut_engine import build, clip_len
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", register_root_meta=False,
                 enable_claim=False, enable_subtitles=False, gap_mode="fixed",
                 enable_ad=True, ad_path=ad, ad_after="2", enable_remotion=True)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    d = json.loads((build(s, assets, plan, lambda m: None) / "draft_content.json")
                   .read_text(encoding="utf-8"))
    mats = {m["id"]: m for m in d["materials"]["videos"]}
    tracks = {t["name"]: t for t in d["tracks"]}
    movs = [(st, ln, x) for st, ln, x in _segs(tracks["chu_main"])
            if mats[x["material_id"]]["path"].endswith(".mov")]
    assert len(movs) == 3                                  # TERM + TIMELINE cắt đôi quanh quảng cáo
    for _, _, x in movs:
        assert x["volume"] == 0.0 and not x.get("common_keyframes")
        assert Path(mats[x["material_id"]]["path"]).is_file()
    term, tl1, tl2 = movs
    at, ln = plan[1].end, clip_len(ad, "quảng cáo")
    assert tl1[0] + tl1[1] == pytest.approx(at, abs=1e-3)
    assert tl2[0] == pytest.approx(at + ln, abs=1e-3)
    # mẩu sau quảng cáo đọc clip từ đúng chỗ mẩu trước dừng
    assert tl2[2]["source_timerange"]["start"] == tl1[2]["source_timerange"]["duration"]
    assert term[2]["source_timerange"]["start"] == 0
    # không còn ảnh PNG nào của TERM/TIMELINE
    pngs = [mats[x["material_id"]]["path"] for t in tracks.values() if t["name"].startswith("chu_")
            for x in t["segments"] if mats.get(x["material_id"])]
    pngs = [p for p in pngs if p.endswith(".png")]
    assert not [p for p in pngs if "_term_" in p or "_timeline_" in p]


def test_render_composites_clip_into_mp4(tmp_path, monkeypatch):
    ff = _ffmpeg()
    calls = []
    _fake_render(monkeypatch, calls=calls)
    Image = _project(tmp_path, n=3, sec=2.0)
    for i in range(1, 4):
        Image.new("RGB", (64, 36), (230, 230, 230)).save(tmp_path / "Images" / f"{i}.png")
    _write_csv(tmp_path / "overlay.csv", [["2", "TERM", "Logos | λόγος", "word", "Greek"]])
    from capcut_draft_studio import render
    from capcut_draft_studio.media import scan_assets, validate
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path / "CH", draft_name="d",
                 capcut_drafts=tmp_path / "drafts", width=320, height=180, fps=10,
                 enable_claim=False, enable_logo=False, enable_bgm=False,
                 enable_subtitles=False, enable_transition=False, image_anim="off",
                 gap_mode="fixed", scene_gap=0.0, render_preset="veryfast", enable_remotion=True)
    assets = scan_assets(s, lambda m: None)
    plan = validate(s, assets, lambda m: None)
    out = tmp_path / "out.mp4"
    render.Renderer(render.RenderJob("t", s, assets, plan, out), log=lambda m: None).run()
    assert [(c.kind, c.props["width"], c.props["fps"]) for c in calls] == [("TERM", 320, 10)]

    def luma(t, x, y):
        raw = subprocess.run([ff, "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(out),
                              "-frames:v", "1", "-vf", f"crop=20:10:{x}:{y},scale=1:1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        return raw[0]

    assert luma(1.0, 150, 85) > 180                      # cảnh 1: không có đồ họa
    assert luma(plan[1].start + 1.0, 150, 85) < 80       # cảnh 2: hộp tối của clip (alpha 0,85)
    assert luma(plan[1].start + 1.0, 10, 10) > 180       # ngoài hộp: nền trong suốt, ảnh vẫn sáng
    assert luma(plan[2].start + 1.0, 150, 85) > 180


def test_scene_args_clip_seeks_when_started_in_previous_scene(tmp_path):
    from capcut_draft_studio import render

    class R:
        scene_args = render.Renderer.scene_args
        scene_overlays = render.Renderer.scene_overlays
        _overlay_filters = render.Renderer._overlay_filters
        _crop = render.Renderer._crop
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
    clip = tmp_path / "rm.mov"
    pl = ov.Placement(ov.Frame(ov.OverlayItem(1, "TIMELINE", "a | b")), plan[0].start + 1.0,
                      plan[1].end - plan[0].start - 1.0, "main", 0.0, 0.0, 1, motion="none", clip=clip)
    a1 = R(plan, [pl]).scene_args(0, plan[0], Path("o.mp4"))
    a2 = R(plan, [pl]).scene_args(1, plan[1], Path("o.mp4"))
    assert str(clip) in a1 and str(clip) in a2
    i1 = a1.index(str(clip))
    assert a1[i1 - 2] != "-ss"                            # cảnh đầu: clip bắt đầu ở 1,0 s
    c1 = a1[a1.index("-filter_complex") + 1]
    assert "setpts=PTS-STARTPTS+1.0000/TB" in c1 and "overlay=0:0:eof_action=pass" in c1
    i2 = a2.index(str(clip))
    skip = plan[1].start - pl.start
    assert a2[i2 - 3:i2 - 1] == ["-ss", f"{skip:.4f}"]   # cảnh sau: nhảy vào giữa clip
    assert "setpts=PTS-STARTPTS+0.0000/TB" in a2[a2.index("-filter_complex") + 1]


def test_cli_remotion_status(monkeypatch, tmp_path, capsys):
    from capcut_draft_studio import cli
    monkeypatch.setenv("CDS_REMOTION_HOME", str(tmp_path / "h"))
    assert cli.main(["remotion-status"]) == 1
    assert "Remotion" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Remotion thật (chỉ chạy khi engine đã cài: CDS_REMOTION_HOME trỏ tới bản đã cài)
# --------------------------------------------------------------------------- #
def test_real_remotion_clip_has_alpha_and_length(tmp_path):
    if not os.environ.get("CDS_REMOTION_HOME") or not rm.status().ready:
        pytest.skip("Remotion chưa cài trong môi trường test")
    ff = _ffmpeg()
    st = ov.OverlayStyle()
    p = rm.make_props(ITEMS[0], st, (480, 270), 30, 1.5)
    out = tmp_path / rm.clip_name("TERM", p, rm.source_hash())
    logs = []
    res = rm.render_jobs([rm.Job("TERM", 1, p, out)], log=logs.append)
    assert res == {out: True}, logs
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_frames",
                                      "-of", "json", str(out)], capture_output=True, text=True).stdout)
    v = info["streams"][0]
    assert v["codec_name"] == "prores" and v["pix_fmt"].startswith("yuva444")
    assert (v["width"], v["height"], int(v["nb_frames"])) == (480, 270, p["frames"])
    from PIL import Image
    frame = tmp_path / "f.png"
    subprocess.run([ff, "-v", "error", "-y", "-ss", "1.0", "-i", str(out), "-frames:v", "1",
                    "-pix_fmt", "rgba", str(frame)], check=True)
    a = Image.open(frame).getchannel("A")
    assert a.getpixel((5, 5)) == 0                        # góc trống trong suốt
    assert a.getextrema()[1] == 255                       # thẻ hiện rõ
    last = tmp_path / "l.png"
    subprocess.run([ff, "-v", "error", "-y", "-sseof", "-0.04", "-i", str(out), "-frames:v", "1",
                    "-pix_fmt", "rgba", str(last)], check=True)
    assert Image.open(last).getchannel("A").getextrema()[1] == 0   # đã tắt hẳn ở cuối
