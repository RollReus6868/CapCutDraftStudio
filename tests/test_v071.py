"""0.7.1: phông EB Garamond của tool có chữ Hy Lạp — bản vẽ thường (Pillow) không còn
ra ô vuông ở thẻ từ gốc / trích dẫn tiếng Hy Lạp; chữ Latin, Việt giữ nguyên.
Chỉ dùng Pillow (máy build CI không có fontTools)."""
from __future__ import annotations

import pytest

from capcut_draft_studio import overlays as ov
from capcut_draft_studio.overlay_draw import FONT_FILES, Frame, OverlayStyle, _font_path, font, render_frame

GREEK = "ὁλόγοςσὰρξἐγένετοἸησοῦςΧριστός"
MISSING = ""          # vùng riêng của Unicode: không phông nào có → ra glyph thiếu


def _mask(f, ch: str) -> bytes:
    m = f.getmask(ch)
    return bytes(m) + str(m.size).encode()


@pytest.mark.parametrize("role", ["serif_semibold", "serif_italic", "serif_italic_med"])
def test_serif_fonts_draw_greek_and_vietnamese(role):
    assert _font_path(role), FONT_FILES[role]
    f = font(role, 60)
    missing = _mask(f, MISSING)
    for ch in GREEK + "ạếữĐ":
        assert _mask(f, ch) != missing, f"{FONT_FILES[role]} thiếu {ch!r}"


def test_greek_term_draws_inside_frame():
    it = ov.OverlayItem(1, "TERM", "Logos | λόγος", "ὁ λόγος σὰρξ ἐγένετο", "Greek")
    im = render_frame(Frame(it), 1920, 1080, OverlayStyle())
    box = im.getchannel("A").getbbox()
    assert box and box[2] <= 1920 and box[3] <= 1080
