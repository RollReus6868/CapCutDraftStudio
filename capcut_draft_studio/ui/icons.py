"""Bộ icon lucide (https://lucide.dev, giấy phép ISC) vẽ bằng Pillow cho Tkinter.

Tk không đọc được SVG, nên file này mang theo dữ liệu nét vẽ gốc của từng icon
(lưới 24×24, nét 2px, đầu nét tròn) và tự rasterize: vẽ ở độ phân giải gấp 4
rồi thu nhỏ để nét mịn. Ảnh được cache theo (tên, cỡ, màu).
"""
from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw, ImageTk

# Mỗi icon là danh sách phần tử SVG: ("path", d) · ("circle", cx, cy, r)
# · ("rect", x, y, w, h, rx) · ("line", x1, y1, x2, y2) · ("poly", "x y x y…", đóng?)
LUCIDE: dict[str, list[tuple]] = {
    "layout-dashboard": [("rect", 3, 3, 7, 9, 1), ("rect", 14, 3, 7, 5, 1),
                         ("rect", 14, 12, 7, 9, 1), ("rect", 3, 16, 7, 5, 1)],
    "sliders-horizontal": [("line", 21, 4, 14, 4), ("line", 10, 4, 3, 4),
                           ("line", 21, 12, 12, 12), ("line", 8, 12, 3, 12),
                           ("line", 21, 20, 16, 20), ("line", 12, 20, 3, 20),
                           ("line", 14, 2, 14, 6), ("line", 8, 10, 8, 14),
                           ("line", 16, 18, 16, 22)],
    "clapperboard": [("path", "M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 "
                              "2.2.3 2.5 1.3Z"),
                     ("path", "m6.2 5.3 3.1 3.9"), ("path", "m12.4 3.4 3.1 4"),
                     ("path", "M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z")],
    "bookmark": [("path", "m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z")],
    "book-open": [("path", "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"),
                  ("path", "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z")],
    "refresh-cw": [("path", "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"),
                   ("path", "M21 3v5h-5"),
                   ("path", "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"),
                   ("path", "M8 16H3v5")],
    "sun": [("circle", 12, 12, 4), ("path", "M12 2v2"), ("path", "M12 20v2"),
            ("path", "m4.93 4.93 1.41 1.41"), ("path", "m17.66 17.66 1.41 1.41"),
            ("path", "M2 12h2"), ("path", "M20 12h2"), ("path", "m6.34 17.66-1.41 1.41"),
            ("path", "m19.07 4.93-1.41 1.41")],
    "moon": [("path", "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z")],
    "chevrons-left": [("path", "m11 17-5-5 5-5"), ("path", "m18 17-5-5 5-5")],
    "chevrons-right": [("path", "m6 17 5-5-5-5"), ("path", "m13 17 5-5-5-5")],
    "play": [("poly", "6 3 20 12 6 21 6 3", True)],
    "circle-check": [("circle", 12, 12, 10), ("path", "m9 12 2 2 4-4")],
    "check": [("path", "M20 6 9 17l-5-5")],
    "square": [("rect", 5, 5, 14, 14, 2)],
    "sparkles": [("path", "M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962"
                          "L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0"
                          "L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964"
                          "L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"),
                 ("path", "M20 3v4"), ("path", "M22 5h-4"), ("path", "M4 17v2"),
                 ("path", "M5 18H3")],
    "audio-lines": [("path", "M2 10v3"), ("path", "M6 6v11"), ("path", "M10 3v18"),
                    ("path", "M14 8v7"), ("path", "M18 5v13"), ("path", "M22 10v3")],
    "image": [("rect", 3, 3, 18, 18, 2), ("circle", 9, 9, 2),
              ("path", "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21")],
    "music": [("path", "M9 18V5l12-2v13"), ("circle", 6, 18, 3), ("circle", 18, 16, 3)],
    "film": [("rect", 3, 3, 18, 18, 2), ("path", "M7 3v18"), ("path", "M3 7.5h4"),
             ("path", "M3 12h18"), ("path", "M3 16.5h4"), ("path", "M17 3v18"),
             ("path", "M17 7.5h4"), ("path", "M17 16.5h4")],
    "clock": [("circle", 12, 12, 10), ("poly", "12 6 12 12 16 14", False)],
    "folder-open": [("path", "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6"
                             "a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9"
                             "a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2")],
    "list-checks": [("path", "m3 17 2 2 4-4"), ("path", "m3 7 2 2 4-4"), ("path", "M13 6h8"),
                    ("path", "M13 12h8"), ("path", "M13 18h8")],
    "terminal": [("poly", "4 17 10 11 4 5", False), ("line", 12, 19, 20, 19)],
    "palette": [("dot", 13.5, 6.5), ("dot", 17.5, 10.5), ("dot", 8.5, 7.5), ("dot", 6.5, 12.5),
                ("path", "M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 "
                         "0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 "
                         "0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 "
                         "17.461 2 12 2z")],
    "captions": [("rect", 3, 5, 18, 14, 2), ("path", "M7 15h4M15 15h2M7 11h2M13 11h4")],
    "wand": [("path", "m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 "
                      "0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"),
             ("path", "m14 7 3 3"), ("path", "M5 6v4"), ("path", "M19 14v4"),
             ("path", "M10 2v2"), ("path", "M7 8H3"), ("path", "M21 16h-4"),
             ("path", "M11 3H9")],
    "volume": [("path", "M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8"
                        "H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 "
                        "3.384A.705.705 0 0 0 11 19.298z"),
               ("path", "M16 9a5 5 0 0 1 0 6"), ("path", "M19.364 18.364a9 9 0 0 0 0-12.728")],
    "shield-check": [("path", "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13"
                              "V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0"
                              "C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"),
                     ("path", "m9 12 2 2 4-4")],
    "history": [("path", "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"),
                ("path", "M3 3v5h5"), ("path", "M12 7v5l4 2")],
    "list-video": [("path", "M12 12H3"), ("path", "M16 6H3"), ("path", "M12 18H3"),
                   ("path", "m16 12 5 3-5 3v-6Z")],
    "timer": [("line", 10, 2, 14, 2), ("line", 12, 14, 15, 11), ("circle", 12, 14, 8)],
    "filter": [("poly", "22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3", True)],
    "info": [("circle", 12, 12, 10), ("path", "M12 16v-4"), ("dot", 12, 8)],
    "x": [("path", "M18 6 6 18"), ("path", "m6 6 12 12")],
    "chevron-down": [("path", "m6 9 6 6 6-6")],
}

#: ký tự icon cũ (unicode) → tên icon lucide tương ứng
GLYPH = {
    "▦": "layout-dashboard", "⚙": "sliders-horizontal", "▶": "clapperboard",
    "★": "bookmark", "?": "book-open", "♪": "audio-lines", "▣": "image",
    "♫": "music", "✓": "film", "◐": "clock", "✎": "captions",
}

_NUM = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc(x1, y1, rx, ry, phi, fa, fs, x2, y2, steps=None):
    """Chuyển cung SVG (dạng điểm cuối) thành danh sách điểm."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = steps or max(6, int(abs(dt) / (math.pi / 24)))
    pts = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return pts


def _bezier(p0, p1, p2, p3, n=16):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0]
                    + t ** 3 * p3[0],
                    mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1]
                    + t ** 3 * p3[1]))
    return out


def parse_path(d: str) -> list[tuple[list, bool]]:
    """SVG path → [(điểm, đóng?)] — đủ cho bộ icon lucide."""
    toks = _TOK.findall(d)
    subs: list[tuple[list, bool]] = []
    pts: list = []
    i, cmd = 0, ""
    x = y = sx = sy = 0.0
    last_c = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flush(closed=False):
        nonlocal pts
        if len(pts) > 1 or (pts and closed):
            subs.append((pts, closed))
        pts = []

    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                if pts:
                    pts.append((sx, sy))
                flush(True)
                x, y = sx, sy
                pts = [(x, y)]
                last_c = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "M":
            flush()
            x, y = ox + num(), oy + num()
            sx, sy = x, y
            pts = [(x, y)]
            cmd = "l" if rel else "L"
            last_c = None
        elif c == "L":
            x, y = ox + num(), oy + num()
            pts.append((x, y))
            last_c = None
        elif c == "H":
            x = ox + num()
            pts.append((x, y))
            last_c = None
        elif c == "V":
            y = (y if rel else 0.0) + num()
            pts.append((x, y))
            last_c = None
        elif c == "C":
            p1 = (ox + num(), oy + num())
            p2 = (ox + num(), oy + num())
            p3 = (ox + num(), oy + num())
            pts.extend(_bezier((x, y), p1, p2, p3))
            x, y = p3
            last_c = p2
        elif c == "S":
            p1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
            p2 = (ox + num(), oy + num())
            p3 = (ox + num(), oy + num())
            pts.extend(_bezier((x, y), p1, p2, p3))
            x, y = p3
            last_c = p2
        elif c == "A":
            rx, ry, phi, fa, fs = num(), num(), num(), num(), num()
            ex, ey = ox + num(), oy + num()
            pts.extend(_arc(x, y, rx, ry, phi, int(fa), int(fs), ex, ey))
            x, y = ex, ey
            last_c = None
        else:  # lệnh không dùng tới trong bộ icon này
            i += 1
    if not pts or len(pts) > 1:
        flush()
    return subs


def _rect_path(x, y, w, h, r) -> str:
    if not r:
        return f"M{x} {y}h{w}v{h}h{-w}Z"
    return (f"M{x + r} {y}h{w - 2 * r}a{r} {r} 0 0 1 {r} {r}v{h - 2 * r}"
            f"a{r} {r} 0 0 1 {-r} {r}h{-(w - 2 * r)}a{r} {r} 0 0 1 {-r} {-r}"
            f"v{-(h - 2 * r)}a{r} {r} 0 0 1 {r} {-r}Z")


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def render(name: str, size: int, color: str, stroke: float = 2.0) -> Image.Image:
    """Vẽ icon `name` cỡ `size` px, màu `color` → ảnh RGBA."""
    spec = LUCIDE.get(name) or LUCIDE["square"]
    k = 4
    big = size * k
    scale = big / 24.0
    w = max(1.0, stroke * scale)
    mask = Image.new("L", (big, big), 0)
    dr = ImageDraw.Draw(mask)

    def stroke_poly(points, closed):
        pts = [(px * scale, py * scale) for px, py in points]
        if closed and pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) > 1:
            dr.line(pts, fill=255, width=int(round(w)), joint="curve")
        r = w / 2
        for px, py in (pts if len(pts) < 3 else [pts[0], pts[-1]] + pts[1:-1]):
            dr.ellipse((px - r, py - r, px + r, py + r), fill=255)

    for el in spec:
        kind = el[0]
        if kind == "path":
            for pts, closed in parse_path(el[1]):
                stroke_poly(pts, closed)
        elif kind == "rect":
            _, x, y, rw, rh, rr = el
            for pts, closed in parse_path(_rect_path(x, y, rw, rh, rr)):
                stroke_poly(pts, closed)
        elif kind == "line":
            _, x1, y1, x2, y2 = el
            stroke_poly([(x1, y1), (x2, y2)], False)
        elif kind == "poly":
            nums = [float(v) for v in _NUM.findall(el[1])]
            stroke_poly(list(zip(nums[0::2], nums[1::2])), el[2])
        elif kind == "circle":
            _, cx, cy, r = el
            cx, cy, r = cx * scale, cy * scale, r * scale
            dr.ellipse((cx - r - w / 2, cy - r - w / 2, cx + r + w / 2, cy + r + w / 2),
                       fill=255)
            if r - w / 2 > 0:
                dr.ellipse((cx - r + w / 2, cy - r + w / 2, cx + r - w / 2, cy + r - w / 2),
                           fill=0)
        elif kind == "dot":
            _, cx, cy = el
            cx, cy, r = cx * scale, cy * scale, w * 0.75
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)

    mask = mask.resize((size, size), Image.LANCZOS)
    img = Image.new("RGBA", (size, size), _hex(color) + (0,))
    img.putalpha(mask)
    return img


_cache: dict[tuple, ImageTk.PhotoImage] = {}


def photo(name: str, size: int, color: str, stroke: float = 2.0) -> ImageTk.PhotoImage:
    """PhotoImage có cache — giữ tham chiếu nên Tk không xoá ảnh."""
    key = (name, size, color, stroke)
    img = _cache.get(key)
    if img is None:
        img = ImageTk.PhotoImage(render(name, size, color, stroke))
        _cache[key] = img
    return img


def from_glyph(glyph: str) -> str:
    """Tên icon lucide cho ký tự icon cũ ('' nếu không có)."""
    return GLYPH.get(glyph, glyph if glyph in LUCIDE else "")
