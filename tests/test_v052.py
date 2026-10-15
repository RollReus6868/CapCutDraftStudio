"""0.5.2: đọc Excel không có dòng tiêu đề (cột A = STT, cột B = lời thoại),
và intro/outro."""
from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from capcut_draft_studio import config  # noqa: E402
from capcut_draft_studio.models import Settings  # noqa: E402
from capcut_draft_studio.subtitles import (_excel_texts, _resolve_col,  # noqa: E402
                                           excel_columns, guess_excel_columns)


def _xlsx(tmp_path: Path, name: str, rows) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(list(r))
    p = tmp_path / name
    wb.save(p)
    return p


def test_no_header_defaults_to_a_stt_b_script(tmp_path):
    # đúng dạng file phân cảnh mẫu: dòng 0 là tiêu đề video, không có dòng tiêu đề cột
    p = _xlsx(tmp_path, "phan_canh.xlsx", [
        ("0", "God_s_Promise_for_Your_Old_Age"),
        ("1", "Most of the promises we love in the Bible are about the beginning."),
        ("2", "A land. A plan for your future."),
    ])
    out = _excel_texts(p, "", "")
    assert out[1].startswith("Most of the promises")
    assert out[2] == "A land. A plan for your future."
    sheets, headers = excel_columns(p)
    assert headers == ["Cột A", "Cột B"]
    assert guess_excel_columns(headers) == ("Cột B", "Cột A")


def test_stale_column_names_fall_back_to_defaults(tmp_path):
    p = _xlsx(tmp_path, "x.xlsx", [(1, "One"), (2, "Two")])
    for script, scene in (("Lời thoại", "STT"), ("B", "A"), ("2", "1"), ("Cột B", "Cột A")):
        assert _excel_texts(p, script, scene) == {1: "One", 2: "Two"}, (script, scene)


def test_header_rows_still_found_by_name(tmp_path):
    p = _xlsx(tmp_path, "h.xlsx", [("Scene", "Ghi chú", "Script"), (1, "x", "Hello"),
                                   (2, "y", "World")])
    assert _excel_texts(p, "", "") == {1: "Hello", 2: "World"}
    p = _xlsx(tmp_path, "v.xlsx", [("STT", "Lời thoại"), (1, "Xin chào"), (2, "Tạm biệt")])
    assert _excel_texts(p, "", "") == {1: "Xin chào", 2: "Tạm biệt"}
    assert guess_excel_columns(excel_columns(p)[1]) == ("Lời thoại", "STT")


def test_resolve_col_accepts_letters_and_numbers():
    assert _resolve_col("B", []) == 1
    assert _resolve_col("2", []) == 1
    assert _resolve_col("Cột C", []) == 2
    assert _resolve_col("Script", ["Scene", "Script"]) == 1
    assert _resolve_col("", ["x"]) is None


def test_intro_outro_only_used_when_enabled_and_file_exists(tmp_path):
    clip = tmp_path / "intro.mp4"
    clip.write_bytes(b"x")
    s = Settings(input_dir=tmp_path, channel_dir=tmp_path, draft_name="t",
                 capcut_drafts=tmp_path, intro_path=clip, outro_path=tmp_path / "none.mp4")
    assert s.intro_file() is None          # chưa bật
    s.enable_intro = True
    s.enable_outro = True
    assert s.intro_file() == clip
    assert s.outro_file() is None          # file không tồn tại
    for key in ("enable_intro", "intro_path", "enable_outro", "outro_path"):
        assert key in config.DEFAULT_CHANNEL_KEYS
