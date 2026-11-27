"""0.7.1: phông EB Garamond của tool có chữ Hy Lạp — bản vẽ thường (Pillow) không còn
ra ô vuông ở thẻ từ gốc / trích dẫn tiếng Hy Lạp; chữ Latin, Việt giữ nguyên."""
from __future__ import annotations

import pytest

from capcut_draft_studio import overlays as ov
from capcut_draft_studio.overlay_draw import FONT_FILES, Frame, OverlayStyle, _font_path, font, render_frame

GREEK = "ὁ λόγος σὰρξ ἐγένετο Ἰησοῦς Χριστός"


@pytest.mark.parametrize("role", ["serif_semibold", "serif_italic", "serif_italic_med"])
def test_serif_fonts_cover_greek_and_vietnamese(role):
    from fontTools.ttLib import TTFont
    path = _font_path(role)
    assert path, FONT_FILES[role]
    cmap = TTFont(path).getBestCmap()
    for ch in GREEK + "λόγος ạ ế ữ Đ":
        if not ch.isspace():
            assert ord(ch) in cmap, f"{FONT_FILES[role]} thiếu {ch!r}"


@pytest.mark.parametrize("role", ["serif_semibold", "serif_italic"])
def test_greek_letters_are_not_the_missing_glyph(role):
    f = font(role, 60)
    missing = f.getmask("￿").getbbox()
    for ch in "λόγοςὁἐ":
        assert f.getmask(ch).getbbox() != missing or f.getmask(ch).size != f.getmask("￿").size


def test_greek_term_draws_inside_frame():
    it = ov.OverlayItem(1, "TERM", "Logos | λόγος", "ὁ λόγος σὰρξ ἐγένετο", "Greek")
    im = render_frame(Frame(it), 1920, 1080, OverlayStyle())
    box = im.getchannel("A").getbbox()
    assert box and box[2] <= 1920 and box[3] <= 1080
