"""Vẽ đồ họa chữ thành ảnh PNG trong suốt đúng cỡ khung (Pillow).

0.6.4:
* chữ to hơn 30 % (`BASE_SIZE`), ô "Cỡ chữ" của người dùng vẫn nhân thêm;
* mỗi đồ họa chia thành PHẦN (`Frame.part`) để chuyển động riêng: hộp trích
  dẫn (box) + chữ đánh máy (text) + tham chiếu (ref); hai cột so sánh; từng
  dòng danh sách; hai thanh khung điện ảnh…;
* chữ đánh máy theo TỪNG KÝ TỰ (`Frame.chars`) với con trỏ (`Frame.caret`);
* *chữ giữa hai dấu sao* được tô màu nhấn (trích dẫn, câu chốt, giấy cổ,
  dòng thời gian, từ khóa);
* thêm 9 kiểu: PLACE, TERM, VS, TIMELINE, KEYWORD, SOURCE, NOTE, CINEMA,
  SUBSCRIBE.

Mọi vị trí tính từ MỘT bố cục cố định cho cả câu, nên lúc đánh máy chữ không
nhảy chỗ, và các phần của cùng một đồ họa luôn khớp nhau.
"""
from __future__ import annotations

import hashlib
import random
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: 0.6.4: cỡ chữ cơ bản to hơn 30 % so với 0.6.0–0.6.3
BASE_SIZE = 1.30


def _hex(c: str, default: str) -> tuple[int, int, int]:
    c = (c or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        c = default.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class OverlayStyle:
    accent: str = "#C9A45C"         # vàng đồng
    stamp: str = "#B3261E"          # đỏ dấu mộc
    box_alpha: float = 0.80
    scale: float = 1.0
    typewriter: bool = True
    #: phụ đề đang bật → nâng nhãn dưới / thẻ chương lên để không đè phụ đề
    subs_on: bool = False

    @classmethod
    def from_settings(cls, s) -> "OverlayStyle":
        return cls(accent=str(getattr(s, "overlay_accent", cls.accent) or cls.accent),
                   stamp=str(getattr(s, "overlay_stamp", cls.stamp) or cls.stamp),
                   box_alpha=max(0.0, min(1.0, float(getattr(s, "overlay_box_alpha", 0.8)))),
                   scale=max(0.5, min(2.0, float(getattr(s, "overlay_scale", 1.0) or 1.0))),
                   typewriter=bool(getattr(s, "overlay_typewriter", True)),
                   subs_on=bool(getattr(s, "enable_subtitles", False)
                                and str(getattr(s, "subtitle_source", "off")) != "off"))

    @property
    def acc(self):
        return _hex(self.accent, "#C9A45C")

    @property
    def red(self):
        return _hex(self.stamp, "#B3261E")

    def key(self) -> str:
        return (f"{self.accent}|{self.stamp}|{self.box_alpha:.3f}|{self.scale:.3f}"
                f"|{int(self.subs_on)}|v064")


WHITE = (246, 241, 232)
CREAM = (226, 214, 190)
PANEL = (14, 12, 10)
INK = (48, 30, 16)
PAPER = (231, 214, 176)

FONT_FILES = {
    "serif_semibold": "EBGaramond-SemiBold.ttf",
    "serif_italic": "EBGaramond-Italic.ttf",
    "serif_italic_med": "EBGaramond-MediumItalic.ttf",
    "sans_med": "Montserrat-Medium.ttf",
    "sans_bold": "Montserrat-Bold.ttf",
    "sans_black": "Montserrat-ExtraBold.ttf",
    "condensed": "Oswald-Bold.ttf",
    "mono": "CourierPrime-Regular.ttf",
    "mono_bold": "CourierPrime-Bold.ttf",
    "hebrew": "NotoSerifHebrew.ttf",
}


def font_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    dirs = [here / "assets" / "overlay-fonts"]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.insert(0, Path(base) / "assets" / "overlay-fonts")
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "assets" / "overlay-fonts")
    return dirs


@lru_cache(maxsize=None)
def _font_path(role: str) -> str | None:
    name = FONT_FILES[role]
    for d in font_dirs():
        p = d / name
        if p.is_file():
            return str(p)
    return None


@lru_cache(maxsize=512)
def font(role: str, px: int):
    from PIL import ImageFont
    path = _font_path(role)
    px = max(6, int(round(px)))
    if path:
        if role == "hebrew":
            # bố cục BASIC ở mọi máy (Windows thường không có raqm) — tự đảo chiều chữ
            return ImageFont.truetype(path, px, layout_engine=ImageFont.Layout.BASIC)
        return ImageFont.truetype(path, px)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", px)
    except Exception:
        return ImageFont.load_default()


def fonts_ok() -> bool:
    return all(_font_path(r) for r in FONT_FILES)


# --------------------------------------------------------------------------- #
# chữ
# --------------------------------------------------------------------------- #
HEBREW = re.compile(r"[֐-׿יִ-ﭏ]")


def is_hebrew(text: str) -> bool:
    return bool(HEBREW.search(text or ""))


def _clusters(text: str) -> list[tuple[str, str]]:
    """[(chữ gốc, các dấu đi kèm)] theo thứ tự logic."""
    import unicodedata
    out: list[tuple[str, str]] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] = (out[-1][0], out[-1][1] + ch)
        else:
            out.append((ch, ""))
    return out


def visual_rtl(text: str) -> str:
    """Chữ Hebrew → thứ tự hiển thị trái-sang-phải (dấu đi sau chữ gốc)."""
    return "".join(b + m for b, m in reversed(_clusters(text)))


def hebrew_width(f, text: str) -> float:
    return sum(f.getlength(b) for b, _ in _clusters(text))


def draw_hebrew(d, xy, text: str, f, fill) -> None:
    """Vẽ Hebrew từ phải sang trái, dấu nguyên âm đặt giữa chữ gốc của nó — không cần
    raqm (bản Pillow trên Windows thường không có), nên máy nào cũng ra giống nhau."""
    x, y = xy
    for base, mks in reversed(_clusters(text)):
        bw = f.getlength(base)
        d.text((x, y), base, font=f, fill=fill)
        for m in mks:
            l, _t, r, _b = f.getbbox(m)
            d.text((x + (bw - (r - l)) / 2 - l, y), m, font=f, fill=fill)
        x += bw


def marks(text: str) -> tuple[str, frozenset[int]]:
    """'*chữ nhấn*' → (chữ trơn, vị trí các ký tự được tô màu nhấn)."""
    raw = " ".join(str(text or "").split())
    out: list[str] = []
    hi: set[int] = set()
    on = False
    for ch in raw:
        if ch == "*":
            on = not on
            continue
        if on:
            hi.add(len(out))
        out.append(ch)
    plain = re.sub(r" {2,}", " ", "".join(out)).strip()
    if plain != "".join(out):          # dấu sao đứng một mình làm lệch vị trí → bỏ tô màu
        return plain, frozenset()
    return plain, frozenset(hi)


def plain(text: str) -> str:
    return marks(text)[0]


def _text_w(f, text: str, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    if not tracking:
        return f.getlength(text)
    return sum(f.getlength(ch) for ch in text) + tracking * (len(text) - 1)


def _wrap(f, text: str, max_w: float, tracking: float = 0.0) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if cur and _text_w(f, test, tracking) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _balanced(f, text: str, max_w: float, tracking: float = 0.0) -> list[str]:
    """Như _wrap nhưng chia đều các dòng (tránh dòng cuối mồ côi một từ)."""
    lines = _wrap(f, text, max_w, tracking)
    if len(lines) < 2:
        return lines
    lo, hi = max_w * 0.45, max_w
    best = lines
    for _ in range(14):
        mid = (lo + hi) / 2
        trial = _wrap(f, text, mid, tracking)
        if len(trial) <= len(lines):
            best, hi = trial, mid
        else:
            lo = mid
    return best


def _draw_tracked(d, xy, text: str, f, fill, tracking: float = 0.0):
    x, y = xy
    if not tracking:
        d.text((x, y), text, font=f, fill=fill)
        return
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking


def _line_h(f) -> float:
    a, de = f.getmetrics()
    return a + de


@dataclass
class TypedLine:
    x: float
    y: float
    text: str
    off: int          # vị trí ký tự đầu dòng trong chữ trơn


def line_offsets(plain_text: str, lines: list[str]) -> list[int]:
    offs, pos = [], 0
    for ln in lines:
        i = plain_text.find(ln, pos)
        i = pos if i < 0 else i
        offs.append(i)
        pos = i + len(ln)
    return offs


def draw_typed(d, lines: list[TypedLine], f, color, hi_color, hi: frozenset[int],
               limit: int | None = None, caret=None, k: float = 1.0) -> None:
    """Vẽ `limit` ký tự đầu (None = hết) của các dòng; ký tự trong `hi` tô màu nhấn.
    Mỗi ký tự ở đúng chỗ của nó trong dòng đầy đủ (đo theo cả tiền tố → giữ kerning).
    `caret` = màu con trỏ đặt ngay sau ký tự cuối đã hiện."""
    pos = None
    for ln in lines:
        avail = len(ln.text) if limit is None else limit - ln.off
        if avail <= 0:
            if avail == 0:                       # đã gõ dấu cách xuống dòng → con trỏ đầu dòng mới
                pos = (ln.x, ln.y)
            break
        n = min(len(ln.text), avail)
        i = 0
        while i < n:
            on = (ln.off + i) in hi
            j = i
            while j < n and ((ln.off + j) in hi) == on:
                j += 1
            d.text((ln.x + f.getlength(ln.text[:i]), ln.y), ln.text[i:j], font=f,
                   fill=(hi_color if on else color))
            i = j
        pos = (ln.x + f.getlength(ln.text[:n]), ln.y)
        if n < len(ln.text):
            break
    if caret is not None and pos is not None:
        a, de = f.getmetrics()
        x, y = pos
        d.rectangle([x + 3 * k, y + a * 0.12, x + 3 * k + max(2, 3.2 * k), y + a + de * 0.15], fill=caret)


def _panel(img, box, alpha: float, radius: int = 0, fill=PANEL):
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(round(255 * max(0.0, min(1.0, alpha))))
    box = [int(round(v)) for v in box]
    if radius:
        d.rounded_rectangle(box, radius=radius, fill=fill + (a,))
    else:
        d.rectangle(box, fill=fill + (a,))
    img.alpha_composite(layer)


def _shadow_text(img, draw_fn, blur: float, alpha: int = 200):
    """Vẽ chữ hai lần: lớp bóng mờ đen rồi lớp chữ — chữ đọc được trên mọi ảnh."""
    from PIL import Image, ImageDraw, ImageFilter
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(sh), (0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(max(1.0, blur)))
    img.alpha_composite(sh)
    top = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(top), None)
    img.alpha_composite(top)


def _gradient(img, y0: float, y1: float, a0: float, a1: float):
    """Dải tối dọc từ y0 (độ đậm a0) tới y1 (độ đậm a1) — làm chữ nổi trên ảnh full."""
    from PIL import Image
    w, h = img.size
    y0, y1 = int(max(0, y0)), int(min(h, y1))
    if y1 <= y0:
        return
    col = Image.new("L", (1, y1 - y0))
    for i in range(y1 - y0):
        t = i / max(1, (y1 - y0 - 1))
        col.putpixel((0, i), int(255 * (a0 + (a1 - a0) * t)))
    mask = col.resize((w, y1 - y0))
    layer = Image.new("RGBA", (w, y1 - y0), (0, 0, 0, 255))
    layer.putalpha(mask)
    img.alpha_composite(layer, (0, y0))


def _vignette(img, strength: float):
    """Tối dần ra mép khung (giữa gần như trong suốt)."""
    from PIL import Image, ImageFilter
    w, h = img.size
    g = Image.radial_gradient("L")              # 256×256: giữa 0, mép 255
    g = g.point(lambda v: int(max(0.0, min(1.0, (v / 255 - 0.25) / 0.75)) * 255 * strength))
    mask = g.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(max(2, w / 200)))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    layer.putalpha(mask)
    img.alpha_composite(layer)


# --------------------------------------------------------------------------- #
# khung cần vẽ
# --------------------------------------------------------------------------- #
@dataclass
class Frame:
    """Thông tin cho một ảnh cần vẽ."""
    item: object                     # OverlayItem
    words: int | None = None         # (0.6.0–0.6.3) giữ cho tương thích; 0.6.4 dùng chars
    list_items: tuple[str, ...] = ()  # LIST (cả danh sách, xem thử): các mục đang hiện
    list_label: str = ""
    part: str = ""                   # "" = cả đồ họa; xem từng kiểu
    chars: int | None = None         # đánh máy: số ký tự đã hiện (None = hết)
    caret: bool = False              # đang đánh máy: vẽ con trỏ
    progress: float | None = None    # vạch chạy (dòng thời gian, gạch chân): 0..1
    index: int = 0                   # LIST part="row": số thứ tự dòng (1, 2…)

    def key(self) -> str:
        it = self.item
        return "|".join([it.kind, it.text, it.sub, it.label, str(self.words), "/".join(self.list_items),
                         self.list_label, self.part, str(self.chars), str(int(self.caret)),
                         "" if self.progress is None else f"{self.progress:.3f}", str(self.index)])


def render_frame(fr: Frame, w: int, h: int, st: OverlayStyle):
    """Ảnh RGBA w×h trong suốt chứa đúng một đồ họa (hoặc một phần của nó)."""
    from PIL import Image
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    k = min(w, h) / 1080.0 * st.scale * BASE_SIZE
    fn = _RENDERERS[fr.item.kind]
    fn(img, fr, k, st)
    return img


def _want(fr: Frame, *parts: str) -> bool:
    """Phần này có được vẽ trong khung `fr` không ("" = vẽ tất cả)."""
    return fr.part == "" or fr.part in parts


# --------------------------------------------------------------------------- #
# các kiểu 0.6.0 (to hơn 30 %, thêm phần)
# --------------------------------------------------------------------------- #
def _r_chapter(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    _gradient(img, h * (0.40 if st.subs_on else 0.50), h, 0.0, 0.80)
    main = it.text.upper()
    fm = font("sans_bold", 31 * k)
    tr = 31 * k * 0.20
    lines = _balanced(fm, main, w * 0.66, tr)[:2]
    lh = _line_h(fm) * 1.15
    fs = font("serif_italic", 36 * k)
    cy = h * (0.70 if st.subs_on else 0.80)
    total = (lh * len(lines)) + (_line_h(fs) + 14 * k if it.sub else 0)
    y = cy - total / 2
    d = ImageDraw.Draw(img)
    if it.sub:
        sw = fs.getlength(it.sub)
        d.text(((w - sw) / 2, y), it.sub, font=fs, fill=CREAM + (255,))
        y += _line_h(fs) + 14 * k
    for ln in lines:
        lw = _text_w(fm, ln, tr)
        x = (w - lw) / 2
        _draw_tracked(d, (x, y), ln, fm, st.acc + (255,), tr)
        mid = y + _line_h(fm) * 0.52
        gap, L = 26 * k, 110 * k
        d.line([(x - gap - L, mid), (x - gap, mid)], fill=st.acc + (220,), width=max(1, int(2 * k)))
        d.line([(x + lw + gap, mid), (x + lw + gap + L, mid)], fill=st.acc + (220,),
               width=max(1, int(2 * k)))
        y += lh


def _label_box(img, x, y_bottom, text, k, st):
    """Nhãn nhỏ in hoa giãn chữ trên hộp tối; trả về (x2, y_top)."""
    from PIL import ImageDraw
    fl = font("sans_bold", 20 * k)
    tr = 20 * k * 0.22
    t = text.upper()
    tw = _text_w(fl, t, tr)
    px, py = 14 * k, 8 * k
    bh = _line_h(fl) + py * 2
    box = (x, y_bottom - bh, x + tw + px * 2, y_bottom)
    _panel(img, box, min(1.0, st.box_alpha + 0.08))
    d = ImageDraw.Draw(img)
    _draw_tracked(d, (x + px, y_bottom - bh + py), t, fl, st.acc + (255,), tr)
    return box[2], box[1]


def _r_lower(img, fr, k, st, serif: bool = False):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    x = w * 0.05
    bottom = h * (0.78 if st.subs_on else 0.88)
    fm = font("serif_italic_med", 50 * k) if serif else font("sans_bold", 38 * k)
    lines = _balanced(fm, it.text, w * 0.56)[:2]
    lh = _line_h(fm) * (1.02 if serif else 1.12)
    px, py = 22 * k, 12 * k
    tw = max(fm.getlength(ln) for ln in lines) if lines else 0
    bh = lh * len(lines) + py * 2
    bar = 5 * k
    box = (x, bottom - bh, x + bar + tw + px * 2, bottom)
    _panel(img, box, st.box_alpha)
    d = ImageDraw.Draw(img)
    d.rectangle([box[0], box[1], box[0] + bar, box[3]], fill=st.acc + (255,))
    y = box[1] + py - (4 * k if serif else 2 * k)
    for ln in lines:
        d.text((box[0] + bar + px, y), ln, font=fm, fill=WHITE + (255,))
        y += lh
    label = it.label or (it.sub if not serif else "")
    if label:
        _label_box(img, x, box[1] - 8 * k, label, k, st)
    if serif and it.sub:
        fs = font("sans_med", 22 * k)
        d.text((box[0] + bar + px, box[3] + 10 * k), it.sub, font=fs, fill=CREAM + (255,))


def _r_name(img, fr, k, st):
    _r_lower(img, fr, k, st, serif=True)


def quote_layout(text: str, w: int, h: int, k: float):
    """Bố cục cố định của chữ trích dẫn (tính MỘT lần cho cả câu): font, dòng, cao dòng."""
    body = plain(text)
    f, lines = None, []
    for size in (46, 42, 38, 34, 30, 27):
        f = font("serif_italic", size * k)
        lines = _balanced(f, body, w * 0.62)
        if len(lines) <= 6 and len(lines) * _line_h(f) * 1.08 < h * 0.62:
            break
    lh = _line_h(f) * 1.08
    return f, lines, lh


def _quote_geom(it, w, h, k):
    body, hi = marks(it.text)
    f, lines, lh = quote_layout(it.text, w, h, k)
    fr_ref = font("sans_bold", 18 * k)
    tr = 18 * k * 0.24
    ref = it.sub.upper()
    tw = max(f.getlength(ln) for ln in lines) if lines else 0
    padx, pady = 56 * k, 42 * k
    bw = max(tw, _text_w(fr_ref, ref, tr)) + padx * 2
    bw = max(bw, w * 0.40)
    ref_h = (_line_h(fr_ref) + 32 * k) if ref else 0
    bh = lh * len(lines) + pady * 2 + ref_h
    x0, y0 = (w - bw) / 2, (h - bh) / 2
    offs = line_offsets(body, lines)
    tl = [TypedLine((w - f.getlength(ln)) / 2, y0 + pady + i * lh, ln, offs[i]) for i, ln in enumerate(lines)]
    return dict(f=f, lines=tl, hi=hi, box=(x0, y0, x0 + bw, y0 + bh), pady=pady, ref=ref,
                fr_ref=fr_ref, tr=tr, n=len(body))


def _r_quote(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    g = _quote_geom(fr.item, w, h, k)
    box = g["box"]
    if _want(fr, "box"):
        _panel(img, box, st.box_alpha)
        d = ImageDraw.Draw(img)
        lw = max(1, int(round(1.6 * k)))
        d.rectangle([box[0], box[1], box[2], box[3]], outline=st.acc + (110,), width=lw)
        d.line([(box[0], box[1]), (box[2], box[1])], fill=st.acc + (255,), width=max(2, int(3 * k)))
    d = ImageDraw.Draw(img)
    if _want(fr, "text"):
        limit = fr.chars
        if limit is None and fr.words is not None:          # cách đếm cũ theo từ
            limit = len(" ".join(plain(fr.item.text).split()[:fr.words]))
        draw_typed(d, g["lines"], g["f"], WHITE + (255,), st.acc + (255,), g["hi"], limit,
                   st.acc + (255,) if fr.caret else None, k)
    show_ref = fr.part == "ref" or (fr.part == "" and (fr.words is None and fr.chars is None))
    if g["ref"] and show_ref:
        fr_ref, tr, ref = g["fr_ref"], g["tr"], g["ref"]
        ry = box[3] - g["pady"] - _line_h(fr_ref) + 8 * k
        rw = _text_w(fr_ref, ref, tr)
        _draw_tracked(d, ((w - rw) / 2, ry), ref, fr_ref, st.acc + (255,), tr)
        d.line([((w - 60 * k) / 2, ry - 16 * k), ((w + 60 * k) / 2, ry - 16 * k)],
               fill=st.acc + (200,), width=max(1, int(1.5 * k)))


def _r_title(img, fr, k, st):
    w, h = img.size
    it = fr.item
    _panel(img, (0, 0, w, h), 0.30, fill=(0, 0, 0))
    _vignette(img, 0.55)
    body, hi = marks(it.text.upper())
    fm = font("sans_black", 66 * k)
    lines = _balanced(fm, body, w * 0.74)[:3]
    if len(lines) == 3:
        fm = font("sans_black", 56 * k)
        lines = _balanced(fm, body, w * 0.78)[:3]
    lh = _line_h(fm) * 1.05
    fs = font("serif_italic", 36 * k)
    sub_lines = _balanced(fs, it.sub, w * 0.62)[:2] if it.sub else []
    slh = _line_h(fs) * 1.05
    total = lh * len(lines) + (24 * k + slh * len(sub_lines) if sub_lines else 0)
    y0 = (h - total) / 2
    offs = line_offsets(body, lines)
    tl = [TypedLine((w - fm.getlength(ln)) / 2, y0 + i * lh, ln, offs[i]) for i, ln in enumerate(lines)]

    def draw(d, shadow):
        if shadow:
            for t in tl:
                d.text((t.x, t.y), t.text, font=fm, fill=shadow)
        else:
            draw_typed(d, tl, fm, WHITE + (255,), st.acc + (255,), hi)
        y = y0 + lh * len(lines) + 24 * k
        for ln in sub_lines:
            sw = fs.getlength(ln)
            d.text(((w - sw) / 2, y), ln, font=fs, fill=shadow or (CREAM + (255,)))
            y += slh

    _shadow_text(img, draw, blur=10 * k, alpha=230)


def _r_stamp(img, fr, k, st):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    w, h = img.size
    it = fr.item
    text = it.text.upper()
    f = font("condensed", 64 * k)
    tr = 64 * k * 0.06
    lines = _balanced(f, text, w * 0.50, tr)[:2]
    lh = _line_h(f) * 1.0
    tw = max(_text_w(f, ln, tr) for ln in lines)
    padx, pady = 42 * k, 22 * k
    bw, bh = tw + padx * 2, lh * len(lines) + pady * 2
    pad = int(40 * k)
    tile = Image.new("RGBA", (int(bw) + pad * 2, int(bh) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    red = st.red
    b = (pad, pad, pad + bw, pad + bh)
    d.rectangle(b, fill=red + (40,), outline=red + (255,), width=max(3, int(6 * k)))
    inset = 11 * k
    d.rectangle((b[0] + inset, b[1] + inset, b[2] - inset, b[3] - inset), outline=red + (230,),
                width=max(1, int(2 * k)))
    y = pad + pady - 4 * k
    for ln in lines:
        lw = _text_w(f, ln, tr)
        _draw_tracked(d, (pad + (bw - lw) / 2, y), ln, f, red + (255,), tr)
        y += lh
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    noise = Image.new("L", tile.size, 255)
    nd = ImageDraw.Draw(noise)
    for _ in range(int(tile.size[0] * tile.size[1] / 900)):
        x, yy = rng.randrange(tile.size[0]), rng.randrange(tile.size[1])
        r = rng.uniform(0.6, 2.6) * k
        nd.ellipse((x - r, yy - r, x + r, yy + r), fill=rng.randrange(0, 120))
    noise = noise.filter(ImageFilter.GaussianBlur(0.6 * k))
    alpha = ImageChops.multiply(tile.getchannel("A"), noise)
    tile.putalpha(alpha)
    tile = tile.rotate(7, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(tile, (int((w - tile.size[0]) / 2), int(h * 0.47 - tile.size[1] / 2)))


def _list_geom(label: str, w, h, k):
    fl = font("sans_bold", 19 * k)
    fn = font("sans_bold", 21 * k)
    fi = font("sans_bold", 27 * k)
    x, y = w * 0.04, h * 0.055
    label_h = 0.0
    if label:
        label_h = _line_h(fl) + 18 * k + 10 * k
    row_h = _line_h(fi) + 18 * k
    return dict(fl=fl, fn=fn, fi=fi, x=x, y=y, label_h=label_h, row_h=row_h, gap=8 * k)


def _r_list(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    label = (fr.list_label or fr.item.label or "").upper()
    g = _list_geom(label, w, h, k)
    x, y = g["x"], g["y"]
    fl, fn, fi = g["fl"], g["fn"], g["fi"]
    tr = 19 * k * 0.24
    if label and _want(fr, "label"):
        px, py = 16 * k, 9 * k
        tw = _text_w(fl, label, tr)
        bh = _line_h(fl) + py * 2
        _panel(img, (x, y, x + tw + px * 2, y + bh), min(1.0, st.box_alpha + 0.08))
        d = ImageDraw.Draw(img)
        _draw_tracked(d, (x + px, y + py), label, fl, st.acc + (255,), tr)
    if fr.part == "label":
        return
    rows = [(fr.index, fr.item.text)] if fr.part == "row" else list(enumerate(fr.list_items, start=1))
    for i, item in rows:
        ry = y + g["label_h"] + (i - 1) * (g["row_h"] + g["gap"])
        num = f"{i:02d}"
        px, py = 14 * k, 9 * k
        nw = fn.getlength(num)
        iw = fi.getlength(item)
        _panel(img, (x, ry, x + px * 3 + nw + iw, ry + g["row_h"]), st.box_alpha)
        d = ImageDraw.Draw(img)
        d.text((x + px, ry + py + (_line_h(fi) - _line_h(fn)) / 2), num, font=fn, fill=st.acc + (255,))
        d.text((x + px * 2 + nw, ry + py), item, font=fi, fill=WHITE + (255,))


def _r_stat(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    fnum = font("sans_black", 104 * k)
    flab = font("sans_bold", 19 * k)
    tr = 19 * k * 0.22
    lab_lines = _balanced(flab, it.sub.upper(), w * 0.22, tr)[:3] if it.sub else []
    nw = fnum.getlength(it.text)
    lw = max([_text_w(flab, ln, tr) for ln in lab_lines] or [0])
    padx, pady = 34 * k, 22 * k
    bw = max(nw, lw) + padx * 2
    nh = _line_h(fnum) * 0.92
    llh = _line_h(flab) * 1.25
    bh = nh + (12 * k + llh * len(lab_lines) if lab_lines else 0) + pady * 2
    x1, y0 = w * 0.955, h * 0.07
    box = (x1 - bw, y0, x1, y0 + bh)
    _panel(img, box, min(1.0, st.box_alpha + 0.05))
    d = ImageDraw.Draw(img)
    d.rectangle(box, outline=st.acc + (255,), width=max(2, int(2.5 * k)))
    d.text((box[0] + (bw - nw) / 2, y0 + pady - 10 * k), it.text, font=fnum, fill=WHITE + (255,))
    y = y0 + pady + nh + 12 * k
    for ln in lab_lines:
        lw_ = _text_w(flab, ln, tr)
        _draw_tracked(d, (box[0] + (bw - lw_) / 2, y), ln, flab, st.acc + (255,), tr)
        y += llh


# --------------------------------------------------------------------------- #
# 0.6.4: kiểu mới
# --------------------------------------------------------------------------- #
def place_text(it) -> str:
    """Chữ đánh máy của PLACE: tên nơi (in hoa) + xuống dòng + dòng phụ."""
    return it.text.upper() + (("\n" + it.sub) if it.sub else "")


def _place_geom(it, w, h, k):
    fm = font("mono_bold", 30 * k)
    fs = font("mono", 24 * k)
    main = it.text.upper()
    sub = it.sub
    x, y = w * 0.05, h * 0.07
    pad = 18 * k
    bar = 5 * k
    tw = max(fm.getlength(main), fs.getlength(sub) if sub else 0)
    bh = _line_h(fm) + (_line_h(fs) + 8 * k if sub else 0) + pad * 2
    box = (x, y, x + bar + pad * 2 + tw + 18 * k, y + bh)
    tx = x + bar + pad
    lines = [TypedLine(tx, y + pad, main, 0)]
    if sub:
        lines.append(TypedLine(tx, y + pad + _line_h(fm) + 8 * k, sub, len(main) + 1))
    return dict(fm=fm, fs=fs, box=box, bar=bar, lines=lines, n=len(place_text(it)))


def _r_place(img, fr, k, st):
    """Mốc nơi chốn / thời gian góc trên trái, chữ máy đánh."""
    from PIL import ImageDraw
    w, h = img.size
    g = _place_geom(fr.item, w, h, k)
    box = g["box"]
    if _want(fr, "box"):
        _panel(img, box, st.box_alpha)
        d = ImageDraw.Draw(img)
        d.rectangle([box[0], box[1], box[0] + g["bar"], box[3]], fill=st.acc + (255,))
    if _want(fr, "text"):
        d = ImageDraw.Draw(img)
        limit = fr.chars
        main, sub = g["lines"][0], g["lines"][1:] if len(g["lines"]) > 1 else []
        caret = st.acc + (255,) if fr.caret else None
        on_main = limit is None or limit <= len(main.text)
        draw_typed(d, [main], g["fm"], WHITE + (255,), st.acc + (255,), frozenset(), limit,
                   caret if on_main else None, k)
        if sub:
            draw_typed(d, sub, g["fs"], CREAM + (255,), st.acc + (255,), frozenset(), limit,
                       None if on_main else caret, k)


def _split_term(text: str) -> tuple[str, str]:
    a, _, b = str(text or "").partition("|")
    return a.strip(), b.strip()


def _r_term(img, fr, k, st):
    """Thẻ từ gốc: ngôn ngữ (label) · chữ gốc (Hebrew/Hy Lạp) · từ phiên âm · nghĩa."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    term, orig = _split_term(it.text)
    fl = font("sans_bold", 18 * k)
    trl = 18 * k * 0.26
    fo = font("hebrew", 50 * k) if is_hebrew(orig) else font("serif_semibold", 46 * k)
    ft = font("serif_semibold", 52 * k)
    fmn = font("serif_italic", 30 * k)
    label = it.label.upper()
    heb = is_hebrew(orig)
    pad = 30 * k
    maxw = w * 0.34
    mean = _balanced(fmn, it.sub, maxw)[:3] if it.sub else []
    ow = (hebrew_width(fo, orig) if heb else fo.getlength(orig)) if orig else 0
    tw = max([ow, ft.getlength(term), _text_w(fl, label, trl)]
             + [fmn.getlength(m) for m in mean])
    bw = max(tw + pad * 2, w * 0.24)
    parts_h = (_line_h(fl) + 14 * k if label else 0) + (_line_h(fo) + 4 * k if orig else 0) \
        + _line_h(ft) + (22 * k + _line_h(fmn) * 1.05 * len(mean) if mean else 0)
    bh = parts_h + pad * 2
    x1 = w * 0.95
    y0 = (h - bh) / 2 - h * 0.03
    box = (x1 - bw, y0, x1, y0 + bh)
    _panel(img, box, st.box_alpha)
    d = ImageDraw.Draw(img)
    d.rectangle([box[2] - 5 * k, box[1], box[2], box[3]], fill=st.acc + (255,))
    x, y = box[0] + pad, box[1] + pad
    if label:
        _draw_tracked(d, (x, y), label, fl, st.acc + (255,), trl)
        y += _line_h(fl) + 14 * k
    if orig:
        if heb:
            draw_hebrew(d, (x, y), orig, fo, CREAM + (255,))
        else:
            d.text((x, y), orig, font=fo, fill=CREAM + (255,))
        y += _line_h(fo) + 4 * k
    d.text((x, y), term, font=ft, fill=WHITE + (255,))
    y += _line_h(ft)
    if mean:
        y += 10 * k
        d.line([(x, y), (x + 70 * k, y)], fill=st.acc + (230,), width=max(1, int(2 * k)))
        y += 12 * k
        for m in mean:
            d.text((x, y), m, font=fmn, fill=CREAM + (255,))
            y += _line_h(fmn) * 1.05


def _vs_geom(it, w, h, k):
    f = font("sans_bold", 34 * k)
    fl = font("sans_bold", 19 * k)
    colw = w * 0.30
    left = _balanced(f, it.text, colw - 60 * k)[:3]
    right = _balanced(f, it.sub, colw - 60 * k)[:3]
    lh = _line_h(f) * 1.12
    rows = max(len(left), len(right), 1)
    bh = rows * lh + 60 * k
    cy = h * 0.55
    y0 = cy - bh / 2
    gap = w * 0.035
    lbox = (w / 2 - gap - colw, y0, w / 2 - gap, y0 + bh)
    rbox = (w / 2 + gap, y0, w / 2 + gap + colw, y0 + bh)
    return dict(f=f, fl=fl, left=left, right=right, lh=lh, lbox=lbox, rbox=rbox, y0=y0, bh=bh)


def _r_vs(img, fr, k, st):
    """So sánh hai bên: text (trái) đối sub (phải), label = tiêu đề phía trên."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    g = _vs_geom(it, w, h, k)
    f, lh = g["f"], g["lh"]

    def column(box, lines, accent_side):
        _panel(img, box, st.box_alpha)
        d = ImageDraw.Draw(img)
        d.line([(box[0], box[1]), (box[2], box[1])], fill=st.acc + (255,), width=max(2, int(3 * k)))
        y = (box[1] + box[3]) / 2 - lh * len(lines) / 2
        for ln in lines:
            d.text(((box[0] + box[2]) / 2 - f.getlength(ln) / 2, y), ln, font=f, fill=WHITE + (255,))
            y += lh

    if _want(fr, "left"):
        column(g["lbox"], g["left"], "l")
    if _want(fr, "right"):
        column(g["rbox"], g["right"], "r")
    if _want(fr, "mid"):
        d = ImageDraw.Draw(img)
        r = 38 * k
        cx, cy = w / 2, g["y0"] + g["bh"] / 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PANEL + (240,), outline=st.acc + (255,),
                  width=max(2, int(3 * k)))
        fv = font("condensed", 34 * k)
        t = "VS"
        d.text((cx - fv.getlength(t) / 2, cy - _line_h(fv) / 2 - 2 * k), t, font=fv, fill=st.acc + (255,))
        if it.label:
            lab = it.label.upper()
            tr = 19 * k * 0.26
            lw = _text_w(g["fl"], lab, tr)
            ly = g["y0"] - _line_h(g["fl"]) - 22 * k
            _panel(img, (w / 2 - lw / 2 - 16 * k, ly - 9 * k, w / 2 + lw / 2 + 16 * k,
                         ly + _line_h(g["fl"]) + 9 * k), min(1.0, st.box_alpha + 0.08))
            d = ImageDraw.Draw(img)
            _draw_tracked(d, (w / 2 - lw / 2, ly), lab, g["fl"], st.acc + (255,), tr)


def timeline_points(text: str) -> list[tuple[str, bool]]:
    """'1446 BC | *586 BC* | 70 AD' → [(nhãn, là điểm đang nói)]; không đánh dấu thì điểm cuối."""
    pts = [p.strip() for p in str(text or "").split("|") if p.strip()]
    out = []
    for p in pts:
        cur = p.startswith("*") and p.endswith("*") and len(p) > 2
        out.append((p.strip("*").strip(), cur))
    if out and not any(c for _, c in out):
        out[-1] = (out[-1][0], True)
    return out


def _r_timeline(img, fr, k, st):
    """Dòng thời gian ngang dưới khung: vạch chạy từ trái sang, điểm hiện khi vạch tới."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    pts = timeline_points(it.text)
    cy = h * (0.70 if st.subs_on else 0.80)
    x0, x1 = w * 0.10, w * 0.90
    if _want(fr, "bg"):
        _gradient(img, cy - h * 0.20, min(h, cy + h * 0.22), 0.0, 0.75)
        if it.label:
            fl = font("sans_bold", 19 * k)
            tr = 19 * k * 0.26
            d = ImageDraw.Draw(img)
            _draw_tracked(d, (x0, cy - 92 * k), it.label.upper(), fl, st.acc + (255,), tr)
    if not _want(fr, "line"):
        return
    prog = 1.0 if fr.progress is None else max(0.0, min(1.0, fr.progress))
    d = ImageDraw.Draw(img)
    lw = max(2, int(3 * k))
    d.line([(x0, cy), (x1, cy)], fill=CREAM + (70,), width=lw)
    xe = x0 + (x1 - x0) * prog
    if prog > 0:
        d.line([(x0, cy), (xe, cy)], fill=st.acc + (255,), width=lw)
    n = len(pts)
    fy = font("sans_bold", 26 * k)
    fyc = font("sans_black", 30 * k)
    for i, (lab, cur) in enumerate(pts):
        px = x0 + (x1 - x0) * ((i + 0.5) / n if n else 0.5)
        if px > xe + 1:
            continue
        r = (11 if cur else 7) * k
        if cur:
            d.ellipse([px - r * 1.9, cy - r * 1.9, px + r * 1.9, cy + r * 1.9], fill=st.acc + (60,))
        d.ellipse([px - r, cy - r, px + r, cy + r], fill=(st.acc if cur else CREAM) + (255,),
                  outline=PANEL + (255,), width=max(1, int(2 * k)))
        f = fyc if cur else fy
        above = i % 2 == 0
        ty = cy - r - 14 * k - _line_h(f) if above else cy + r + 12 * k
        d.text((px - f.getlength(lab) / 2, ty), lab, font=f,
               fill=(st.acc if cur else WHITE) + (255,))


def _keyword_geom(it, w, h, k):
    body, hi = marks(it.text.upper())
    f = font("sans_black", 92 * k)
    lines = _balanced(f, body, w * 0.80)[:2]
    if len(lines) == 2:
        f = font("sans_black", 76 * k)
        lines = _balanced(f, body, w * 0.82)[:2]
    lh = _line_h(f) * 1.0
    fk = font("sans_bold", 21 * k)
    fs = font("serif_italic", 36 * k)
    kick = it.label.upper()
    total = lh * len(lines) + (_line_h(fk) + 16 * k if kick else 0) + (24 * k + _line_h(fs) if it.sub else 0)
    y = h * 0.5 - total / 2
    ky = y
    if kick:
        y += _line_h(fk) + 16 * k
    offs = line_offsets(body, lines)
    tl = [TypedLine((w - f.getlength(ln)) / 2, y + i * lh, ln, offs[i]) for i, ln in enumerate(lines)]
    ul_y = y + lh * len(lines) + 6 * k
    ul_w = max(f.getlength(ln) for ln in lines) if lines else 0
    return dict(f=f, tl=tl, hi=hi, fk=fk, fs=fs, kick=kick, ky=ky, ul=(w / 2 - ul_w / 2, ul_y, ul_w),
                sub_y=ul_y + 24 * k)


def _r_keyword(img, fr, k, st):
    """Từ khóa lớn giữa khung, gạch chân màu nhấn chạy ra."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    g = _keyword_geom(it, w, h, k)
    if _want(fr, "word"):
        def draw(d, shadow):
            if g["kick"]:
                tr = 21 * k * 0.3
                kw = _text_w(g["fk"], g["kick"], tr)
                _draw_tracked(d, ((w - kw) / 2, g["ky"]), g["kick"], g["fk"], shadow or (st.acc + (255,)), tr)
            if shadow:
                for t in g["tl"]:
                    d.text((t.x, t.y), t.text, font=g["f"], fill=shadow)
            else:
                draw_typed(d, g["tl"], g["f"], WHITE + (255,), st.acc + (255,), g["hi"])
            if it.sub:
                sw = g["fs"].getlength(it.sub)
                d.text(((w - sw) / 2, g["sub_y"]), it.sub, font=g["fs"], fill=shadow or (CREAM + (255,)))
        _shadow_text(img, draw, blur=12 * k, alpha=235)
    if _want(fr, "line"):
        prog = 1.0 if fr.progress is None else max(0.0, min(1.0, fr.progress))
        x, y, uw = g["ul"]
        if prog > 0:
            d = ImageDraw.Draw(img)
            cx = x + uw / 2
            half = uw / 2 * prog
            d.rectangle([cx - half, y, cx + half, y + max(3, 6 * k)], fill=st.acc + (255,))


def _r_source(img, fr, k, st):
    """Chú thích nguồn nhỏ góc dưới phải."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    fl = font("sans_bold", 16 * k)
    tr = 16 * k * 0.26
    ft = font("serif_italic", 27 * k)
    label = (it.label or "Source").upper()
    lines = _balanced(ft, it.text, w * 0.36)[:2]
    pad = 14 * k
    tw = max([ft.getlength(ln) for ln in lines] + [_text_w(fl, label, tr)])
    bh = _line_h(fl) + 6 * k + _line_h(ft) * 1.02 * len(lines) + pad * 2
    x1 = w * 0.955
    y1 = h * (0.78 if st.subs_on else 0.92)
    box = (x1 - tw - pad * 2, y1 - bh, x1, y1)
    _panel(img, box, st.box_alpha)
    d = ImageDraw.Draw(img)
    d.line([(box[0], box[1]), (box[0], box[3])], fill=st.acc + (255,), width=max(2, int(3 * k)))
    x, y = box[0] + pad, box[1] + pad
    _draw_tracked(d, (x, y), label, fl, st.acc + (255,), tr)
    y += _line_h(fl) + 6 * k
    for ln in lines:
        d.text((x, y), ln, font=ft, fill=CREAM + (255,))
        y += _line_h(ft) * 1.02


def _note_geom(it, w, h, k):
    body, hi = marks(it.text)
    f = None
    lines: list[str] = []
    for size in (40, 36, 33, 30, 27):
        f = font("serif_italic_med", size * k)
        lines = _balanced(f, body, w * 0.50)
        if len(lines) <= 7:
            break
    lh = _line_h(f) * 1.12
    fa = font("sans_bold", 18 * k)
    tra = 18 * k * 0.22
    attr = it.sub.upper()
    padx, pady = 62 * k, 54 * k
    tw = max(f.getlength(ln) for ln in lines) if lines else 0
    bw = max(tw + padx * 2, w * 0.40)
    bh = lh * len(lines) + pady * 2 + ((_line_h(fa) + 26 * k) if attr else 0)
    x0, y0 = (w - bw) / 2, (h - bh) / 2
    offs = line_offsets(body, lines)
    tl = [TypedLine(x0 + padx, y0 + pady + i * lh, ln, offs[i]) for i, ln in enumerate(lines)]
    return dict(f=f, tl=tl, hi=hi, box=(x0, y0, x0 + bw, y0 + bh), fa=fa, tra=tra, attr=attr,
                padx=padx, pady=pady, n=len(body))


def _parchment(img, box, k, seed_text: str):
    """Tờ giấy cổ: màu giấy, vệt ố, mép sẫm và rách nhẹ, bóng đổ."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    bw, bh = x1 - x0, y1 - y0
    rng = random.Random(int(hashlib.md5(seed_text.encode("utf-8")).hexdigest()[:8], 16))
    # bóng đổ
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([x0 + 10 * k, y0 + 14 * k, x1 + 10 * k, y1 + 14 * k], fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14 * k)))
    paper = Image.new("RGBA", (bw, bh), PAPER + (255,))
    # vệt ố
    stains = Image.new("L", (bw, bh), 0)
    sd = ImageDraw.Draw(stains)
    for _ in range(14):
        cx, cy = rng.uniform(0, bw), rng.uniform(0, bh)
        r = rng.uniform(0.08, 0.30) * max(bw, bh)
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rng.randrange(18, 48))
    stains = stains.filter(ImageFilter.GaussianBlur(max(bw, bh) * 0.06))
    dark = Image.new("RGBA", (bw, bh), (120, 84, 40, 255))
    paper = Image.composite(dark, paper, stains)
    # mép sẫm
    edge = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(edge).rectangle([0, 0, bw - 1, bh - 1], outline=255, width=max(2, int(26 * k)))
    edge = edge.filter(ImageFilter.GaussianBlur(22 * k)).point(lambda v: int(v * 0.55))
    paper = Image.composite(Image.new("RGBA", (bw, bh), (96, 64, 30, 255)), paper, edge)
    # hạt giấy
    grain = Image.effect_noise((max(1, bw // 2), max(1, bh // 2)), 18).resize((bw, bh))
    grain = grain.point(lambda v: max(0, min(255, v - 128 + 128)))
    paper = Image.blend(paper.convert("RGB"), Image.merge("RGB", (grain,) * 3), 0.06).convert("RGBA")
    # mép rách
    mask = Image.new("L", (bw, bh), 255)
    md = ImageDraw.Draw(mask)
    step = max(3, int(9 * k))
    for x in range(0, bw, step):
        for yy in (0, bh - 1):
            r = rng.uniform(0.5, 3.4) * k
            md.ellipse([x - r, yy - r, x + r, yy + r], fill=0)
    for y in range(0, bh, step):
        for xx in (0, bw - 1):
            r = rng.uniform(0.5, 3.4) * k
            md.ellipse([xx - r, y - r, xx + r, y + r], fill=0)
    paper.putalpha(ImageChops.multiply(paper.getchannel("A"), mask))
    img.alpha_composite(paper, (x0, y0))


def _r_note(img, fr, k, st):
    """Tờ giấy cổ giữa khung, chữ mực hiện như đang viết/đánh máy."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    g = _note_geom(it, w, h, k)
    box = g["box"]
    if _want(fr, "card"):
        _parchment(img, box, k, it.text)
    d = ImageDraw.Draw(img)
    if _want(fr, "text"):
        draw_typed(d, g["tl"], g["f"], INK + (255,), (128, 30, 22, 255), g["hi"], fr.chars,
                   INK + (230,) if fr.caret else None, k)
    show_ref = fr.part == "ref" or (fr.part == "" and fr.chars is None)
    if g["attr"] and show_ref:
        ry = box[3] - g["pady"] - _line_h(g["fa"]) + 6 * k
        aw = _text_w(g["fa"], "— " + g["attr"], g["tra"])
        _draw_tracked(d, (box[2] - g["padx"] - aw, ry), "— " + g["attr"], g["fa"], (110, 62, 26, 255), g["tra"])


def cinema_bar(w: int, h: int) -> float:
    """Chiều cao mỗi thanh đen (px) để khung còn lại tỉ lệ 2,39:1."""
    return max(0.0, (h - w / 2.39) / 2)


def _r_cinema(img, fr, k, st):
    """Khung điện ảnh: hai thanh đen trên dưới, chú thích nhỏ trong thanh dưới."""
    from PIL import ImageDraw
    w, h = img.size
    bar = max(cinema_bar(w, h), h * 0.09)
    d = ImageDraw.Draw(img)
    if _want(fr, "top"):
        d.rectangle([0, 0, w, bar], fill=(0, 0, 0, 255))
    if _want(fr, "bottom"):
        d.rectangle([0, h - bar, w, h], fill=(0, 0, 0, 255))
        cap = fr.item.text.upper()
        if cap:
            f = font("sans_bold", 20 * k)
            tr = 20 * k * 0.34
            tw = _text_w(f, cap, tr)
            _draw_tracked(d, ((w - tw) / 2, h - bar / 2 - _line_h(f) / 2), cap, f, CREAM + (230,), tr)


def _r_subscribe(img, fr, k, st):
    """Nút đăng ký kênh góc dưới phải: nút đỏ + chuông, dòng mời nhỏ phía trên."""
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    text = (it.text or "Subscribe").upper()
    f = font("sans_black", 30 * k)
    tr = 30 * k * 0.06
    tw = _text_w(f, text, tr)
    pad = 24 * k
    bh = _line_h(f) + 24 * k
    x1 = w * 0.955
    y1 = h * (0.78 if st.subs_on else 0.90)
    bell = bh
    box = (x1 - tw - pad * 2 - bell - 14 * k, y1 - bh, x1 - bell - 14 * k, y1)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([int(v) for v in box], radius=int(bh / 2), fill=(204, 0, 0, 255))
    _draw_tracked(d, (box[0] + pad, box[1] + 11 * k), text, f, (255, 255, 255, 255), tr)
    # chuông
    bx0, by0 = x1 - bell, y1 - bh
    d.ellipse([bx0, by0, bx0 + bell, by0 + bell], fill=PANEL + (235,), outline=WHITE + (255,),
              width=max(1, int(2 * k)))
    cx, cy, s = bx0 + bell / 2, by0 + bell / 2, bell * 0.22
    d.pieslice([cx - s, cy - s * 1.3, cx + s, cy + s * 0.7], 180, 360, fill=WHITE + (255,))
    d.rectangle([cx - s, cy - s * 0.3, cx + s, cy + s * 0.55], fill=WHITE + (255,))
    d.rectangle([cx - s * 1.3, cy + s * 0.5, cx + s * 1.3, cy + s * 0.75], fill=WHITE + (255,))
    d.ellipse([cx - s * 0.3, cy + s * 0.75, cx + s * 0.3, cy + s * 1.25], fill=WHITE + (255,))
    if it.sub:
        fs = font("sans_med", 22 * k)
        sw = fs.getlength(it.sub)
        sy = box[1] - 14 * k - _line_h(fs) - 12 * k
        _panel(img, (x1 - sw - 28 * k, sy, x1, box[1] - 14 * k), st.box_alpha)
        d = ImageDraw.Draw(img)
        d.text((x1 - sw - 14 * k, sy + 6 * k), it.sub, font=fs, fill=WHITE + (255,))


_RENDERERS = {"CHAPTER": _r_chapter, "LOWER": _r_lower, "NAME": _r_name, "QUOTE": _r_quote,
              "TITLE": _r_title, "STAMP": _r_stamp, "LIST": _r_list, "STAT": _r_stat,
              "PLACE": _r_place, "TERM": _r_term, "VS": _r_vs, "TIMELINE": _r_timeline,
              "KEYWORD": _r_keyword, "SOURCE": _r_source, "NOTE": _r_note, "CINEMA": _r_cinema,
              "SUBSCRIBE": _r_subscribe}


def typed_length(it) -> int:
    """Số ký tự đánh máy của QUOTE / NOTE / PLACE (khớp bố cục)."""
    if it.kind == "PLACE":
        return len(place_text(it))
    return len(plain(it.text))
