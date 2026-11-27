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
import re
from dataclasses import dataclass
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
    "NAME": ("Nhãn tên", "như Nhãn dưới nhưng chữ chính là serif nghiêng (tên người, năm)"),
    "QUOTE": ("Hộp trích dẫn", "hộp giữa khung, chữ hiện từng ký tự như đánh máy theo giọng đọc, tham chiếu ở dưới"),
    "TITLE": ("Câu chốt", "chữ in hoa trắng đậm giữa màn hình, nền tối dần, dòng phụ nghiêng"),
    "STAMP": ("Dấu mộc", "con dấu đỏ nghiêng đóng xuống — dùng rất ít"),
    "LIST": ("Danh sách", "nhãn góc trên trái + các mục đánh số 01, 02… trượt vào lần lượt qua nhiều cảnh"),
    "STAT": ("Ô số liệu", "số lớn trong hộp viền màu nhấn, nhãn nhỏ bên dưới, góc trên phải"),
    # 0.6.4
    "PLACE": ("Mốc nơi chốn", "tên nơi + năm/thời điểm, chữ máy đánh góc trên trái (kiểu phim tài liệu)"),
    "TERM": ("Thẻ từ gốc", "từ phiên âm | chữ gốc Hebrew/Hy Lạp, nghĩa (sub), ngôn ngữ (label) — bên phải"),
    "VS": ("So sánh", "hai cột: text (trái) đối sub (phải), label = tiêu đề; hai cột trượt vào từ hai bên"),
    "TIMELINE": ("Dòng thời gian", "các mốc cách nhau bằng | (vd 1446 BC | *586 BC* | 70 AD), vạch chạy từ trái"),
    "KEYWORD": ("Từ khóa", "một từ/cụm rất lớn giữa khung, gạch chân màu nhấn chạy ra; label = dòng nhỏ phía trên"),
    "SOURCE": ("Nguồn", "chú thích nguồn nhỏ góc dưới phải (sách, học giả, bản thảo)"),
    "NOTE": ("Giấy cổ", "tờ giấy cổ giữa khung, chữ mực hiện như đang viết; sub = người viết / văn bản"),
    "CINEMA": ("Khung điện ảnh", "hai thanh đen trượt vào trên dưới (2,39:1); text = chú thích nhỏ (có thể trống)"),
    "SUBSCRIBE": ("Nút đăng ký", "nút Subscribe đỏ + chuông góc dưới phải; sub = câu mời nhỏ"),
}

#: tên khác mà người dùng hay gõ → key chuẩn
ALIASES = {
    "CHUONG": "CHAPTER", "CHƯƠNG": "CHAPTER", "CHAP": "CHAPTER", "SECTION": "CHAPTER",
    "NHAN": "LOWER", "NHÃN": "LOWER", "LOWER3": "LOWER", "LOWERTHIRD": "LOWER", "TAG": "LOWER",
    "CALLOUT": "LOWER", "LABEL": "LOWER",
    "TEN": "NAME", "TÊN": "NAME",
    "TRICH": "QUOTE", "TRÍCH": "QUOTE", "TRICHDAN": "QUOTE", "TRÍCHDẪN": "QUOTE",
    "VERSE": "QUOTE",
    "CHOT": "TITLE", "CHỐT": "TITLE", "CAUCHOT": "TITLE", "CÂUCHỐT": "TITLE", "PUNCH": "TITLE",
    "MOC": "STAMP", "MỘC": "STAMP", "DAU": "STAMP", "DẤU": "STAMP", "DAUMOC": "STAMP",
    "DẤUMỘC": "STAMP",
    "DANHSACH": "LIST", "DANHSÁCH": "LIST", "STEPS": "LIST", "CHECKLIST": "LIST",
    "SO": "STAT", "SỐ": "STAT", "SOLIEU": "STAT", "SỐLIỆU": "STAT", "NUMBER": "STAT",
    "COUNT": "STAT",
    "DATE": "PLACE", "LOCATION": "PLACE", "DATELINE": "PLACE", "DIADIEM": "PLACE",
    "ĐỊAĐIỂM": "PLACE", "NOICHON": "PLACE", "NƠICHỐN": "PLACE",
    "WORD": "TERM", "TUGOC": "TERM", "TỪGỐC": "TERM", "DINHNGHIA": "TERM", "ĐỊNHNGHĨA": "TERM",
    "DEFINITION": "TERM", "ORIGIN": "TERM",
    "VERSUS": "VS", "COMPARE": "VS", "SOSANH": "VS", "SOSÁNH": "VS", "SOSANHHAI": "VS",
    "DONGTHOIGIAN": "TIMELINE", "DÒNGTHỜIGIAN": "TIMELINE", "TIME": "TIMELINE", "ERA": "TIMELINE",
    "TUKHOA": "KEYWORD", "TỪKHÓA": "KEYWORD", "TỪKHOÁ": "KEYWORD", "EMPHASIS": "KEYWORD",
    "NHANMANH": "KEYWORD", "NHẤNMẠNH": "KEYWORD", "BIGWORD": "KEYWORD",
    "NGUON": "SOURCE", "NGUỒN": "SOURCE", "CITE": "SOURCE", "CITATION": "SOURCE", "REF": "SOURCE",
    "GIAYCO": "NOTE", "GIẤYCỔ": "NOTE", "DOCUMENT": "NOTE", "LETTER": "NOTE", "PARCHMENT": "NOTE",
    "SCROLL": "NOTE", "MANUSCRIPT": "NOTE",
    "LETTERBOX": "CINEMA", "DIENANH": "CINEMA", "ĐIỆNẢNH": "CINEMA", "KHUNGDIENANH": "CINEMA",
    "CINEMATIC": "CINEMA", "BARS": "CINEMA",
    "DANGKY": "SUBSCRIBE", "ĐĂNGKÝ": "SUBSCRIBE", "SUB": "SUBSCRIBE", "CTA": "SUBSCRIBE",
}

#: giới hạn số từ — vượt thì cảnh báo (vẫn dựng), chữ quá dài khó đọc trên hình
WORD_LIMITS = {"CHAPTER": 9, "LOWER": 9, "NAME": 8, "QUOTE": 55, "TITLE": 14,
               "STAMP": 6, "LIST": 7, "STAT": 3, "PLACE": 5, "TERM": 4, "VS": 8,
               "TIMELINE": 18, "KEYWORD": 4, "SOURCE": 14, "NOTE": 60, "CINEMA": 8,
               "SUBSCRIBE": 3}

#: lớp (track), dưới lên trên: khung điện ảnh, danh sách, đồ họa thường, chữ đánh
#: máy / phần chạy, dấu mộc
LAYER_OF = {"LIST": "list", "STAMP": "stamp", "CINEMA": "frame"}
LAYERS = ("frame", "list", "main", "text", "stamp")
#: kiểu được phép để trống cột text
TEXT_OPTIONAL = {"CINEMA", "SUBSCRIBE"}


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
        if not it.text and not (it.kind == "LIST" and it.label) and it.kind not in TEXT_OPTIONAL:
            errors.append(f"{where}: chưa có chữ (cột text)")
        if it.kind == "VS" and it.text and not it.sub:
            errors.append(f"{where}: So sánh cần cả cột sub (bên phải)")
        if it.kind == "TIMELINE" and it.text and len(timeline_points(it.text)) < 2:
            errors.append(f"{where}: Dòng thời gian cần ít nhất 2 mốc, cách nhau bằng |")
        if it.until is not None:
            if it.until < it.scene:
                errors.append(f"{where}: 'until' {it.until} nhỏ hơn số cảnh")
            elif it.until not in nums:
                errors.append(f"{where}: 'until' {it.until} không phải cảnh có thật")
        if it.dur is not None and it.dur <= 0:
            errors.append(f"{where}: 'dur' phải lớn hơn 0")
        n = len(it.text.replace("|", " ").split())
        lim = WORD_LIMITS.get(it.kind, 99)
        if n > lim:
            warns.append(f"{where}: {n} từ, dài hơn mức dễ đọc ({lim} từ)")
    return errors, warns


# --------------------------------------------------------------------------- #
# vẽ — overlay_draw.py (0.6.4); tên cũ vẫn dùng được qua module này
# --------------------------------------------------------------------------- #
from .overlay_draw import (  # noqa: E402,F401
    BASE_SIZE, CREAM, FONT_FILES, PANEL, WHITE, Frame, OverlayStyle, _balanced, _line_h,
    _RENDERERS, _text_w, _wrap, cinema_bar, font, font_dirs, fonts_ok, marks, plain,
    quote_layout, render_frame, timeline_points, typed_length,
)
from . import motion as mo  # noqa: E402


# --------------------------------------------------------------------------- #
# lập lịch
# --------------------------------------------------------------------------- #
DELAY = 0.35        # chữ hiện sau khi cảnh bắt đầu (giây)
TAIL = 0.15         # tắt trước khi cảnh kết thúc
FADE_IN = 0.35      # (0.6.0–0.6.3) giữ cho mã cũ; 0.6.4 lấy theo kiểu chuyển động
FADE_OUT = 0.30
QUOTE_BOX_ONLY = 0.30   # hộp trích dẫn hiện rỗng trước rồi chữ mới chạy
MAX_STEPS = 14          # (0.6.0–0.6.3) số bước đánh máy theo từ — 0.6.4 đánh theo ký tự
MIN_SHOW = 0.6
TYPE_CPS = 22.0         # đánh máy khi không khớp giọng: ký tự / giây
PLACE_CPS = 16.0        # mốc nơi chốn gõ chậm hơn cho có chất máy chữ
MIN_TYPE_STEP = 1 / 30  # hai bước đánh máy cách nhau ít nhất một khung hình
MAX_TYPE_FRAMES = 480   # trần số ảnh của một câu đánh máy (câu rất dài thì gộp ký tự)
WIPE_STEPS = 12         # gạch chân từ khóa chạy ra
WIPE_DUR = 0.50
TL_STEPS = 24           # vạch dòng thời gian chạy
TL_DUR = 1.40

#: kiểu chuyển động chính của từng loại (xem motion.PRESETS)
MOTION_OF = {"CHAPTER": "rise", "LOWER": "slide_left", "NAME": "slide_left", "QUOTE": "pop",
             "TITLE": "settle", "STAMP": "slam", "LIST": "slide_left", "STAT": "drop",
             "PLACE": "slide_left", "TERM": "slide_right", "VS": "slide_left", "TIMELINE": "fade",
             "KEYWORD": "settle", "SOURCE": "rise", "NOTE": "pop", "CINEMA": "bar_top",
             "SUBSCRIBE": "slide_right"}
#: kiểu có chữ đánh máy: phần nền → phần chữ
TYPED = {"QUOTE": "box", "NOTE": "card", "PLACE": "box"}


@dataclass
class Placement:
    """Một ảnh phủ trên trục NỘI DUNG."""
    frame: Frame
    start: float
    length: float
    layer: str = "main"
    fade_in: float = 0.0            # thời gian hiện rõ (alpha 0 → 1); 0 = không có đoạn hiện
    fade_out: float = 0.0           # thời gian tắt; 0 = tắt ngay (mẩu giữa của chuỗi đánh máy)
    scene: int = 0
    png: Path | None = None
    track: int = 0                  # số track trong lớp (khi hai đồ họa chồng giờ)
    motion: str = "fade"            # tên trong motion.PRESETS
    group: str = ""                 # chuỗi ảnh nối nhau (đánh máy, vạch chạy) — render gộp làm một
    stacked: bool = False           # cố ý chồng giờ với phần khác của cùng đồ họa
    bbox: tuple[int, int, int, int] | None = None   # vùng có hình (sau khi vẽ PNG)
    clip: Path | None = None        # 0.7.0: clip Remotion (ProRes 4444 có alpha) thay cho PNG
    clip_box: dict | None = None    # 0.7.3: clip đã cắt gọn — {x, y, w, h, W, H}; None = trọn khung

    @property
    def end(self) -> float:
        return self.start + self.length

    @property
    def anchor(self) -> tuple[float, float] | None:
        if not self.bbox:
            return None
        x0, y0, x1, y1 = self.bbox
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def placement_motion(pl: Placement, w: int, h: int) -> tuple[mo.Motion, bool, bool]:
    """(chuyển động, có đoạn hiện, có đoạn tắt) của một ảnh."""
    if pl.motion in ("bar_top", "bar_bottom"):
        bar = max(cinema_bar(w, h), h * 0.09) / h
        m = mo.bar_motion(pl.motion, bar + 0.004)
    elif pl.motion == "none" or pl.motion not in mo.PRESETS:
        m = mo.Motion(din=pl.fade_in, dout=pl.fade_out, ain=pl.fade_in)
    else:
        m = mo.PRESETS[pl.motion]
    return m, pl.fade_in > 0, pl.fade_out > 0


def _new(fr: Frame, start: float, end: float, layer: str, motion: str, scene: int,
         fade_in: bool = True, fade_out: bool = True, **kw) -> Placement:
    m = mo.get(motion)
    fi = (m.ain or m.din) if fade_in else 0.0
    fo = m.dout if fade_out else 0.0
    return Placement(fr, start, max(0.04, end - start), layer, fi, fo, scene, motion=motion, **kw)


def _steps(n_words: int) -> list[int]:
    """(0.6.0–0.6.3) Số từ hiện sau mỗi bước của hiệu ứng đánh máy theo từ."""
    if n_words <= 0:
        return []
    k = min(MAX_STEPS, n_words)
    return sorted({max(1, round(n_words * (i + 1) / k)) for i in range(k)})


def _seq(it: OverlayItem, plan: list[ScenePlan], pos: dict[int, int], words) -> list:
    """Lời đọc (từ, giây bắt đầu, giây kết thúc — trục nội dung) từ cảnh của mục
    tới cảnh `until`."""
    if not words or it.scene not in pos:
        return []
    i0 = pos[it.scene]
    i1 = pos.get(it.until, i0) if it.until else i0
    seq = []
    for p in plan[i0:max(i0, i1) + 1]:
        for w, a, b in words.get(p.number, ()):
            seq.append((w, p.start + a, p.start + b))
    return seq


def spoken_start(it: OverlayItem, seq: list) -> float | None:
    """Lúc giọng đọc bắt đầu nói tới chữ của đồ họa (None = không tìm thấy)."""
    from . import speech
    if not seq:
        return None
    flat = [w for w, _, _ in seq]
    texts = [it.text]
    if it.kind in ("CHAPTER", "STAT") and it.sub:
        texts.append(it.sub)
    if it.kind in ("LOWER", "NAME") and it.label:
        texts.append(it.label)
    for txt in texts:
        for variant in speech.item_variants(txt):
            hit = speech.locate(variant, flat)
            if hit:
                i, j, _ = hit
                return seq[max(0, i - j)][1]
    return None


def spoken_tokens(text: str, seq: list) -> list[float] | None:
    """Lúc đọc tới TỪNG từ (tách theo khoảng trắng, như hộp trích dẫn đếm) của
    `text`; từ ngoài đoạn khớp được nội suy theo vị trí. None = không khớp."""
    from . import speech
    if not seq:
        return None
    toks = text.split()
    first_norm: list[int] = []
    norm: list[str] = []
    for t in toks:
        first_norm.append(len(norm))
        norm += speech.norm_words(t)
    hit = speech.locate(norm, [w for w, _, _ in seq])
    if not hit:
        return None
    i, j, _ = hit
    out, prev = [], -1.0
    for nq in first_norm:
        k = max(0, min(len(seq) - 1, i + (nq - j)))
        t = max(prev, seq[k][1])
        out.append(t)
        prev = t
    return out


LEAD = 0.12          # (0.6.2) giữ cho mã cũ / test; 0.6.3 dùng SHOW_BEFORE + thời gian hiện
SHOW_BEFORE = 0.10   # 0.6.3: chữ đã HIỆN RÕ (hết mờ dần) trước khi giọng nói tới 0,1 s
TYPE_LEAD = 0.08     # trích dẫn đánh máy: mỗi chữ hiện trước tiếng của nó 0,08 s
MIN_VISIBLE = 1.2    # khớp giọng làm chữ hiện muộn — vẫn phải đủ lâu để đọc
REPORT_NAME = "khop-giong-doc.csv"


class WordMap(dict):
    """{số cảnh: [(từ, bắt đầu, kết thúc)]} + nguồn mốc của từng cảnh
    (`sources[n] = ("exact"|"silence"|"plain", bộ máy)`)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.sources: dict[int, tuple[str, str]] = {}


@dataclass
class TimingRow:
    """Một dòng của báo cáo khớp giọng đọc."""
    scene: int
    kind: str
    text: str
    spoken: float | None      # giây trong cảnh lúc giọng nói tới (None = không thấy)
    shown: float              # giây trong cảnh lúc chữ bắt đầu hiện
    how: str                  # nguồn / lý do
    fade: float = FADE_IN     # thời gian từ lúc bắt đầu hiện tới lúc hiện rõ

    @property
    def ahead(self) -> float | None:
        """Chữ đã hiện rõ trước tiếng bao nhiêu giây (âm = hiện rõ sau tiếng)."""
        if self.spoken is None:
            return None
        return round(self.spoken - (self.shown + self.fade), 3)


def _vis(kind: str) -> float:
    """Từ lúc bắt đầu hiện tới lúc hiện rõ, theo kiểu chuyển động của loại."""
    m = mo.get(MOTION_OF.get(kind, "fade"))
    return m.ain or m.din


def char_times(text: str, tok_times: list[float] | None, start: float, cps: float,
               avail: float) -> list[float]:
    """Lúc ký tự thứ 1..n hiện. Có `tok_times` (lúc đọc tới từng từ) thì mỗi từ gõ
    trong khoảng từ lúc nó được đọc tới lúc từ sau được đọc (tối đa 0,1 s/ký tự);
    không có thì gõ đều `cps` ký tự/giây, co lại cho vừa `avail` giây."""
    n = len(text)
    if n == 0:
        return []
    if not tok_times:
        dur = min(n / cps, max(0.3, avail))
        return [start + dur * i / n for i in range(n)]
    toks = text.split(" ")
    out: list[float] = []
    for i, tok in enumerate(toks):
        t0 = tok_times[min(i, len(tok_times) - 1)] - TYPE_LEAD
        if i + 1 < len(toks):
            nxt = tok_times[min(i + 1, len(tok_times) - 1)] - TYPE_LEAD
        else:
            nxt = t0 + len(tok) / cps
        span = max(0.0, min(nxt - t0, len(tok) * 0.10))
        L = max(1, len(tok))
        for j in range(len(tok)):
            out.append(t0 + span * j / L)
        if i + 1 < len(toks):
            out.append(nxt)                 # dấu cách hiện cùng chữ đầu của từ sau
    prev = -1e9
    for i, t in enumerate(out):
        prev = max(prev, t)
        out[i] = prev
    return out[:n]


def type_marks(times: list[float]) -> list[tuple[float, int]]:
    """[(giây, số ký tự đã hiện)] — gộp các ký tự hiện sát nhau (< 1 khung hình)."""
    marks_: list[tuple[float, int]] = []
    for c, t in enumerate(times, start=1):
        if marks_ and t - marks_[-1][0] < MIN_TYPE_STEP:
            marks_[-1] = (marks_[-1][0], c)
        else:
            marks_.append((t, c))
    if len(marks_) > MAX_TYPE_FRAMES:
        step = len(marks_) / MAX_TYPE_FRAMES
        keep = [marks_[int(i * step)] for i in range(MAX_TYPE_FRAMES - 1)]
        marks_ = [(t, c) for (t, _), (_, c) in zip(keep, keep[1:] + [marks_[-1]])]
        marks_[-1] = (marks_[-1][0], len(times))
    return marks_


#: 0.7.3: danh sách hiện quanh lúc từng dòng được nhắc rồi tự ẩn (thay vì ở lại tới cảnh `until`)
LIST_HOLD = 10.0     # giây hiện sau mỗi lần một dòng được nhắc
LIST_JOIN = 4.0      # hai lần nhắc cách nhau ít hơn chừng này (sau khi ẩn) thì hiện liền


def list_groups(lists: dict[str, list[OverlayItem]], order: list[str], nums: list[int]
                ) -> list[list[OverlayItem]]:
    """Tách các danh sách TRÙNG TÊN: một dòng nằm sau cảnh cuối của danh sách trước
    (cảnh `until` hoặc dòng cuối) là danh sách mới. Trước 0.7.3 hai danh sách cùng nhãn
    (vd. 'Tres lugares del texto' ở cảnh 14 và 377) bị gộp làm một và hiện liền 39 phút."""
    pos = {n: i for i, n in enumerate(nums)}
    out: list[list[OverlayItem]] = []
    for key in order:
        cur: list[OverlayItem] = []
        end = -1
        for it in sorted(lists[key], key=lambda x: (pos.get(x.scene, 0), x.row)):
            p = pos.get(it.scene, 0)
            if cur and p > end:
                out.append(cur)
                cur, end = [], -1
            cur.append(it)
            end = max(end, pos.get(it.until, p) if it.until else p)
        if cur:
            out.append(cur)
    return out


def list_windows(events: list[float], t_end: float, hold: float | None) -> list[tuple[float, float]]:
    """Khoảng hiện của một danh sách: mỗi lần nhắc hiện `hold` giây, các lần gần nhau nối
    liền. `hold` None = như trước 0.7.3 (hiện liền từ lần nhắc đầu tới cảnh `until`)."""
    events = sorted(events)
    if hold is None or not events:
        return [(events[0], t_end)] if events else []
    wins: list[list[float]] = []
    for e in events:
        end = min(t_end, max(e + hold, e + MIN_SHOW))
        if wins and e <= wins[-1][1] + LIST_JOIN:
            wins[-1][1] = max(wins[-1][1], end)
        else:
            wins.append([e, end])
    if t_end - wins[-1][1] < LIST_JOIN:
        wins[-1][1] = t_end
    return [(a, b) for a, b in wins if b - a >= MIN_SHOW]


def schedule(items: list[OverlayItem], plan: list[ScenePlan], st: OverlayStyle,
             log: LogFn = print, words: dict | None = None,
             report: list | None = None, warn_overlap: bool = True,
             list_hold: float | None = None) -> list[Placement]:
    """Đổi các dòng overlay thành danh sách ảnh + thời gian, theo `plan`
    (trục nội dung). Mục có cảnh không nằm trong plan bị bỏ qua.

    `words` = {số cảnh: [(từ, giây bắt đầu, giây kết thúc)]} tính từ đầu file
    giọng đọc của cảnh. Có thì chữ hiện đúng lúc giọng đọc nói tới nó (đã hiện
    rõ trước tiếng SHOW_BEFORE giây), trích dẫn đánh máy từng ký tự theo giọng;
    không khớp được thì như cũ (đầu cảnh + DELAY). `report` (list) nhận một
    TimingRow mỗi mục. 0.6.4: mỗi phần của đồ họa là một Placement riêng có
    kiểu chuyển động (`motion`)."""
    by_num = {p.number: p for p in plan}
    nums = [p.number for p in plan]
    pos = {p.number: i for i, p in enumerate(plan)}
    out: list[Placement] = []
    synced = [0, 0, 0]                    # [khớp được, có lời thoại để khớp, theo mốc chính xác]
    sources = getattr(words, "sources", {}) if words else {}

    def source_at(t: float) -> tuple[str, str]:
        for q in plan:
            if q.start - 1e-6 <= t < q.end + 1e-6:
                return sources.get(q.number, ("", ""))
        return ("", "")

    def note(it: OverlayItem, ts: float | None, t0: float, how: str, vis: float) -> None:
        if report is None:
            return
        p0 = by_num[it.scene]
        report.append(TimingRow(it.scene, it.kind, it.text or it.sub or it.label,
                                None if ts is None else round(ts - p0.start, 3),
                                round(t0 - p0.start, 3), how, round(vis, 3)))

    def window(it: OverlayItem, first_delay: float = DELAY) -> tuple[float, float, float | None] | None:
        p = by_num.get(it.scene)
        if not p:
            return None
        last = by_num.get(it.until) if it.until else p
        if last is None:
            last = p
        t1 = last.end - TAIL
        ts = None
        how = "Đặt tay (cột start)" if it.start is not None else "Không có lời thoại / mốc → đầu cảnh"
        if it.start is None and words:
            seq = _seq(it, plan, pos, words)
            if seq:
                synced[1] += 1
                ts = spoken_start(it, seq)
                if ts is not None:
                    synced[0] += 1
                    src, engine = source_at(ts)
                    if src == "exact":
                        synced[2] += 1
                    from .speech import SOURCE_LABELS
                    how = SOURCE_LABELS.get(src, "Ước lượng") + (f" ({engine})" if engine else "")
                else:
                    how = "Không thấy chữ này trong lời đọc → đầu cảnh"
        vis = _vis(it.kind)
        if ts is not None:
            t0 = max(p.start, ts - vis - SHOW_BEFORE)
        else:
            delay = it.start if it.start is not None else min(first_delay, p.slot_duration * 0.2)
            t0 = p.start + max(0.0, delay)
        if it.dur is not None:
            # có 'until' thì dur chỉ được rút ngắn; không có thì dur quyết định
            t1 = min(t1, t0 + it.dur) if it.until else t0 + it.dur
        if t1 - t0 < (MIN_VISIBLE if ts is not None else MIN_SHOW):
            t1 = t0 + (MIN_VISIBLE if ts is not None else MIN_SHOW)
        note(it, ts, t0, how, vis)
        return t0, t1, ts

    def chain(it, frames: list[tuple[float, Frame]], t1: float, group: str, fade_out: float):
        """Ảnh nối liền nhau trên lớp 'text' (đánh máy, vạch chạy)."""
        frames = [f for f in frames if f[0] < t1 - 0.02]
        for i, (at, fr) in enumerate(frames):
            end = frames[i + 1][0] if i + 1 < len(frames) else t1
            if end - at < 0.004:
                continue
            last = i == len(frames) - 1
            out.append(Placement(fr, at, max(0.004, end - at), "text", 0.0,
                                 fade_out if last else 0.0, it.scene, motion="none", group=group))

    def typed(it: OverlayItem, t0: float, t1: float, tok_times):
        p = by_num[it.scene]
        base = TYPED[it.kind]
        mname = MOTION_OF[it.kind]
        m = mo.get(mname)
        text = place_text_of(it)
        n = len(text)
        has_ref = it.kind in ("QUOTE", "NOTE") and bool(it.sub)
        if tok_times:
            box = max(p.start, min(t0, tok_times[0] - TYPE_LEAD - m.din))
            times = char_times(text, tok_times, box + m.din, TYPE_CPS, t1 - box)
        else:
            box = t0
            start = t0 + min(m.din, (t1 - t0) * 0.25)
            cps = PLACE_CPS if it.kind == "PLACE" else TYPE_CPS
            times = char_times(text, None, start, cps, (t1 - start) * (0.55 if has_ref else 0.75))
        done = times[-1] if times else box
        t1 = max(t1, done + 0.3)              # câu đã gõ xong vẫn đứng lại một chút
        out.append(_new(Frame(it, part=base), box, t1, "main", mname, it.scene))
        tm = type_marks(times)
        frames: list[tuple[float, Frame]] = []
        if tm and tm[0][0] - (box + m.din * 0.6) > 0.12:   # con trỏ chờ trong hộp trống
            frames.append((box + m.din * 0.6, Frame(it, part="text", chars=0, caret=True)))
        for at, c in tm:
            frames.append((at, Frame(it, part="text", chars=None if c >= n else c, caret=c < n)))
        if frames and frames[-1][1].chars is not None:
            frames.append((done + 0.05, Frame(it, part="text")))
        chain(it, frames, t1, f"{it.row}:{it.kind}:text", m.dout)
        if has_ref and t1 - done > 0.35:
            out.append(_new(Frame(it, part="ref"), done + 0.05, t1, "text", "rise", it.scene, stacked=True))

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
        first_delay = {"STAMP": 0.6, "CINEMA": 0.0}.get(it.kind, DELAY)
        win = window(it, first_delay)
        if not win:
            continue
        t0, t1, _ts = win
        layer = LAYER_OF.get(it.kind, "main")
        mname = MOTION_OF.get(it.kind, "fade")
        if it.kind in TYPED and (st.typewriter or it.kind == "PLACE"):
            tok_times = None
            body = place_text_of(it)
            if (it.kind != "PLACE" and words and it.start is None and len(body.split()) > 1):
                tok_times = spoken_tokens(body, _seq(it, plan, pos, words))
            typed(it, t0, t1, tok_times)
        elif it.kind == "KEYWORD":
            out.append(_new(Frame(it, part="word"), t0, t1, layer, mname, it.scene))
            w0 = t0 + min(0.45, (t1 - t0) * 0.3)
            frames = [(w0 + WIPE_DUR * i / WIPE_STEPS,
                       Frame(it, part="line", progress=None if i == WIPE_STEPS else mo.ease_out(i / WIPE_STEPS)))
                      for i in range(1, WIPE_STEPS + 1)]
            chain(it, frames, t1, f"{it.row}:KEYWORD:line", mo.get(mname).dout)
        elif it.kind == "TIMELINE":
            out.append(_new(Frame(it, part="bg"), t0, t1, layer, "fade", it.scene))
            w0 = t0 + min(0.30, (t1 - t0) * 0.2)
            dur = min(TL_DUR, max(0.4, (t1 - w0) * 0.5))
            frames = [(w0 + dur * i / TL_STEPS,
                       Frame(it, part="line", progress=None if i == TL_STEPS else mo.ease_out(i / TL_STEPS)))
                      for i in range(0, TL_STEPS + 1)]
            chain(it, frames, t1, f"{it.row}:TIMELINE:line", mo.get("fade").dout)
        elif it.kind == "VS":
            out.append(_new(Frame(it, part="left"), t0, t1, layer, "slide_left", it.scene))
            out.append(_new(Frame(it, part="right"), min(t1 - 0.3, t0 + 0.12), t1, layer, "slide_right",
                            it.scene, stacked=True))
            out.append(_new(Frame(it, part="mid"), min(t1 - 0.3, t0 + 0.30), t1, "text", "pop", it.scene,
                            stacked=True))
        elif it.kind == "CINEMA":
            out.append(_new(Frame(it, part="top"), t0, t1, layer, "bar_top", it.scene))
            out.append(_new(Frame(it, part="bottom"), t0, t1, layer, "bar_bottom", it.scene, stacked=True))
        else:
            fr = Frame(it, part="" if it.kind != "QUOTE" else "")
            out.append(_new(fr, t0, t1, layer, mname, it.scene))

    # danh sách: nhãn hiện trước, mỗi mục trượt vào đúng lúc được nhắc; 0.7.3: danh sách trùng
    # tên được tách riêng, và (list_hold) tự ẩn khi lời đọc chuyển ý, hiện lại khi nhắc dòng sau
    for group in list_groups(lists, order, nums):
        label = next((g.label for g in group if g.label), "")
        entries = [g for g in group if g.text]
        end_it = max(group, key=lambda g: (g.until or g.scene))
        last_scene = end_it.until or end_it.scene
        first = group[0]
        n_rep = len(report) if report is not None else 0
        t_first, _, _ = window(first)
        if report is not None and first.text:
            del report[n_rep:]            # mục đầu có chữ sẽ được ghi ở vòng dưới
        p_last = by_num.get(last_scene) or by_num[group[-1].scene]
        t_end = p_last.end - TAIL
        if any(g.dur for g in group):
            t_end = min(t_end, max(t_first + g.dur for g in group if g.dur))
        t_end = max(t_end, t_first + MIN_SHOW)
        row_t = []
        for g in entries:
            ts, _, _ = window(g)
            row_t.append(min(max(ts, t_first + (0.15 if label else 0.0)), t_end - MIN_SHOW))
        for ws, we in list_windows([t_first] + row_t, t_end, list_hold):
            if label:
                out.append(_new(Frame(first, part="label", list_label=label), ws, we, "list",
                                "slide_left", first.scene))
            k = 0
            for i, (g, ts) in enumerate(zip(entries, row_t), start=1):
                if ts >= we - 0.04:
                    continue
                if ts < ws:                       # dòng đã nhắc trước: hiện lại cùng danh sách
                    k += 1
                    ts = min(ws + (0.15 if label else 0.0) + 0.08 * (k - 1), we - MIN_SHOW)
                out.append(_new(Frame(g, part="row", index=i, list_label=label), ts, we, "list",
                                "slide_left", g.scene, stacked=True))

    if words is not None and synced[1]:
        log(f"[BUILD] Đồ họa chữ khớp giọng đọc: {synced[0]}/{synced[1]} mục hiện đúng lúc "
            "giọng nói tới" + ("" if synced[0] == synced[1] else
                               " — mục còn lại không tìm thấy chữ trong lời thoại, hiện ở đầu cảnh"))
        if synced[0]:
            if synced[2] == synced[0]:
                log(f"[BUILD] Đồ họa chữ: cả {synced[0]} mục theo MỐC CHÍNH XÁC của từng từ trong file giọng")
            elif synced[2]:
                log(f"[WARN] Đồ họa chữ: {synced[2]} mục theo mốc chính xác, {synced[0] - synced[2]} mục "
                    "chỉ ƯỚC LƯỢNG (file giọng của các cảnh đó không có mốc từng từ)")
            else:
                log("[WARN] Đồ họa chữ: file giọng không có mốc từng từ nên thời điểm chỉ là ƯỚC LƯỢNG "
                    "(có thể lệch 0,3–1 s). Muốn khớp chính xác: tạo giọng bằng TTS Clone Studio 3.3+ "
                    "và bật '⏱ Ghi mốc thời gian từng từ vào MP3'")
    # 0.7.3: khi bật tránh che nhau, avoid_overlap() xử lý và báo — không cảnh báo hai lần
    _assign_tracks(out, log if warn_overlap else (lambda m: None))
    out.sort(key=lambda p: (LAYERS.index(p.layer), p.track, p.start))
    return out


def place_text_of(it: OverlayItem) -> str:
    """Chữ đánh máy (trơn, đúng thứ tự ký tự của bố cục)."""
    from .overlay_draw import place_text
    return place_text(it) if it.kind == "PLACE" else plain(it.text)


def us(t: float) -> int:
    """Giây → micro giây nguyên, đúng cách CapCut lưu thời gian."""
    return int(round(float(t) * 1_000_000))


def us_span(start: float, length: float) -> tuple[int, int]:
    """(bắt đầu, kết thúc) theo micro giây, làm tròn TỪNG ĐẦU MÚT.

    Không được làm tròn riêng độ dài: round(a) + round(b) có thể lớn hơn
    round(a + b) 1 µs, và hai đoạn nối liền (các bước đánh máy của trích dẫn)
    chồng nhau 1 µs → pycapcut báo SegmentOverlap (lỗi 0.6.0 bản đầu)."""
    return us(start), us(float(start) + float(length))


def _assign_tracks(pls: list[Placement], log: LogFn) -> None:
    """Hai ảnh cùng lớp chồng giờ nhau → đặt sang track thứ hai (và báo nếu không
    phải các phần cố ý chồng của cùng một đồ họa).

    So sánh trên micro giây nguyên (như CapCut) và chặt: kết thúc ≤ bắt đầu."""
    by_layer: dict[str, list[Placement]] = {}
    for p in pls:
        by_layer.setdefault(p.layer, []).append(p)
    for layer, group in by_layer.items():
        ends: list[int] = []
        warned: set[int] = set()
        for p in sorted(group, key=lambda x: (us(x.start), x.stacked, x.scene)):
            s0, e0 = us_span(p.start, p.length)
            for i, e in enumerate(ends):
                if e <= s0:
                    p.track = i
                    ends[i] = e0
                    break
            else:
                p.track = len(ends)
                ends.append(e0)
            if p.track > 0 and not p.stacked and p.scene not in warned:
                warned.add(p.scene)
                log(f"[WARN] Đồ họa chữ: cảnh {p.scene} có hai đồ họa '{layer}' cùng lúc "
                    "— đặt chồng lên nhau, nên xem lại")


# --------------------------------------------------------------------------- #
# ghi PNG
# --------------------------------------------------------------------------- #
def _frame_key(fr: Frame, w: int, h: int, st: OverlayStyle) -> str:
    raw = "|".join([fr.key(), f"{w}x{h}", st.key()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def write_pngs(pls: list[Placement], out_dir: Path, w: int, h: int, st: OverlayStyle,
               log: LogFn = print, cancel=None) -> int:
    """Vẽ mọi ảnh cần thiết vào `out_dir` (xoá ảnh cũ của tool trước). Ảnh trùng
    nội dung dùng chung một file. Ghi luôn vùng có hình (`Placement.bbox`) để
    chuyển động phóng quanh tâm đồ họa và render chỉ phủ phần cần thiết.
    Trả về số file đã vẽ."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("ov_*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    cache: dict[str, tuple[Path, tuple[int, int, int, int] | None]] = {}
    for p in pls:
        if p.clip is not None:          # đồ họa Remotion: đã có clip, không vẽ PNG
            continue
        if cancel and cancel():
            from .media import Cancelled
            raise Cancelled()
        key = _frame_key(p.frame, w, h, st)
        got = cache.get(key)
        if got is None:
            path = out_dir / f"ov_{p.scene:04d}_{p.frame.item.kind.lower()}_{key}.png"
            img = render_frame(p.frame, w, h, st)
            bbox = img.getchannel("A").getbbox()
            img.save(path, optimize=False, compress_level=3)
            got = cache[key] = (path, bbox)
        p.png, p.bbox = got
    return len(cache)


# --------------------------------------------------------------------------- #
# 0.7.3: tránh hai đồ họa che nhau
# --------------------------------------------------------------------------- #
#: mức alpha coi là "phần đặc" (chữ, hộp) — bỏ qua nền tối mờ dần (≤ 0,75 = 191)
SOLID_ALPHA = 200
#: hai đồ họa chỉ tính là che nhau khi chồng giờ hơn chừng này
OVERLAP_MIN = 0.12
#: đồ họa trước tắt mờ dần trong lúc đồ họa sau hiện lên
HANDOFF = 0.15
READ_MIN, READ_MAX, READ_PER_WORD = 1.5, 3.5, 0.35


def _solid_box(fr: Frame, st: OverlayStyle) -> tuple[int, int, int, int] | None:
    """Vùng có chữ / hộp (đã bỏ nền mờ) của cả đồ họa, trên khung 1920×1080."""
    a = render_frame(fr, 1920, 1080, st).getchannel("A")
    return a.point(lambda v: 255 if v > SOLID_ALPHA else 0).getbbox()


def _read_time(it: OverlayItem) -> float:
    n = len(plain(" ".join(x for x in (it.text, it.sub, it.label) if x)).split())
    return max(READ_MIN, min(READ_MAX, READ_PER_WORD * n))


def _cut(parts: list[Placement], at: float) -> list[Placement]:
    """Đồ họa tắt (mờ dần) ở `at`: bỏ phần bắt đầu sau đó, rút ngắn phần đang hiện."""
    keep = []
    for p in parts:
        if p.start >= at - 0.04:
            continue
        if p.end > at:
            p.length = at - p.start
            m = mo.get(p.motion)
            p.fade_out = (m.dout if p.motion != "none" and m.dout else
                          min(FADE_OUT, max(0.04, p.length * 0.6)))
        keep.append(p)
    return keep


def _delay(parts: list[Placement], to: float) -> list[Placement]:
    """Đồ họa hiện muộn lại cho tới `to`, vẫn tắt đúng giờ cũ: mọi mốc bên trong (chữ đánh
    máy, vạch chạy, nhãn phụ) được nén lại cho vừa — câu trích dẫn vẫn gõ xong trọn."""
    t0 = min(p.start for p in parts)
    end = max(p.end for p in parts)
    if to <= t0 or end - to < 0.08:
        return parts if to <= t0 else []
    k = (end - to) / (end - t0)
    for p in parts:
        a, b = p.start, p.end
        p.start = to + (a - t0) * k
        p.length = max(0.004, (b - a) * k)
    return parts


def avoid_overlap(pls: list[Placement], st: OverlayStyle, log: LogFn = print) -> list[Placement]:
    """Hai đồ họa chồng cả vùng hình lẫn thời gian → đồ họa đến trước nhường chỗ.

    Nguyên nhân che nhau: mỗi đồ họa ở lại tới hết cảnh (hoặc tới cảnh `until`), và
    nhiều loại có chỗ cố định trùng nhau (TERM bên phải đè hộp giữa của QUOTE /
    TITLE / NOTE / VS; dải CHAPTER, TIMELINE đè nhãn dưới LOWER / NAME / SOURCE…).
    Cách nhường: đồ họa trước đã hiện đủ lâu để đọc (`_read_time`) thì tắt khi đồ
    họa sau hiện; chưa đủ thì đồ họa sau đợi tới lúc đó (vẫn tắt đúng giờ của nó);
    đợi không nổi thì đồ họa sau thắng và ghi cảnh báo. Không có chồng → không đổi gì."""
    groups: dict[object, list[Placement]] = {}
    # danh sách: mỗi khoảng hiện liền của một nhãn là một đồ họa (nhãn + các dòng)
    clusters: dict[str, list[list]] = {}
    for p in sorted((q for q in pls if q.frame.item.kind == "LIST"), key=lambda q: q.start):
        lab = (p.frame.list_label or p.frame.item.label).strip().upper() or "_"
        cl = clusters.setdefault(lab, [])
        if cl and p.start < cl[-1][0] + 0.05:
            cl[-1][0] = max(cl[-1][0], p.end)
        else:
            cl.append([p.end])
        groups.setdefault(("LIST", lab, len(cl)), []).append(p)
    for p in pls:
        if p.frame.item.kind != "LIST":
            groups.setdefault(id(p.frame.item), []).append(p)
    region: dict[object, tuple | None] = {}
    first: dict[object, OverlayItem] = {}
    for key, parts in groups.items():
        it = min(parts, key=lambda q: q.start).frame.item
        first[key] = it
        if it.kind == "CINEMA":
            region[key] = None
        elif it.kind == "LIST":
            texts = tuple(dict.fromkeys(q.frame.item.text for q in parts if q.frame.item.text))
            region[key] = _solid_box(Frame(it, list_items=texts, list_label=it.label), st)
        else:
            region[key] = _solid_box(Frame(it), st)

    def span(k):
        g = groups[k]
        return min(q.start for q in g), max(q.end for q in g)

    def hit(a, b):
        ra, rb = region[a], region[b]
        return bool(ra and rb and ra[0] < rb[2] and rb[0] < ra[2] and ra[1] < rb[3] and rb[1] < ra[3])

    fixed: list[str] = []
    stuck: list[str] = []
    for _ in range(4):                    # vài vòng: một lần nhường có thể đẩy sang chỗ khác
        changed = False
        keys = sorted((k for k in groups if groups[k]), key=lambda k: span(k)[0])
        for j, b in enumerate(keys):
            for a in keys[:j]:
                if not groups[a] or not groups[b]:
                    continue
                a0, a1 = span(a)
                b0, b1 = span(b)
                # đã nhường (chỉ còn đoạn mờ dần lúc giao nhau) hoặc không chung vùng → bỏ qua
                if a1 - b0 <= max(OVERLAP_MIN, HANDOFF) + 0.01 or not hit(a, b):
                    continue
                A, B = first[a], first[b]
                need = a0 + _read_time(A)
                label = f"cảnh {B.scene}: {A.kind} nhường {B.kind}"
                if b0 >= need - 1e-6:
                    groups[a] = _cut(groups[a], b0 + HANDOFF)
                elif need + MIN_VISIBLE <= b1:
                    groups[b] = _delay(groups[b], need)
                    groups[a] = _cut(groups[a], need + HANDOFF)
                    label += f" (hiện muộn {need - b0:.1f} s)"
                elif b1 - a0 >= 2 * MIN_SHOW + HANDOFF:
                    mid = a0 + (b1 - a0) / 2          # không đủ chỗ cho cả hai: chia đôi thời gian
                    if mid > b0:
                        groups[b] = _delay(groups[b], mid)
                    groups[a] = _cut(groups[a], max(mid, b0) + HANDOFF)
                    label += " (chia đôi thời gian)"
                else:
                    groups[a] = []                     # quá ngắn để hiện cả hai: bỏ đồ họa trước
                    stuck.append(f"cảnh {A.scene}: bỏ {A.kind} vì {B.kind} cùng chỗ, cảnh quá ngắn")
                    label = ""
                if label:
                    fixed.append(label)
                changed = True
        if not changed:
            break
    out = [p for g in groups.values() for p in g]
    if fixed:
        log(f"[BUILD] Đồ họa chữ: {len(fixed)} chỗ hai đồ họa che nhau → đồ họa trước tắt khi đồ họa "
            "sau hiện (" + "; ".join(fixed[:6]) + (" …" if len(fixed) > 6 else "") + ")")
    for x in stuck[:8]:
        log(f"[WARN] Đồ họa chữ: {x} — nên dời một đồ họa sang cảnh khác trong file overlay")
    _assign_tracks(out, lambda m: None)
    out.sort(key=lambda p: (LAYERS.index(p.layer), p.track, p.start))
    return out


def remotion_kinds(s) -> tuple[str, ...]:
    """Loại đồ họa vẽ bằng Remotion (0.7.0) — rỗng khi tắt."""
    if not getattr(s, "enable_remotion", False):
        return ()
    from .remotion import KINDS
    return KINDS


def use_remotion(s, pls: list[Placement], st: OverlayStyle, size: tuple[int, int], fps: int,
                 log: LogFn = print, cancel=None, base: Path | None = None) -> list[Placement]:
    """0.7.0: mỗi đồ họa loại Remotion (mọi phần + chuỗi ảnh của nó) gộp thành MỘT
    clip chuyển động cùng giờ bắt đầu / kết thúc. Clip nào không vẽ được thì giữ
    nguyên các ảnh Pillow của mục đó — không bao giờ làm hỏng việc dựng."""
    kinds = remotion_kinds(s)
    if not kinds:
        return pls
    from . import remotion as rm
    groups: dict[int, list[Placement]] = {}
    for p in pls:
        if p.frame.item.kind in kinds:
            groups.setdefault(id(p.frame.item), []).append(p)
    if not groups:
        return pls
    cache = Path(s.input_dir) / "_capcut_draft_studio" / rm.CACHE_DIR
    src_hash = rm.source_hash()
    jobs: dict[int, rm.Job] = {}
    spans: dict[int, tuple[float, float]] = {}
    for key, parts in groups.items():
        it = parts[0].frame.item
        t0 = min(p.start for p in parts)
        t1 = max(p.end for p in parts)
        props = rm.make_props(it, st, size, fps, t1 - t0)
        jobs[key] = rm.Job(it.kind, it.scene, props, cache / rm.clip_name(it.kind, props, src_hash))
        spans[key] = (t0, t1)
    ok = rm.render_jobs(list(jobs.values()), base, log, cancel)
    out: list[Placement] = []
    swapped: set[int] = set()
    for p in pls:
        key = id(p.frame.item)
        if key not in jobs:
            out.append(p)
            continue
        if not ok.get(jobs[key].out):
            out.append(p)               # quay về bản Pillow
            continue
        if p.frame.part in rm.STATIC_PARTS.get(p.frame.item.kind, ()):
            out.append(p)               # nền tĩnh: vẫn là ảnh PNG, nằm dưới clip
            continue
        if key in swapped:
            continue
        swapped.add(key)
        t0, t1 = spans[key]
        it = p.frame.item
        clip = jobs[key].out
        out.append(Placement(Frame(it), t0, t1 - t0, LAYER_OF.get(it.kind, "main"), 0.0, 0.0,
                             it.scene, motion="none", clip=clip,
                             clip_box=rm.crop_clip(clip, size[0], size[1], log),
                             # có nền tĩnh cùng giờ → clip xếp SAU nó (nằm trên)
                             stacked=bool(rm.STATIC_PARTS.get(it.kind))))
    if swapped:
        log(f"[BUILD] Đồ họa chữ: {len(swapped)} mục ({', '.join(kinds)}) dùng clip Remotion")
        try:
            rm.prune_cache(cache, {j.out.resolve() for j in jobs.values()})
        except OSError:
            pass
    _assign_tracks(out, lambda m: None)     # chồng giờ đã được báo lúc lập lịch
    out.sort(key=lambda p: (LAYERS.index(p.layer), p.track, p.start))
    return out


def prepare(s, plan: list[ScenePlan], out_dir: Path, log: LogFn = print,
            cancel=None, size: tuple[int, int] | None = None,
            report_dir: Path | None = None, fps: int | None = None) -> list[Placement]:
    """Đọc file overlay của project, lập lịch theo `plan` và vẽ PNG.
    Không bật / không có file → []. Lỗi trong file → BuildError.

    Khi khớp theo giọng đọc, ghi báo cáo REPORT_NAME vào `report_dir`
    (mặc định thư mục cha của `out_dir`)."""
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
    words = voice_words(s, plan, items, log) if getattr(s, "overlay_sync", True) else None
    rows: list[TimingRow] = []
    avoid = bool(getattr(s, "overlay_avoid_overlap", True))
    pls = schedule(items, plan, st, log, words=words, report=rows, warn_overlap=not avoid,
                   list_hold=LIST_HOLD if avoid else None)
    if avoid:
        pls = avoid_overlap(pls, st, log)
    if words is not None and rows:
        write_report(rows, Path(report_dir or Path(out_dir).parent) / REPORT_NAME, log)
    w, h = size or (int(s.width), int(s.height))
    if remotion_kinds(s):
        if fps is None:
            from .render import target_fps
            fps = target_fps(s)
        pls = use_remotion(s, pls, st, (w, h), int(fps), log, cancel)
    n = write_pngs(pls, out_dir, w, h, st, log, cancel)
    log(f"[BUILD] Đồ họa chữ: {len(items)} mục từ {path.name} → {n} ảnh, {len(pls)} đoạn")
    return pls


def voice_words(s, plan: list[ScenePlan], items: list[OverlayItem], log: LogFn = print) -> WordMap:
    """{số cảnh: thời gian từng từ} cho các cảnh có đồ họa (tới cảnh 'until').

    0.6.3: mốc THẬT của từng từ đọc trong file giọng (TTS Clone Studio 3.3+ ghi
    vào MP3) được ưu tiên; cảnh không có mốc thì ước lượng như 0.6.2 từ lời
    thoại (manifest / Excel / Texts/, kể cả khi phụ đề tắt) + quãng lặng."""
    from dataclasses import replace
    from . import speech
    from .subtitles import load_scene_texts
    pos = {p.number: i for i, p in enumerate(plan)}
    need: set[int] = set()
    for it in items:
        if it.scene in pos:
            i1 = pos.get(it.until, pos[it.scene]) if it.until else pos[it.scene]
            need.update(p.number for p in plan[pos[it.scene]:i1 + 1])
    out = WordMap()
    if not need:
        return out
    src = s if str(getattr(s, "subtitle_source", "auto")) != "off" else \
        replace(s, subtitle_source="auto")
    try:
        texts = load_scene_texts(src, sorted(need), lambda m: None)
    except Exception as e:
        log(f"[WARN] Đồ họa chữ: không đọc được lời thoại để khớp giọng ({e})")
        texts = {}
    try:
        from .render import find_tool
        ffmpeg = find_tool("ffmpeg")
    except Exception:
        ffmpeg = None
    counts = {"exact": 0, "silence": 0, "plain": 0}
    engines: set[str] = set()
    for p in plan:
        if p.number not in need:
            continue
        words, how, engine = speech.scene_timing(texts.get(p.number, ""), p.audio_path,
                                                 p.audio_duration, ffmpeg)
        if words:
            out[p.number] = words
            out.sources[p.number] = (how, engine)
            counts[how] = counts.get(how, 0) + 1
            if engine:
                engines.add(engine)
    if not out:
        log("[WARN] Đồ họa chữ: không có lời thoại (Texts/, Excel, manifest) và file giọng không có mốc "
            "từng từ nên chữ hiện ở đầu cảnh, không khớp theo giọng đọc")
        return out
    parts = []
    if counts["exact"]:
        parts.append(f"{counts['exact']} cảnh theo mốc chính xác trong file giọng"
                     + (f" ({', '.join(sorted(engines))})" if engines else ""))
    if counts["silence"]:
        parts.append(f"{counts['silence']} cảnh ước lượng (đo quãng lặng bằng ffmpeg)")
    if counts["plain"]:
        parts.append(f"{counts['plain']} cảnh ước lượng theo độ dài chữ (không có ffmpeg)")
    log("[BUILD] Đồ họa chữ: khớp theo giọng đọc — " + "; ".join(parts))
    return out


def write_report(rows: list[TimingRow], path: Path, log: LogFn = print) -> Path | None:
    """Báo cáo khớp giọng (CSV UTF-8 có BOM — mở thẳng bằng Excel)."""
    import csv

    def sec(v):
        return "" if v is None else f"{v:.2f}".replace(".", ",")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Cảnh", "Loại", "Chữ trên hình", "Giọng nói tới (giây trong cảnh)",
                        "Chữ bắt đầu hiện (giây trong cảnh)", "Hiện rõ trước tiếng (giây)", "Cách khớp"])
            for r in sorted(rows, key=lambda r: (r.scene, r.shown)):
                w.writerow([r.scene, r.kind, r.text, sec(r.spoken), sec(r.shown), sec(r.ahead), r.how])
    except OSError as e:
        log(f"[WARN] Đồ họa chữ: không ghi được báo cáo khớp giọng ({e})")
        return None
    log(f"[BUILD] Đồ họa chữ: báo cáo khớp giọng từng mục → {path}")
    return path


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
    ["1", "CINEMA", "Judea · 1st century", "", "", "2", "", ""],
    ["1", "CHAPTER", "When the righteous are finally revealed", "1 Enoch 38", "", "", "", ""],
    ["2", "PLACE", "Qumran, Judean Desert", "Spring 1947", "", "", "", ""],
    ["3", "QUOTE", "They shall not be able to behold *the face of the holy*", "1 Enoch 38:4",
     "", "", "", ""],
    ["4", "STAMP", "His light. On their faces.", "", "", "", "", ""],
    ["5", "LIST", "One on the face", "", "Three marks", "9", "", ""],
    ["7", "LIST", "One on the forehead", "", "Three marks", "", "", ""],
    ["9", "LIST", "One where no one can see", "", "Three marks", "", "", ""],
    ["10", "TITLE", "The one who carries it does *not know* it is there", "Other people see it.",
     "", "", "", ""],
    ["12", "STAT", "~11", "copies found at Qumran", "", "", "", ""],
    ["14", "NAME", "Jean Starcky · 1964", "", "The Aramaic text", "", "", ""],
    ["15", "LOWER", "The kings and the powerful", "", "Will no longer be exalted", "", "", ""],
    ["16", "TERM", "Nephilim | נְפִילִים", "“the fallen ones”", "Hebrew", "", "", ""],
    ["18", "VS", "What the church taught", "What the scroll actually says", "Two readings", "", "", ""],
    ["20", "TIMELINE", "1446 BC | 1010 BC | *586 BC* | 70 AD", "", "The exile", "", "", ""],
    ["22", "KEYWORD", "*Betrayal*", "Thirty pieces of silver", "Chapter three", "", "", ""],
    ["23", "SOURCE", "Josephus, Antiquities of the Jews 18.3", "", "", "", "", ""],
    ["25", "NOTE", "I have seen the city of the dead, and *no one* returns from it unchanged.",
     "Letter of Aristeas", "", "", "", ""],
    ["27", "SUBSCRIBE", "Subscribe", "New study every week", "", "", "3", ""],
]

GUIDE_ROWS = [
    ["Cột", "Ý nghĩa"],
    ["scene", "Số cảnh (khớp số file Audio). 0007 hay 7 đều được."],
    ["type", "Loại đồ họa (tên tiếng Anh hoặc tiếng Việt không dấu đều được):"],
    *[[k, f"{v[0]} — {v[1]}"] for k, v in KINDS.items()],
    ["text", "Chữ chính. LIST: tên mục. STAT: con số. TERM: từ phiên âm | chữ gốc. VS: bên trái. "
             "TIMELINE: các mốc cách nhau bằng |. CINEMA, SUBSCRIBE: có thể để trống. "
             "*Chữ giữa hai dấu sao* được tô màu nhấn (QUOTE, TITLE, NOTE, KEYWORD, mốc TIMELINE)."],
    ["sub", "Dòng phụ: tham chiếu của QUOTE, nguồn của CHAPTER, dòng nghiêng của TITLE/KEYWORD, "
            "nhãn của STAT, năm của PLACE, nghĩa của TERM, bên phải của VS, người viết của NOTE, "
            "câu mời của SUBSCRIBE."],
    ["label", "Nhãn nhỏ in hoa: LOWER/NAME (dòng trên hộp), LIST (tên danh sách — các dòng LIST "
              "cùng label cộng dồn thành một danh sách), TERM (ngôn ngữ), VS/TIMELINE (tiêu đề), "
              "KEYWORD (dòng nhỏ phía trên), SOURCE (mặc định SOURCE)."],
    ["until", "Giữ tới hết cảnh số này (LIST, CINEMA, QUOTE dài…). Để trống = hết cảnh của dòng."],
    ["start", "Hiện sau bao nhiêu giây kể từ đầu cảnh (trống = tự khớp giọng đọc, không khớp "
              "được thì 0.35 giây)."],
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
