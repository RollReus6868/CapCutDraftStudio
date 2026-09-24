"""Test cho các tính năng thêm ở 0.4.0: khoảng nghỉ, âm lượng video,
bóng đổ phụ đề, engine render và bộ cập nhật."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from capcut_draft_studio import media, render, styles, updater
from capcut_draft_studio.models import Assets, ScenePlan, Settings
from capcut_draft_studio.subtitles import build_srt


# --------------------------------------------------------------------------- #
# tiện ích
# --------------------------------------------------------------------------- #
def make_settings(tmp_path: Path, **kw) -> Settings:
    (tmp_path / "in").mkdir(exist_ok=True)
    (tmp_path / "ch").mkdir(exist_ok=True)
    (tmp_path / "drafts").mkdir(exist_ok=True)
    base = dict(input_dir=tmp_path / "in", channel_dir=tmp_path / "ch",
                draft_name="test", capcut_drafts=tmp_path / "drafts")
    base.update(kw)
    return Settings(**base)


def assets_with(audios, videos=None, images=None) -> Assets:
    return Assets(audios=audios, videos=videos or {}, images=images or {})


def patch_durations(monkeypatch, table: dict[str, float]):
    def fake(path):
        return table[Path(path).name]
    monkeypatch.setattr(media, "media_duration_sec", fake)


# --------------------------------------------------------------------------- #
# ScenePlan
# --------------------------------------------------------------------------- #
def test_scene_plan_gap_properties():
    p = ScenePlan(1, Path("1.mp3"), 3.0, "IMAGE", Path("1.jpg"), start=10.0, gap=0.4)
    assert p.slot_duration == pytest.approx(3.4)
    assert p.audio_end == pytest.approx(13.0)
    assert p.end == pytest.approx(13.4)


def test_scene_plan_without_gap_matches_old_behaviour():
    p = ScenePlan(1, Path("1.mp3"), 3.0, "IMAGE", Path("1.jpg"), start=2.0)
    assert p.end == p.audio_end == pytest.approx(5.0)
    assert p.slot_duration == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# validate() với khoảng nghỉ
# --------------------------------------------------------------------------- #
def test_gap_shifts_start_times_and_last_scene_has_no_gap(tmp_path, monkeypatch):
    patch_durations(monkeypatch, {"1.mp3": 2.0, "2.mp3": 3.0, "3.mp3": 1.0})
    s = make_settings(tmp_path, scene_gap=0.5)
    a = assets_with({1: Path("1.mp3"), 2: Path("2.mp3"), 3: Path("3.mp3")},
                    images={1: Path("1.jpg"), 2: Path("2.jpg"), 3: Path("3.jpg")})
    plan = media.validate(s, a, log=lambda m: None)
    assert [p.gap for p in plan] == [0.5, 0.5, 0.0]
    assert [round(p.start, 3) for p in plan] == [0.0, 2.5, 6.0]
    assert plan[-1].end == pytest.approx(7.0)


def test_gap_zero_is_identical_to_old_layout(tmp_path, monkeypatch):
    patch_durations(monkeypatch, {"1.mp3": 2.0, "2.mp3": 3.0})
    s = make_settings(tmp_path, scene_gap=0.0)
    a = assets_with({1: Path("1.mp3"), 2: Path("2.mp3")},
                    images={1: Path("1.jpg"), 2: Path("2.jpg")})
    plan = media.validate(s, a, log=lambda m: None)
    assert [p.start for p in plan] == [0.0, 2.0]
    assert plan[-1].end == pytest.approx(5.0)


def test_gap_makes_mode_decision_use_the_longer_slot(tmp_path, monkeypatch):
    """Video 2.2s vừa đủ cho audio 2.0s, nhưng thêm 0.5s nghỉ thì phải làm chậm."""
    patch_durations(monkeypatch, {"1.mp3": 2.0, "1.mp4": 2.2, "2.mp3": 1.0})
    a = assets_with({1: Path("1.mp3"), 2: Path("2.mp3")},
                    videos={1: Path("1.mp4")}, images={2: Path("2.jpg")})

    no_gap = media.validate(make_settings(tmp_path, scene_gap=0.0), a, log=lambda m: None)
    assert no_gap[0].mode == "CUT"

    with_gap = media.validate(make_settings(tmp_path, scene_gap=0.5), a, log=lambda m: None)
    assert with_gap[0].mode == "SLOW"
    assert with_gap[0].speed == pytest.approx(2.2 / 2.5)


def test_gap_can_push_a_scene_into_error(tmp_path, monkeypatch):
    patch_durations(monkeypatch, {"1.mp3": 2.0, "1.mp4": 1.6})
    a = assets_with({1: Path("1.mp3")}, videos={1: Path("1.mp4")})
    # cảnh duy nhất -> gap = 0 -> 1.6/2.0 = 0.8 >= min_speed 0.75 -> OK
    plan = media.validate(make_settings(tmp_path, scene_gap=1.0), a, log=lambda m: None)
    assert plan[0].mode == "SLOW"


def test_subtitles_stop_at_voice_end_not_at_gap_end(tmp_path):
    s = make_settings(tmp_path, scene_gap=0.6, sub_max_words=50)
    (tmp_path / "in" / "Texts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "in" / "Texts" / "1.txt").write_text("Một câu duy nhất.", encoding="utf-8")
    plan = [ScenePlan(1, Path("1.mp3"), 2.0, "IMAGE", Path("1.jpg"), start=0.0, gap=0.6)]
    out = tmp_path / "subs.srt"
    assert build_srt(s, plan, out, log=lambda m: None) == 1
    body = out.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:02,000" in body


# --------------------------------------------------------------------------- #
# bóng đổ phụ đề
# --------------------------------------------------------------------------- #
def test_shadow_spec_defaults_to_ninety_percent(tmp_path):
    spec = styles.shadow_spec(make_settings(tmp_path))
    assert spec["alpha"] == pytest.approx(0.9)
    # khớp đúng giá trị CapCut ghi trong draft thật
    assert spec["point"]["x"] == pytest.approx(0.6363961, abs=1e-6)
    assert spec["point"]["y"] == pytest.approx(-0.6363961, abs=1e-6)


def test_shadow_spec_disabled(tmp_path):
    assert styles.shadow_spec(make_settings(tmp_path, sub_shadow=False)) is None
    assert styles.default_subtitle_style(make_settings(tmp_path, sub_shadow=False)) is None


def _draft_with_subtitle(tmp_path: Path) -> Path:
    draft = tmp_path / "draft"
    draft.mkdir()
    (draft / "draft_content.json").write_text(json.dumps({
        "tracks": [{"type": "text", "name": "subtitles",
                    "segments": [{"material_id": "m1"}]}],
        "materials": {"texts": [{"id": "m1", "content": json.dumps({"styles": [{}]})}]},
    }), encoding="utf-8")
    return draft


def test_inject_writes_both_shadow_schemas(tmp_path):
    draft = _draft_with_subtitle(tmp_path)
    s = make_settings(tmp_path, sub_shadow_alpha=0.9)
    changed = styles.inject_subtitle_style(draft, styles.default_subtitle_style(s),
                                           log=lambda m: None)
    assert changed == 1
    data = json.loads((draft / "draft_content.json").read_text(encoding="utf-8"))
    mat = data["materials"]["texts"][0]
    assert mat["has_shadow"] is True
    assert mat["shadow_alpha"] == pytest.approx(0.9)
    content = json.loads(mat["content"])
    shadow = content["styles"][0]["shadows"][0]
    assert shadow["alpha"] == pytest.approx(0.9)
    assert shadow["content"]["solid"]["color"] == [0.0, 0.0, 0.0]


def test_merge_shadow_keeps_harvested_style_fields(tmp_path):
    harvested = {"style": {"size": 12.0, "bold": True}, "shadow": {"legacy": 1}}
    merged = styles.merge_shadow(harvested, make_settings(tmp_path))
    assert merged["style"]["size"] == 12.0
    assert "shadow_spec" in merged
    assert "shadow" not in merged     # bản mô tả mới thay bản harvest cũ


# --------------------------------------------------------------------------- #
# render — chỉ kiểm tra phần dựng lệnh, không chạy ffmpeg
# --------------------------------------------------------------------------- #
def test_target_size_keeps_project_or_scales_short_side(tmp_path):
    assert render.target_size(make_settings(tmp_path)) == (1920, 1080)
    assert render.target_size(make_settings(tmp_path, render_res="720")) == (1280, 720)
    portrait = make_settings(tmp_path, width=1080, height=1920, render_res="720")
    assert render.target_size(portrait) == (720, 1280)


def test_target_size_is_always_even(tmp_path):
    s = make_settings(tmp_path, width=1000, height=563, render_res="481")
    w, h = render.target_size(s)
    assert w % 2 == 0 and h % 2 == 0


def test_target_fps_falls_back_to_project(tmp_path):
    assert render.target_fps(make_settings(tmp_path, fps=25)) == 25
    assert render.target_fps(make_settings(tmp_path, fps=25, render_fps=60)) == 60


def test_atempo_chain():
    assert render.atempo_chain(1.0) is None
    assert render.atempo_chain(0.8) == "atempo=0.800000"
    chain = render.atempo_chain(0.2)
    assert chain.startswith("atempo=0.5,atempo=0.5")
    assert chain.count("atempo") >= 3


def test_kenburns_zoom_only_has_no_position_terms():
    f = render.kenburns_filter("zoom_in", 3.0, 30, 1920, 1080)
    assert "zoompan" in f and "position" not in f
    assert "z='(1.000000+(0.080000)*(on/89))'" in f


def test_kenburns_pan_keeps_image_oversized():
    """Hiệu ứng có trượt phải phóng nền, nếu không sẽ lộ viền đen."""
    f = render.kenburns_filter("pan_left", 2.0, 30, 1920, 1080)
    assert "zoompan" in f
    assert "scale=7680:4320" in f          # ảnh nội bộ phóng 4 lần
    assert "z='(1.120000+(0.000000)*" in f


def test_kenburns_off_is_plain_fill():
    f = render.kenburns_filter("off", 2.0, 30, 1280, 720)
    assert "zoompan" not in f
    assert "crop=1280:720" in f


def test_video_scene_filter_speed():
    assert "setpts=PTS/0.800000" in render.video_scene_filter(0.8, 30, 1280, 720)
    assert "setpts" not in render.video_scene_filter(1.0, 30, 1280, 720)


def test_subtitle_force_style_maps_alpha_to_ass_transparency(tmp_path):
    style = render.subtitle_force_style(make_settings(tmp_path, sub_shadow_alpha=0.9), 1080)
    assert "BackColour=&H19000000" in style      # (1-0.9)*255 ≈ 25.5 -> 0x19
    assert "Shadow=2" in style
    off = render.subtitle_force_style(make_settings(tmp_path, sub_shadow=False), 1080)
    assert "Shadow=0" in off


def test_overlay_position_maps_capcut_coordinates():
    x, y = render.overlay_position(0.0, 0.0, 1920, 1080)
    assert x.startswith("960.00") and y.startswith("540.00")
    # x dương = sang phải, y dương = LÊN trên (y pixel nhỏ hơn)
    x2, y2 = render.overlay_position(0.949, -0.91, 1920, 1080)
    assert float(x2.split("-")[0]) > 960
    assert float(y2.split("-")[0]) > 540


def test_quality_args_switch_by_encoder():
    assert render.quality_args("libx264", 20, "medium") == \
        ["-crf", "20", "-preset", "medium"]
    assert "-cq" in render.quality_args("h264_nvenc", 20, "medium")
    assert "-q:v" in render.quality_args("h264_videotoolbox", 20, "medium")


def test_ass_escape_handles_windows_paths():
    out = render.ass_escape(Path("C:/Videos/_render/a b.srt"))
    assert out == "C\\:/Videos/_render/a b.srt"


def test_default_out_path_sanitises_name(tmp_path):
    s = make_settings(tmp_path)
    assert render.default_out_path(s, 'a:b/c').name == "a_b_c.mp4"


class _FakeRenderer:
    """Dùng lại logic dựng lệnh của Renderer mà không cần ffmpeg."""

    def __init__(self, plan, trans, dur=0.0):
        self.job = type("J", (), {"plan": plan, "duration": dur})()
        self.trans = trans
        self.s = type("S", (), {"render_crf": 20, "render_preset": "medium"})()
        self.encoder = "libx264"

    concat_args = render.Renderer.concat_args


def test_concat_offsets_match_scene_starts():
    plan = [ScenePlan(i, Path(f"{i}.mp3"), 2.0, "IMAGE", Path(f"{i}.jpg"),
                      start=i * 2.4, gap=0.4 if i < 2 else 0.0) for i in range(3)]
    args = _FakeRenderer(plan, trans=0.5).concat_args(
        [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")], Path("out.mp4"))
    chain = args[args.index("-filter_complex") + 1]
    assert "offset=2.4000" in chain
    assert "offset=4.8000" in chain
    assert chain.endswith("[vout]")


def test_concat_without_transition_uses_plain_concat():
    plan = [ScenePlan(i, Path(f"{i}.mp3"), 2.0, "IMAGE", Path(f"{i}.jpg")) for i in range(2)]
    args = _FakeRenderer(plan, trans=0.0).concat_args(
        [Path("a.mp4"), Path("b.mp4")], Path("out.mp4"))
    chain = args[args.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=0" in chain
    assert "xfade" not in chain


def test_fmt_eta_is_human_readable():
    assert render.fmt_eta(0) == "—"
    assert render.fmt_eta(45) == "45 giây"
    assert render.fmt_eta(125) == "2 phút 05 giây"
    assert render.fmt_eta(3700).startswith("1 giờ")


# --------------------------------------------------------------------------- #
# updater
# --------------------------------------------------------------------------- #
def test_version_compare():
    assert updater.parse_version("v0.4.1") == (0, 4, 1)
    assert updater.is_newer("v0.4.1", "0.4.0")
    assert updater.is_newer("1.0", "0.9.9")
    assert not updater.is_newer("0.4.0", "0.4.0")
    assert not updater.is_newer("0.3.9", "0.4.0")


def test_parse_sums_reads_sha256sum_format():
    text = ("a" * 64 + "  CapCutDraftStudio-0.4.1-windows-setup.exe\n"
            + "b" * 64 + " *CapCutDraftStudio-0.4.1-macos.dmg\n"
            "khong-phai-dong-hop-le\n")
    sums = updater.parse_sums(text)
    assert sums["CapCutDraftStudio-0.4.1-windows-setup.exe"] == "a" * 64
    assert sums["CapCutDraftStudio-0.4.1-macos.dmg"] == "b" * 64
    assert len(sums) == 2


def test_verify_package_requires_exact_digest(tmp_path):
    f = tmp_path / "pkg.bin"
    f.write_bytes(b"xin chao")
    digest = updater.sha256_file(f)
    assert updater.verify_package(f, digest)
    assert updater.verify_package(f, digest.upper())
    assert not updater.verify_package(f, "0" * 64)
    assert not updater.verify_package(f, "")


# --------------------------------------------------------------------------- #
# thư mục dữ liệu — bản cài trong Program Files là CHỈ ĐỌC
# --------------------------------------------------------------------------- #
def test_data_dir_uses_install_folder_when_writable(tmp_path, monkeypatch):
    from capcut_draft_studio.ui import app as uiapp
    monkeypatch.setattr(uiapp, "app_dir", lambda: tmp_path)
    assert uiapp.data_dir() == tmp_path


def test_data_dir_falls_back_when_install_folder_is_read_only(tmp_path, monkeypatch):
    """Đúng tình huống gây crash 0.4.0: C:\\Program Files không ghi được."""
    from capcut_draft_studio.ui import app as uiapp
    readonly = tmp_path / "Program Files" / "CapCutDraftStudio"
    userdata = tmp_path / "LocalAppData" / "CapCutDraftStudio"
    monkeypatch.setattr(uiapp, "app_dir", lambda: readonly)
    monkeypatch.setattr(uiapp, "user_data_dir", lambda: userdata)
    monkeypatch.setattr(uiapp, "_is_writable", lambda p: p != readonly)
    assert uiapp.data_dir() == userdata


def test_data_dir_last_resort_is_temp(tmp_path, monkeypatch):
    import tempfile
    from capcut_draft_studio.ui import app as uiapp
    monkeypatch.setattr(uiapp, "app_dir", lambda: tmp_path / "ro")
    monkeypatch.setattr(uiapp, "user_data_dir", lambda: tmp_path / "ro2")
    monkeypatch.setattr(uiapp, "_is_writable", lambda p: False)
    assert uiapp.data_dir() == Path(tempfile.gettempdir()) / uiapp.APP_SLUG


def test_is_writable_detects_a_real_read_only_folder(tmp_path):
    import os
    import stat
    from capcut_draft_studio.ui.app import _is_writable
    ok = tmp_path / "ghi-duoc"
    assert _is_writable(ok)
    if os.name == "nt" or os.geteuid() == 0:
        return          # root/Windows bỏ qua quyền thư mục, không test được
    locked = tmp_path / "chi-doc"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert not _is_writable(locked)
    finally:
        locked.chmod(stat.S_IRWXU)


# --------------------------------------------------------------------------- #
# xuất qua CapCut — phần chạy được ngoài Windows
# --------------------------------------------------------------------------- #
class _FakeWindow:
    def __init__(self, name="", cls="", pid=1234):
        self.Name = name
        self.ClassName = cls
        self.ProcessId = pid


def test_window_state_reads_class_not_title():
    """Đúng chỗ pycapcut sai: bản quốc tế có tiêu đề 'CapCut', không phải tiếng Trung."""
    from capcut_draft_studio import capcut_export as ce
    assert ce._window_state(_FakeWindow("CapCut", "Qt5152HomePageWindow")) == "home"
    assert ce._window_state(_FakeWindow("CapCut", "Qt5152MainWindow")) == "edit"
    assert ce._window_state(_FakeWindow("CapCut专业版", "HomePage")) == "home"
    assert ce._window_state(_FakeWindow("Notepad", "Notepad")) == ""


def test_is_capcut_window_accepts_when_process_unknown(monkeypatch):
    from capcut_draft_studio import capcut_export as ce
    monkeypatch.setattr(ce, "_process_name", lambda pid: "")
    assert ce._is_capcut_window(_FakeWindow("CapCut", "HomePageWindow"))
    monkeypatch.setattr(ce, "_process_name", lambda pid: "chrome.exe")
    assert not ce._is_capcut_window(_FakeWindow("CapCut", "HomePageWindow"))
    monkeypatch.setattr(ce, "_process_name", lambda pid: "CapCut.exe")
    assert ce._is_capcut_window(_FakeWindow("bất kỳ", "MainWindow"))


def test_available_explains_itself_off_windows():
    from capcut_draft_studio import capcut_export as ce
    ok, why = ce.available()
    if os.name != "nt":
        assert not ok and "Windows" in why


def test_diagnose_never_raises():
    from capcut_draft_studio import capcut_export as ce
    report = ce.diagnose()
    assert "CapCut.exe" in report and "uiautomation" in report


def test_resolution_and_fps_maps():
    from capcut_draft_studio import capcut_export as ce
    assert ce.RES_MAP["1080"] == "RES_1080P"
    assert ce.FPS_MAP[60] == "FR_60"


# --------------------------------------------------------------------------- #
# bảng màu theo ngữ nghĩa
# --------------------------------------------------------------------------- #
def test_every_section_mode_and_tile_has_a_colour_in_both_themes():
    from capcut_draft_studio.ui import theme as th
    for table in (th.SECTION_COLORS, th.MODE_COLORS, th.TILE_COLORS, th.STATE_COLORS):
        for key, value in table.items():
            assert set(value) == {"dark", "light"}, key
            for variant in value.values():
                assert re.fullmatch(r"#[0-9a-fA-F]{6}", variant), (key, variant)


def test_section_colours_cover_every_nav_page():
    from capcut_draft_studio.ui import theme as th
    from capcut_draft_studio.ui.app import NAV
    for key, _ in NAV:
        assert key in th.SECTION_COLORS, key
        assert key in th.SECTION_ICONS, key


def test_blend_moves_towards_the_foreground():
    from capcut_draft_studio.ui.theme import blend
    assert blend("#ffffff", "#000000", 0.0) == "#000000"
    assert blend("#ffffff", "#000000", 1.0) == "#ffffff"
    assert blend("#ffffff", "#000000", 0.5) == "#808080"


def test_check_refuses_release_without_checksums(monkeypatch):
    monkeypatch.setattr(updater, "fetch_manifest", lambda url, timeout=10: {
        "tag_name": "v9.9.9",
        "assets": [{"name": "setup.exe", "browser_download_url": "http://x/setup.exe",
                    "size": 10}],
    })
    assert updater.check("0.4.0") is None
