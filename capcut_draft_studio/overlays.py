"""Đồ họa chữ (0.6.0): thẻ chương, nhãn, hộp trích dẫn, câu chốt, dấu mộc, danh
sách đánh số, ô số liệu — đặt đè lên ảnh/video của từng cảnh.

Ảnh của kênh nay được tạo FULL khung, không chừa khoảng trống cho chữ; mọi chữ
trên hình đi qua module này. Người dùng (hoặc skill chia phân cảnh) ghi một file
`overlay.xlsx` (hoặc .csv/.tsv) trong folder VIDEO, mỗi dòng một đồ họa:

    scene | type  | text                          | sub           | label | until | start | dur
    3     | QUOTE | They shall not be able to ... | 1 ENOCH 38:4  |       |       |       |
    5     | LIST  | One on the face               |               | THREE MARKS | 9 |   |

Mỗi đồ họa được vẽ thành một ảnh PNG trong suốt đúng cỡ khung hình (Pillow, font
đi kèm trong assets/overlay-fonts), rồi:

* draft CapCut: đặt thành đoạn ảnh trên các track `chu_*`, có hiệu ứng hiện dần
  / mờ dần (渐显 / 渐隐);
* render ffmpeg: phủ lên clip của từng cảnh (xem render.Renderer.scene_args).

Hai bên dùng CHUNG một danh sách `Placement` (ảnh nào, từ giây nào, dài bao
lâu) nên draft và mp4 khớp nhau. Thời gian tính trên trục NỘI DUNG (giống
`ScenePlan.start`); quảng cáo giữa video do nơi gọi cắt như mọi lớp phủ khác.

Phần đọc file và lập lịch là thuần (không I/O ngoài file đầu vào) để test rẻ.
"""
from __future__ import annotations

import csv
import hashlib
import math
import random
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .models import LogFn, ScenePlan

# --------------------------------------------------------------------------- #
# loại đồ họa
# --------------------------------------------------------------------------- #
#: key → (tên tiếng Việt, mô tả ngắn) — thứ tự này là thứ tự hiện trong hướng dẫn
KINDS: dict[str, tuple[str, str]] = {
    "CHAPTER": ("Thẻ mở chương", "dòng nguồn nhỏ in nghiêng + câu chủ đề in hoa màu nhấn, giữa phần dưới khung"),
    "LOWER": ("Nhãn dưới", "nhãn nhỏ (label) + một dòng chữ trắng trong hộp tối, góc dưới trái"),
    "NAME": ("Nhãn tên", "như Nhãn dưới nhưng chữ chính là serif nghiêng (tên người, nơi, năm)"),
    "QUOTE": ("Hộp trích dẫn", "chữ serif nghiêng hiện dần như đánh máy, tham chiếu ở dưới"),
    "TITLE": ("Câu chốt", "chữ in hoa trắng đậm giữa màn hình, nền tối dần, dòng phụ nghiêng"),
    "STAMP": ("Dấu mộc", "con dấu đỏ nghiêng, chữ in hoa — dùng rất ít"),
    "LIST": ("Danh sách", "nhãn góc trên trái + các mục đánh số 01, 02… cộng dần qua nhiều cảnh"),
    "STAT": ("Ô số liệu", "số lớn trong hộp viền màu nhấn, nhãn nhỏ bên dưới, góc trên phải"),
}

#: tên khác mà người dùng hay gõ → key chuẩn
ALIASES = {
    "CHUONG": "CHAPTER", "CHƯƠNG": "CHAPTER", "CHAP": "CHAPTER", "SECTION": "CHAPTER",
    "NHAN": "LOWER", "NHÃN": "LOWER", "LOWER3": "LOWER", "LOWERTHIRD": "LOWER", "TAG": "LOWER",
    "TERM": "LOWER", "CALLOUT": "LOWER", "LABEL": "LOWER",
    "TEN": "NAME", "TÊN": "NAME", "PLACE": "NAME", "DATE": "NAME",
    "TRICH": "QUOTE", "TRÍCH": "QUOTE", "TRICHDAN": "QUOTE", "TRÍCHDẪN": "QUOTE",
    "VERSE": "QUOTE",
    "CHOT": "TITLE", "CHỐT": "TITLE", "CAUCHOT": "TITLE", "CÂUCHỐT": "TITLE", "PUNCH": "TITLE",
    "MOC": "STAMP", "MỘC": "STAMP", "DAU": "STAMP", "DẤU": "STAMP", "DAUMOC": "STAMP",
    "DẤUMỘC": "STAMP",
    "DANHSACH": "LIST", "DANHSÁCH": "LIST", "STEPS": "LIST", "CHECKLIST": "LIST",
    "SO": "STAT", "SỐ": "STAT", "SOLIEU": "STAT", "SỐLIỆU": "STAT", "NUMBER": "STAT",
    "COUNT": "STAT",
}

#: giới hạn số từ — vượt thì cảnh báo (vẫn dựng), chữ quá dài khó đọc trên hình
WORD_LIMITS = {"CHAPTER": 9, "LOWER": 9, "NAME": 8, "QUOTE": 55, "TITLE": 14,
               "STAMP": 6, "LIST": 7, "STAT": 3}

#: lớp (track) — LIST nằm riêng để giữ được qua nhiều cảnh, dấu mộc nằm trên cùng
LAYER_OF = {"LIST": "list", "STAMP": "stamp"}
LAYERS = ("list", "main", "stamp")


def normalize_kind(raw) -> str | None:
    key = re.sub(r"[\s_\-]+", "", str(raw or "")).upper()
    if not key:
        return None
    if key in KINDS:
        return key
    return ALIASES.get(key)


# --------------------------------------------------------------------------- #
# đọc file overlay
# --------------------------------------------------------------------------- #
@dataclass
class OverlayItem:
    scene: int
    kind: str
    text: str = ""
    sub: str = ""
    label: str = ""
    until: int | None = None
    start: float | None = None      # giây tính từ đầu cảnh
    dur: float | None = None        # giây hiện (để trống = hết cảnh / tới cảnh `until`)
    row: int = 0                    # số dòng trong file — để báo lỗi dễ tìm


COLS = {
    "scene": ("scene", "canh", "cảnh", "so canh", "số cảnh", "stt", "filename", "file"),
    "kind": ("type", "loai", "loại", "kind", "kieu", "kiểu"),
    "text": ("text", "chu", "chữ", "noi dung", "nội dung", "content"),
    "sub": ("sub", "phu", "phụ", "dong phu", "dòng phụ", "ref", "tham chieu", "tham chiếu",
            "nguon", "nguồn", "caption"),
    "label": ("label", "nhan", "nhãn"),
    "until": ("until", "den canh", "đến cảnh", "to"),
    "start": ("start", "bat dau", "bắt đầu", "delay"),
    "dur": ("dur", "duration", "giay", "giây", "thoi luong", "thời lượng"),
}
OVERLAY_PATTERNS = ("overlay", "do-hoa", "do_hoa", "dohoa", "đồ họa", "đồ hoạ")
OVERLAY_EXTS = (".xlsx", ".xlsm", ".csv", ".tsv")


def find_overlay_file(input_dir: Path | None) -> Path | None:
    """File overlay trong folder VIDEO: tên có chữ 'overlay' (vd overlay.xlsx,
    Ten-video_overlay.xlsx). Không có thì None."""
    if not input_dir:
        return None
    d = Path(input_dir)
    if not d.is_dir():
        return None
    found = [f for f in d.iterdir()
             if f.is_file() and f.suffix.lower() in OVERLAY_EXTS
             and not f.name.startswith(("~$", "."))
             and any(p in f.stem.lower() for p in OVERLAY_PATTERNS)]
    found.sort(key=lambda f: (f.suffix.lower() not in (".xlsx", ".xlsm"), f.name.lower()))
    return found[0] if found else None


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _read_rows(path: Path) -> list[list[str]]:
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(str(path), read_only=True, data_only=True)
        try:
            ws = None
            for name in wb.sheetnames:
                if name.strip().upper() in ("OVERLAY", "OVERLAYS", "ĐỒ HỌA", "DO HOA"):
                    ws = wb[name]
                    break
            ws = ws or wb[wb.sheetnames[0]]
            return [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    delim = "\t" if suf == ".tsv" or raw.count("\t") > raw.count(",") else ","
    return [[c.strip() for c in row] for row in csv.reader(raw.splitlines(), delimiter=delim)]


def _header_map(row: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, v in enumerate(row):
        key = v.strip().lower()
        for field_name, names in COLS.items():
            if field_name not in out and key in names:
                out[field_name] = i
    return out


def _num(v: str, cast=float):
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None
    try:
        return cast(float(v)) if cast is int else cast(v)
    except ValueError:
        raise ValueError(f"'{v}' không phải số")


def parse_overlay_rows(rows: list[list[str]]) -> tuple[list[OverlayItem], list[str]]:
    """(các mục, lỗi). Dòng đầu là tiêu đề nếu có tên cột quen; không có thì
    thứ tự cột mặc định: scene, type, text, sub, label, until, start, dur."""
    items: list[OverlayItem] = []
    errors: list[str] = []
    if not rows:
        return items, errors
    hmap = _header_map(rows[0])
    body = rows[1:] if ("scene" in hmap and "kind" in hmap) else rows
    if not ("scene" in hmap and "kind" in hmap):
        hmap = {k: i for i, k in enumerate(("scene", "kind", "text", "sub", "label",
                                            "until", "start", "dur"))}
    first = 2 if body is not rows else 1

    def get(row, key):
        i = hmap.get(key)
        return row[i].strip() if i is not None and i < len(row) and row[i] else ""

    for r, row in enumerate(body, start=first):
        if not any(c.strip() for c in row):
            continue
        scene_raw = get(row, "scene")
        kind_raw = get(row, "kind")
        if not scene_raw and not kind_raw:
            continue
        where = f"dòng {r}"
        m = re.search(r"\d+", scene_raw)
        if not m:
            errors.append(f"{where}: ô cảnh '{scene_raw}' không có số cảnh")
            continue
        kind = normalize_kind(kind_raw)
        if not kind:
            errors.append(f"{where}: loại '{kind_raw}' không hiểu — dùng "
                          + ", ".join(KINDS))
            continue
        try:
            until_raw = get(row, "until")
            um = re.search(r"\d+", until_raw)
            until = int(um.group()) if um else None
            start = _num(get(row, "start"))
            dur = _num(get(row, "dur"))
        except ValueError as e:
            errors.append(f"{where}: {e}")
            continue
        items.append(OverlayItem(scene=int(m.group()), kind=kind, text=get(row, "text"),
                                 sub=get(row, "sub"), label=get(row, "label"),
                                 until=until, start=start, dur=dur, row=r))
    return items, errors


def load_overlays(path: Path) -> tuple[list[OverlayItem], list[str]]:
    try:
        rows = _read_rows(Path(path))
    except Exception as e:
        return [], [f"không đọc được file {Path(path).name}: {e}"]
    return parse_overlay_rows(rows)


def check_items(items: list[OverlayItem], scene_numbers: Iterable[int]) -> tuple[list[str], list[str]]:
    """(lỗi, cảnh báo) so với các cảnh có thật của project."""
    nums = set(scene_numbers)
    errors: list[str] = []
    warns: list[str] = []
    lo, hi = (min(nums), max(nums)) if nums else (0, 0)
    for it in items:
        where = f"dòng {it.row} (cảnh {it.scene}, {it.kind})"
        if it.scene not in nums:
            errors.append(f"{where}: project không có cảnh {it.scene} (có {lo}–{hi})")
            continue
        if not it.text and not (it.kind == "LIST" and it.label):
            errors.append(f"{where}: chưa có chữ (cột text)")
        if it.until is not None:
            if it.until < it.scene:
                errors.append(f"{where}: 'until' {it.until} nhỏ hơn số cảnh")
            elif it.until not in nums:
                errors.append(f"{where}: 'until' {it.until} không phải cảnh có thật")
        if it.dur is not None and it.dur <= 0:
            errors.append(f"{where}: 'dur' phải lớn hơn 0")
        n = len(it.text.split())
        lim = WORD_LIMITS.get(it.kind, 99)
        if n > lim:
            warns.append(f"{where}: {n} từ, dài hơn mức dễ đọc ({lim} từ)")
    return errors, warns


# --------------------------------------------------------------------------- #
# kiểu chữ
# --------------------------------------------------------------------------- #
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
                f"|{int(self.subs_on)}")


WHITE = (246, 241, 232)
CREAM = (226, 214, 190)
PANEL = (14, 12, 10)

FONT_FILES = {
    "serif_semibold": "EBGaramond-SemiBold.ttf",
    "serif_italic": "EBGaramond-Italic.ttf",
    "serif_italic_med": "EBGaramond-MediumItalic.ttf",
    "sans_med": "Montserrat-Medium.ttf",
    "sans_bold": "Montserrat-Bold.ttf",
    "sans_black": "Montserrat-ExtraBold.ttf",
    "condensed": "Oswald-Bold.ttf",
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


@lru_cache(maxsize=256)
def font(role: str, px: int):
    from PIL import ImageFont
    path = _font_path(role)
    px = max(6, int(round(px)))
    if path:
        return ImageFont.truetype(path, px)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", px)
    except Exception:
        return ImageFont.load_default()


def fonts_ok() -> bool:
    return all(_font_path(r) for r in FONT_FILES)


# --------------------------------------------------------------------------- #
# vẽ
# --------------------------------------------------------------------------- #
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


@dataclass
class Frame:
    """Thông tin cho một ảnh cần vẽ."""
    item: OverlayItem
    words: int | None = None        # QUOTE: số từ đã hiện (None = tất cả)
    list_items: tuple[str, ...] = ()  # LIST: các mục đang hiện
    list_label: str = ""


def render_frame(fr: Frame, w: int, h: int, st: OverlayStyle):
    """Ảnh RGBA w×h trong suốt chứa đúng một đồ họa."""
    from PIL import Image
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    k = min(w, h) / 1080.0 * st.scale
    fn = _RENDERERS[fr.item.kind]
    fn(img, fr, k, st)
    return img


def _r_chapter(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    _gradient(img, h * (0.42 if st.subs_on else 0.52), h, 0.0, 0.78)
    main = it.text.upper()
    fm = font("sans_bold", 31 * k)
    tr = 31 * k * 0.20
    lines = _balanced(fm, main, w * 0.62, tr)[:2]
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
        # vạch mảnh hai bên
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
    x = w * 0.055
    bottom = h * (0.78 if st.subs_on else 0.875)
    if serif:
        fm = font("serif_italic_med", 50 * k)
    else:
        fm = font("sans_bold", 38 * k)
    lines = _balanced(fm, it.text, w * 0.52)[:2]
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
    """Bố cục cố định của hộp trích dẫn: [(dòng, [(từ, x, y)])], cỡ hộp.
    Tính MỘT lần từ toàn bộ câu, nên lúc hiện dần chữ không nhảy chỗ."""
    size = 46
    for size in (46, 42, 38, 34, 30):
        f = font("serif_italic", size * k)
        lines = _balanced(f, text, w * 0.50)
        if len(lines) <= 6:
            break
    lh = _line_h(f) * 1.08
    return f, lines, lh


def _r_quote(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    f, lines, lh = quote_layout(it.text, w, h, k)
    fr_ref = font("sans_bold", 18 * k)
    tr = 18 * k * 0.24
    ref = it.sub.upper()
    tw = max(f.getlength(ln) for ln in lines) if lines else 0
    padx, pady = 56 * k, 40 * k
    bw = max(tw, _text_w(fr_ref, ref, tr)) + padx * 2
    bw = max(bw, w * 0.36)
    ref_h = (_line_h(fr_ref) + 30 * k) if ref else 0
    bh = lh * len(lines) + pady * 2 + ref_h
    x0, y0 = (w - bw) / 2, (h - bh) / 2
    box = (x0, y0, x0 + bw, y0 + bh)
    _panel(img, box, st.box_alpha)
    d = ImageDraw.Draw(img)
    lw = max(1, int(round(1.6 * k)))
    d.rectangle([box[0], box[1], box[2], box[3]], outline=st.acc + (110,), width=lw)
    d.line([(box[0], box[1]), (box[2], box[1])], fill=st.acc + (255,), width=max(2, int(3 * k)))
    # chữ: chỉ vẽ `words` từ đầu, mỗi từ ở đúng chỗ của nó trong bố cục đầy đủ
    limit = fr.words if fr.words is not None else 10 ** 9
    shown = 0
    y = y0 + pady
    space = f.getlength(" ")
    for ln in lines:
        lw_ = f.getlength(ln)
        x = (w - lw_) / 2
        for word in ln.split(" "):
            if shown >= limit:
                break
            d.text((x, y), word, font=f, fill=WHITE + (255,))
            x += f.getlength(word) + space
            shown += 1
        y += lh
    if ref and (fr.words is None or fr.words >= len(it.text.split())):
        ry = box[3] - pady - _line_h(fr_ref) + 6 * k
        rw = _text_w(fr_ref, ref, tr)
        _draw_tracked(d, ((w - rw) / 2, ry), ref, fr_ref, st.acc + (255,), tr)
        d.line([((w - 60 * k) / 2, ry - 16 * k), ((w + 60 * k) / 2, ry - 16 * k)],
               fill=st.acc + (200,), width=max(1, int(1.5 * k)))


def _r_title(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    _panel(img, (0, 0, w, h), 0.30, fill=(0, 0, 0))
    _vignette(img, 0.55)
    fm = font("sans_black", 66 * k)
    lines = _balanced(fm, it.text.upper(), w * 0.70)[:3]
    if len(lines) == 3:
        fm = font("sans_black", 56 * k)
        lines = _balanced(fm, it.text.upper(), w * 0.74)[:3]
    lh = _line_h(fm) * 1.05
    fs = font("serif_italic", 36 * k)
    sub_lines = _balanced(fs, it.sub, w * 0.6)[:2] if it.sub else []
    slh = _line_h(fs) * 1.05
    total = lh * len(lines) + (24 * k + slh * len(sub_lines) if sub_lines else 0)
    y0 = (h - total) / 2

    def draw(d, shadow):
        y = y0
        for ln in lines:
            lw = fm.getlength(ln)
            d.text(((w - lw) / 2, y), ln, font=fm, fill=shadow or (WHITE + (255,)))
            y += lh
        y += 24 * k
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
    lines = _balanced(f, text, w * 0.46, tr)[:2]
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
    # vết mực loang: đục lỗ ngẫu nhiên (cố định theo chữ để hai lần dựng giống nhau)
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


def _r_list(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    x, y = w * 0.04, h * 0.055
    label = (fr.list_label or fr.item.label or "").upper()
    fl = font("sans_bold", 19 * k)
    tr = 19 * k * 0.24
    d = ImageDraw.Draw(img)
    if label:
        px, py = 16 * k, 9 * k
        tw = _text_w(fl, label, tr)
        bh = _line_h(fl) + py * 2
        _panel(img, (x, y, x + tw + px * 2, y + bh), min(1.0, st.box_alpha + 0.08))
        d = ImageDraw.Draw(img)
        _draw_tracked(d, (x + px, y + py), label, fl, st.acc + (255,), tr)
        y += bh + 10 * k
    fn = font("sans_bold", 21 * k)
    fi = font("sans_bold", 27 * k)
    for i, item in enumerate(fr.list_items, start=1):
        num = f"{i:02d}"
        px, py = 14 * k, 9 * k
        nw = fn.getlength(num)
        iw = fi.getlength(item)
        bh = _line_h(fi) + py * 2
        _panel(img, (x, y, x + px * 3 + nw + iw, y + bh), st.box_alpha)
        d = ImageDraw.Draw(img)
        d.text((x + px, y + py + (_line_h(fi) - _line_h(fn)) / 2), num, font=fn,
               fill=st.acc + (255,))
        d.text((x + px * 2 + nw, y + py), item, font=fi, fill=WHITE + (255,))
        y += bh + 8 * k


def _r_stat(img, fr, k, st):
    from PIL import ImageDraw
    w, h = img.size
    it = fr.item
    fnum = font("sans_black", 104 * k)
    flab = font("sans_bold", 19 * k)
    tr = 19 * k * 0.22
    lab_lines = _balanced(flab, it.sub.upper(), w * 0.20, tr)[:3] if it.sub else []
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


_RENDERERS = {"CHAPTER": _r_chapter, "LOWER": _r_lower, "NAME": _r_name, "QUOTE": _r_quote,
              "TITLE": _r_title, "STAMP": _r_stamp, "LIST": _r_list, "STAT": _r_stat}


# --------------------------------------------------------------------------- #
# lập lịch
# --------------------------------------------------------------------------- #
DELAY = 0.35        # chữ hiện sau khi cảnh bắt đầu (giây)
TAIL = 0.15         # tắt trước khi cảnh kết thúc
FADE_IN = 0.35
FADE_OUT = 0.30
QUOTE_BOX_ONLY = 0.30   # hộp trích dẫn hiện rỗng trước rồi chữ mới chạy
MAX_STEPS = 14          # số ảnh tối đa cho hiệu ứng đánh máy
MIN_SHOW = 0.6


@dataclass
class Placement:
    """Một ảnh phủ trên trục NỘI DUNG."""
    frame: Frame
    start: float
    length: float
    layer: str = "main"
    fade_in: float = 0.0
    fade_out: float = 0.0
    scene: int = 0
    png: Path | None = None
    track: int = 0                  # số track trong lớp (khi hai đồ họa chồng giờ)

    @property
    def end(self) -> float:
        return self.start + self.length


def _steps(n_words: int) -> list[int]:
    """Số từ hiện sau mỗi bước của hiệu ứng đánh máy (tăng dần, kết thúc = n)."""
    if n_words <= 0:
        return []
    k = min(MAX_STEPS, n_words)
    return sorted({max(1, round(n_words * (i + 1) / k)) for i in range(k)})


def schedule(items: list[OverlayItem], plan: list[ScenePlan], st: OverlayStyle,
             log: LogFn = print) -> list[Placement]:
    """Đổi các dòng overlay thành danh sách ảnh + thời gian, theo `plan`
    (trục nội dung). Mục có cảnh không nằm trong plan bị bỏ qua."""
    by_num = {p.number: p for p in plan}
    nums = [p.number for p in plan]
    out: list[Placement] = []

    def window(it: OverlayItem, first_delay: float = DELAY) -> tuple[float, float] | None:
        p = by_num.get(it.scene)
        if not p:
            return None
        last = by_num.get(it.until) if it.until else p
        if last is None:
            last = p
        delay = it.start if it.start is not None else min(first_delay, p.slot_duration * 0.2)
        t0 = p.start + max(0.0, delay)
        t1 = last.end - TAIL
        if it.dur is not None:
            # có 'until' thì dur chỉ được rút ngắn; không có thì dur quyết định
            t1 = min(t1, t0 + it.dur) if it.until else t0 + it.dur
        if t1 - t0 < MIN_SHOW:
            t1 = t0 + MIN_SHOW
        return t0, t1

    lists: dict[str, list[OverlayItem]] = {}
    order: list[str] = []
    for it in items:
        if it.scene not in by_num:
            continue
        if it.kind == "LIST":
            key = it.label.strip().upper() or "_"
            if key not in lists:
                lists[key] = []
                order.append(key)
            lists[key].append(it)
            continue
        win = window(it, 0.6 if it.kind == "STAMP" else DELAY)
        if not win:
            continue
        t0, t1 = win
        layer = LAYER_OF.get(it.kind, "main")
        if it.kind == "QUOTE" and st.typewriter and len(it.text.split()) > 1:
            n = len(it.text.split())
            total = t1 - t0
            box_only = min(QUOTE_BOX_ONLY, total * 0.15)
            reveal = max(0.8, min(len(it.text) * 0.032, total * 0.45, 4.0))
            steps = _steps(n)
            pieces: list[tuple[Frame, float, float]] = [(Frame(it, words=0), t0, box_only)]
            t = t0 + box_only
            dt = reveal / len(steps)
            for i, wc in enumerate(steps):
                ln = dt if i < len(steps) - 1 else (t1 - t)
                pieces.append((Frame(it, words=None if wc >= n else wc), t, ln))
                t += dt
            for i, (fr, s0, ln) in enumerate(pieces):
                out.append(Placement(fr, s0, max(0.04, ln), layer,
                                     FADE_IN if i == 0 else 0.0,
                                     FADE_OUT if i == len(pieces) - 1 else 0.0, it.scene))
        else:
            out.append(Placement(Frame(it), t0, t1 - t0, layer, FADE_IN, FADE_OUT, it.scene))

    # danh sách: mỗi mục mới thay ảnh trước bằng ảnh có thêm một dòng
    for key in order:
        group = sorted(lists[key], key=lambda x: (nums.index(x.scene), x.row))
        label = next((g.label for g in group if g.label), "")
        entries = [g for g in group if g.text]
        end_it = max(group, key=lambda g: (g.until or g.scene))
        last_scene = end_it.until or end_it.scene
        first = group[0]
        t_first, _ = window(first)
        p_last = by_num.get(last_scene) or by_num[group[-1].scene]
        t_end = p_last.end - TAIL
        if any(g.dur for g in group):
            t_end = min(t_end, max(t_first + g.dur for g in group if g.dur))
        marks: list[tuple[float, tuple[str, ...]]] = []
        shown: list[str] = []
        if not entries or entries[0] is not first:
            marks.append((t_first, ()))
        for g in entries:
            ts, _ = window(g)
            shown.append(g.text)
            marks.append((max(ts, t_first), tuple(shown)))
        marks.sort(key=lambda m: m[0])
        for i, (ts, its) in enumerate(marks):
            te = marks[i + 1][0] if i + 1 < len(marks) else t_end
            if te - ts < 0.04:
                continue
            fr = Frame(first, list_items=its, list_label=label)
            out.append(Placement(fr, ts, te - ts, "list", FADE_IN if i == 0 else 0.0,
                                 FADE_OUT if i == len(marks) - 1 else 0.0, first.scene))

    _assign_tracks(out, log)
    out.sort(key=lambda p: (LAYERS.index(p.layer), p.track, p.start))
    return out


def _assign_tracks(pls: list[Placement], log: LogFn) -> None:
    """Hai đồ họa cùng lớp chồng giờ nhau → đặt sang track thứ hai (và báo)."""
    by_layer: dict[str, list[Placement]] = {}
    for p in pls:
        by_layer.setdefault(p.layer, []).append(p)
    for layer, group in by_layer.items():
        ends: list[float] = []
        warned: set[int] = set()
        # các bước đánh máy của cùng một câu luôn nối nhau, không chồng
        for p in sorted(group, key=lambda x: (x.start, x.scene)):
            for i, e in enumerate(ends):
                if e <= p.start + 1e-6:
                    p.track = i
                    ends[i] = p.end
                    break
            else:
                p.track = len(ends)
                ends.append(p.end)
            if p.track > 0 and p.scene not in warned:
                warned.add(p.scene)
                log(f"[WARN] Đồ họa chữ: cảnh {p.scene} có hai đồ họa '{layer}' cùng lúc "
                    "— đặt chồng lên nhau, nên xem lại")


# --------------------------------------------------------------------------- #
# ghi PNG
# --------------------------------------------------------------------------- #
def _frame_key(fr: Frame, w: int, h: int, st: OverlayStyle) -> str:
    it = fr.item
    raw = "|".join([it.kind, it.text, it.sub, it.label, str(fr.words), "/".join(fr.list_items),
                    fr.list_label, f"{w}x{h}", st.key()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def write_pngs(pls: list[Placement], out_dir: Path, w: int, h: int, st: OverlayStyle,
               log: LogFn = print, cancel=None) -> int:
    """Vẽ mọi ảnh cần thiết vào `out_dir` (xoá ảnh cũ của tool trước). Ảnh trùng
    nội dung dùng chung một file. Trả về số file đã vẽ."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("ov_*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    cache: dict[str, Path] = {}
    for p in pls:
        if cancel and cancel():
            from .media import Cancelled
            raise Cancelled()
        key = _frame_key(p.frame, w, h, st)
        path = cache.get(key)
        if path is None:
            path = out_dir / f"ov_{p.scene:04d}_{p.frame.item.kind.lower()}_{key}.png"
            render_frame(p.frame, w, h, st).save(path, optimize=False, compress_level=6)
            cache[key] = path
        p.png = path
    return len(cache)


def prepare(s, plan: list[ScenePlan], out_dir: Path, log: LogFn = print,
            cancel=None, size: tuple[int, int] | None = None) -> list[Placement]:
    """Đọc file overlay của project, lập lịch theo `plan` và vẽ PNG.
    Không bật / không có file → []. Lỗi trong file → BuildError."""
    from .media import BuildError
    if not getattr(s, "enable_overlays", True):
        return []
    path = overlay_file(s)
    if not path:
        return []
    items, errors = load_overlays(path)
    e2, warns = check_items(items, [p.number for p in plan])
    errors += e2
    if errors:
        for e in errors:
            log(f"[FAIL] Đồ họa chữ: {e}")
        raise BuildError(f"File đồ họa chữ {path.name} có {len(errors)} lỗi — xem nhật ký")
    for wmsg in warns[:20]:
        log(f"[WARN] Đồ họa chữ: {wmsg}")
    if not fonts_ok():
        log("[WARN] Đồ họa chữ: thiếu font trong assets/overlay-fonts → dùng font thay thế")
    st = OverlayStyle.from_settings(s)
    pls = schedule(items, plan, st, log)
    w, h = size or (int(s.width), int(s.height))
    n = write_pngs(pls, out_dir, w, h, st, log, cancel)
    log(f"[BUILD] Đồ họa chữ: {len(items)} mục từ {path.name} → {n} ảnh, {len(pls)} đoạn")
    return pls


def overlay_file(s) -> Path | None:
    explicit = getattr(s, "overlay_file", None)
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    return find_overlay_file(getattr(s, "input_dir", None))


def summary(items: list[OverlayItem]) -> str:
    counts: dict[str, int] = {}
    for it in items:
        counts[it.kind] = counts.get(it.kind, 0) + 1
    return ", ".join(f"{KINDS[k][0]} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def preview_sheet(items: list[OverlayItem], w: int, h: int, st: OverlayStyle, background=None,
                  cols: int = 3, limit: int = 24):
    """Ảnh xem thử: mỗi đồ họa (trạng thái cuối) vẽ trên nền, ghép lưới.
    `background` = một ảnh PIL dùng chung, hoặc hàm(số cảnh) → ảnh PIL | None."""
    from PIL import Image, ImageDraw
    tw, th = 640, int(640 * h / w)
    shown = items[:limit]
    rows = max(1, math.ceil(len(shown) / cols))
    sheet = Image.new("RGB", (tw * cols, th * rows), (30, 30, 30))
    lists: dict[str, list[str]] = {}
    for i, it in enumerate(shown):
        if it.kind == "LIST":
            key = it.label.upper()
            lists.setdefault(key, [])
            if it.text:
                lists[key].append(it.text)
            fr = Frame(it, list_items=tuple(lists[key]), list_label=it.label)
        else:
            fr = Frame(it)
        bg = background(it.scene) if callable(background) else background
        if bg is not None:
            base = _cover(bg, w, h)
        else:
            base = Image.new("RGBA", (w, h), (92, 84, 72, 255))
        base.alpha_composite(render_frame(fr, w, h, st))
        tile = base.convert("RGB").resize((tw, th))
        d = ImageDraw.Draw(tile)
        d.rectangle((0, 0, 150, 20), fill=(0, 0, 0))
        d.text((6, 4), f"{it.scene} · {it.kind}", fill=(255, 230, 0))
        sheet.paste(tile, ((i % cols) * tw, (i // cols) * th))
    return sheet


def _cover(img, w: int, h: int):
    """Phủ kín khung w×h như ảnh cảnh trong video (cắt giữa, không méo)."""
    from PIL import Image
    img = img.convert("RGBA")
    k = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                     Image.BILINEAR)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def scene_image(input_dir: Path, scene: int):
    """Ảnh của cảnh (Images/<số>.*) để làm nền xem thử; không có thì None."""
    from PIL import Image
    from .models import IMAGE_EXTS
    d = Path(input_dir) / "Images"
    if not d.is_dir():
        return None
    for f in d.iterdir():
        if f.suffix.lower() in IMAGE_EXTS and re.fullmatch(r"0*%d" % scene, f.stem):
            try:
                return Image.open(f)
            except Exception:
                return None
    return None


def preview_file(items: list[OverlayItem], s, out: Path) -> Path:
    st = OverlayStyle.from_settings(s)
    sheet = preview_sheet(items, int(s.width), int(s.height), st,
                          background=lambda n: scene_image(s.input_dir, n))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


TEMPLATE_ROWS = [
    ["scene", "type", "text", "sub", "label", "until", "start", "dur"],
    ["1", "CHAPTER", "When the righteous are finally revealed", "1 Enoch 38", "", "", "", ""],
    ["2", "LOWER", "The kings and the powerful", "", "Will no longer be exalted", "", "", ""],
    ["3", "QUOTE", "They shall not be able to behold the face of the holy", "1 Enoch 38:4",
     "", "", "", ""],
    ["4", "STAMP", "His light. On their faces.", "", "", "", "", ""],
    ["5", "LIST", "One on the face", "", "Three marks", "9", "", ""],
    ["7", "LIST", "One on the forehead", "", "Three marks", "", "", ""],
    ["9", "LIST", "One where no one can see", "", "Three marks", "", "", ""],
    ["10", "TITLE", "The one who carries it does not know it is there", "Other people see it.",
     "", "", "", ""],
    ["12", "STAT", "~11", "copies found at Qumran", "", "", "", ""],
    ["14", "NAME", "Jean Starcky · 1964", "", "The Aramaic text", "", "", ""],
]

GUIDE_ROWS = [
    ["Cột", "Ý nghĩa"],
    ["scene", "Số cảnh (khớp số file Audio). 0007 hay 7 đều được."],
    ["type", "Loại đồ họa: " + ", ".join(f"{k} = {v[0]}" for k, v in KINDS.items())],
    ["text", "Chữ chính. LIST: tên mục. STAT: con số."],
    ["sub", "Dòng phụ: tham chiếu của QUOTE, nguồn của CHAPTER, dòng nghiêng của TITLE, "
            "nhãn của STAT."],
    ["label", "Nhãn nhỏ in hoa: LOWER/NAME (dòng trên hộp), LIST (tên danh sách — các dòng "
              "LIST cùng label cộng dồn thành một danh sách)."],
    ["until", "Giữ tới hết cảnh số này (LIST, QUOTE dài…). Để trống = hết cảnh của dòng."],
    ["start", "Hiện sau bao nhiêu giây kể từ đầu cảnh (trống = 0.35 giây)."],
    ["dur", "Hiện bao nhiêu giây (trống = tới hết cảnh / tới cảnh 'until')."],
]


def write_template(dest: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "OVERLAY"
    for r in TEMPLATE_ROWS:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="10B981")
    for col, wd in zip("ABCDEFGH", (8, 11, 60, 26, 26, 8, 8, 8)):
        ws.column_dimensions[col].width = wd
    for row in ws.iter_rows(min_row=2):
        row[2].alignment = Alignment(wrap_text=True)
    g = wb.create_sheet("HUONG DAN")
    for r in GUIDE_ROWS:
        g.append(r)
    g.column_dimensions["A"].width = 10
    g.column_dimensions["B"].width = 110
    for c in g[1]:
        c.font = Font(bold=True)
    wb.save(str(dest))
    return Path(dest)
