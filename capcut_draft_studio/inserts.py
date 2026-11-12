"""Chèn đoạn phụ (video quảng cáo) vào GIỮA timeline mà giọng đọc vẫn khớp cảnh.

Có hai trục thời gian:

* trục NỘI DUNG — timeline như thể không có quảng cáo (cảnh nối cảnh);
* trục TIMELINE — sau khi chèn quảng cáo.

Quảng cáo chèn sau cảnh N nằm ở thời điểm `at` = lúc cảnh N kết thúc trên trục
nội dung. Mọi thứ bắt đầu từ `at` trở đi bị đẩy lùi đúng bằng độ dài quảng cáo:
hình, giọng đọc, phụ đề, SFX của cảnh N+1… Thứ gì đang chạy ngang qua `at`
(nhạc nền, logo, claim, mã QR) được CẮT làm hai, phần sau nối tiếp đúng chỗ đã
dừng — nên nhạc nền "tạm dừng" trong lúc quảng cáo phát rồi chạy tiếp.

Module thuần: không I/O, không Tk, không pycapcut — để test rẻ.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, NamedTuple

EPS = 1e-6
#: Mẩu nhỏ hơn mức này sau khi cắt thì bỏ (tránh đoạn vụn chồng nhau trong CapCut).
MIN_PIECE = 0.05


def parse_scene_list(raw) -> list[int]:
    """"5" → [5]; "5, 12; 7" → [5, 7, 12]. Sai định dạng → ValueError (tiếng Việt)."""
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        raw = str(int(raw))
    out: set[int] = set()
    for tok in re.split(r"[\s,;]+", str(raw).strip()):
        if not tok:
            continue
        if not tok.isdigit() or int(tok) <= 0:
            raise ValueError(f"'{tok}' không phải số cảnh hợp lệ — gõ số cảnh, "
                             "nhiều cảnh thì cách nhau bằng dấu phẩy (vd 5, 12).")
        out.add(int(tok))
    return sorted(out)


@dataclass(frozen=True)
class Break:
    """Một đoạn chèn: bắt đầu ở `at` (trục NỘI DUNG), dài `length` giây."""

    at: float
    length: float
    after_scene: int = 0


class Piece(NamedTuple):
    """Một mẩu của đoạn đã cắt: đặt ở `start` (trục TIMELINE), đọc tư liệu từ
    giây `src` của đoạn gốc, dài `length`."""

    start: float
    src: float
    length: float


class TimeMap:
    """Đổi thời điểm trục nội dung → trục timeline khi có các đoạn chèn."""

    def __init__(self, breaks: Iterable[Break] = ()):
        self.breaks = sorted((b for b in breaks if b.length > 0), key=lambda b: b.at)

    def __bool__(self) -> bool:
        return bool(self.breaks)

    @property
    def extra(self) -> float:
        """Tổng thời lượng đã chèn."""
        return sum(b.length for b in self.breaks)

    def start(self, t: float) -> float:
        """Thứ BẮT ĐẦU đúng lúc `at` thì nằm SAU đoạn chèn."""
        return t + sum(b.length for b in self.breaks if b.at <= t + EPS)

    def end(self, t: float) -> float:
        """Thứ KẾT THÚC đúng lúc `at` thì nằm TRƯỚC đoạn chèn."""
        return t + sum(b.length for b in self.breaks if b.at < t - EPS)

    def timeline_breaks(self) -> list[tuple[float, Break]]:
        """[(thời điểm trên timeline, Break)] — nơi đặt chính đoạn chèn."""
        out, shift = [], 0.0
        for b in self.breaks:
            out.append((b.at + shift, b))
            shift += b.length
        return out

    def split(self, start: float, length: float) -> list[Piece]:
        """Cắt đoạn [start, start+length) của trục nội dung tại các điểm chèn."""
        end = start + length
        cuts = [b.at for b in self.breaks if start + EPS < b.at < end - EPS]
        bounds = [start, *cuts, end]
        out: list[Piece] = []
        for a, b in zip(bounds, bounds[1:]):
            ln = b - a
            if ln < MIN_PIECE and len(bounds) > 2:
                continue
            out.append(Piece(self.start(a), a - start, ln))
        return out


def plan_breaks(plan, scene_numbers: Iterable[int], length: float) -> list[Break]:
    """Đoạn chèn dài `length` sau mỗi cảnh trong `scene_numbers`.

    `plan` là list ScenePlan (đã có start/end). Cảnh không có trong plan →
    ValueError liệt kê đủ các số sai.
    """
    by_num = {p.number: p for p in plan}
    wanted = list(scene_numbers)
    missing = [n for n in wanted if n not in by_num]
    if missing:
        nums = sorted(by_num)
        rng = f"{nums[0]}–{nums[-1]}" if nums else "không có cảnh nào"
        raise ValueError("Không có cảnh số " + ", ".join(map(str, missing))
                         + f" để chèn quảng cáo phía sau (project có cảnh {rng}).")
    return [Break(by_num[n].end, float(length), n) for n in wanted]


def shift_plan(plan, tmap: TimeMap) -> list:
    """Plan mới với `start` đã đổi sang trục timeline (cảnh không bao giờ bị cắt)."""
    if not tmap:
        return list(plan)
    return [replace(p, start=tmap.start(p.start)) for p in plan]


def envelope_keyframes(points: list[tuple[float, float]], src: float,
                       length: float) -> list[tuple[float, float]]:
    """Keyframe âm lượng cho MỘT mẩu (bắt đầu từ giây `src` của đoạn gốc).

    `points` là [(giây, âm lượng)] trên đoạn gốc, nội suy thẳng giữa các điểm,
    giữ nguyên ngoài khoảng. Trả [(giây trong mẩu, âm lượng)]. Với mẩu nguyên vẹn
    (src = 0) kết quả đúng bằng `points` nằm trong mẩu — không thêm điểm thừa.
    """
    if not points:
        return []
    pts = sorted(points)

    def value(t: float) -> float:
        if t <= pts[0][0]:
            return pts[0][1]
        for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
            if t <= t1:
                return v0 if t1 - t0 < EPS else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return pts[-1][1]

    end = src + length
    out = [(0.0, value(src))]
    out += [(t - src, v) for t, v in pts if src + EPS < t <= end + EPS]
    if any(t > end + EPS for t, _ in pts):
        out.append((length, value(end)))
    return out
