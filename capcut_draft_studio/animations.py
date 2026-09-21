"""Kho hiệu ứng Ken Burns cho ảnh tĩnh + bộ chọn hiệu ứng.

Mỗi hiệu ứng được mô tả bằng dữ liệu (không gọi pycapcut ở đây) để có thể
kiểm thử độc lập. `capcut_engine.apply_image_anim` chịu trách nhiệm dịch
mô tả này thành keyframe thật.

Hệ toạ độ của CapCut:
- `position_x`: dương = dịch sang phải, đơn vị là NỬA chiều rộng khung hình.
  Vậy giá trị 0.10 tương ứng 5% chiều rộng tính từ tâm.
- `position_y`: dương = dịch lên trên, đơn vị là NỬA chiều cao khung hình.
- `uniform_scale`: 1.0 = giữ nguyên kích thước.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# Mức phóng nền khi có dịch chuyển ngang/dọc. Ảnh phải to hơn khung hình thì
# mới có phần dư để trượt, nếu không sẽ lòi viền đen ở mép.
PAN_ZOOM = 1.12


@dataclass(frozen=True)
class Anim:
    """Một hiệu ứng: giá trị đầu → cuối của từng thuộc tính."""

    key: str
    label: str
    scale: tuple[float, float] = (1.0, 1.0)
    pos_x: tuple[float, float] = (0.0, 0.0)
    pos_y: tuple[float, float] = (0.0, 0.0)

    @property
    def moves(self) -> bool:
        return self.pos_x != (0.0, 0.0) or self.pos_y != (0.0, 0.0)

    def min_scale(self) -> float:
        return min(self.scale)

    def max_shift(self) -> float:
        """Độ dịch lớn nhất, quy về tỉ lệ so với TOÀN BỘ chiều khung hình.

        Đơn vị gốc là nửa khung hình nên phải chia đôi.
        """
        return max(abs(v) for v in (*self.pos_x, *self.pos_y)) / 2.0

    def required_scale(self) -> float:
        """Mức phóng tối thiểu để không lộ viền đen khi dịch."""
        return 1.0 + 2.0 * self.max_shift()


# --------------------------------------------------------------------------- #
# Kho hiệu ứng
# --------------------------------------------------------------------------- #
ANIMS: tuple[Anim, ...] = (
    Anim("zoom_in", "Phóng to dần", scale=(1.00, 1.08)),
    Anim("zoom_out", "Thu nhỏ dần", scale=(1.15, 1.00)),
    Anim("pan_left", "Trượt sang trái",
         scale=(PAN_ZOOM, PAN_ZOOM), pos_x=(0.10, -0.10)),
    Anim("pan_right", "Trượt sang phải",
         scale=(PAN_ZOOM, PAN_ZOOM), pos_x=(-0.10, 0.10)),
    Anim("pan_up", "Trượt lên trên",
         scale=(PAN_ZOOM, PAN_ZOOM), pos_y=(-0.10, 0.10)),
    Anim("pan_down", "Trượt xuống dưới",
         scale=(PAN_ZOOM, PAN_ZOOM), pos_y=(0.10, -0.10)),
    Anim("zoom_in_pan", "Phóng to + trượt chéo",
         scale=(1.06, 1.18), pos_x=(-0.05, 0.05), pos_y=(0.04, -0.04)),
    Anim("zoom_out_pan", "Thu nhỏ + trượt chéo",
         scale=(1.18, 1.06), pos_x=(0.05, -0.05), pos_y=(-0.04, 0.04)),
)

BY_KEY: dict[str, Anim] = {a.key: a for a in ANIMS}
EFFECT_KEYS: tuple[str, ...] = tuple(a.key for a in ANIMS)

MODE_OFF = "off"
MODE_VARIETY = "variety"
MODE_RANDOM = "random"

#: Thứ tự hiện trong combobox của giao diện: (giá trị lưu, nhãn tiếng Việt)
MODE_CHOICES: tuple[tuple[str, str], ...] = (
    (MODE_RANDOM, "Ngẫu nhiên (không lặp liền kề)"),
    (MODE_VARIETY, "Luân phiên theo thứ tự"),
    *((a.key, a.label) for a in ANIMS),
    (MODE_OFF, "Tắt hiệu ứng"),
)

ALL_MODES: tuple[str, ...] = tuple(k for k, _ in MODE_CHOICES)


def normalize_mode(mode: str) -> str:
    """Đưa giá trị cài đặt về một mode hợp lệ; giá trị lạ → luân phiên."""
    m = (mode or "").strip().lower()
    return m if m in ALL_MODES else MODE_VARIETY


@dataclass
class AnimPicker:
    """Chọn hiệu ứng cho từng cảnh theo mode đã cài.

    - `off`      → không hiệu ứng
    - `variety`  → chạy vòng qua kho hiệu ứng theo thứ tự
    - `random`   → bốc ngẫu nhiên, KHÔNG trùng hiệu ứng của cảnh ngay trước
    - tên cụ thể → luôn dùng đúng hiệu ứng đó
    """

    mode: str = MODE_VARIETY
    seed: int | None = None
    keys: tuple[str, ...] = EFFECT_KEYS
    _rng: random.Random = field(init=False, repr=False)
    _last: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.mode = normalize_mode(self.mode)
        self._rng = random.Random(self.seed)

    def pick(self, idx: int = 0) -> str:
        """Trả về key hiệu ứng cho cảnh thứ `idx` (0-based)."""
        if self.mode == MODE_OFF or not self.keys:
            return MODE_OFF
        if self.mode == MODE_VARIETY:
            choice = self.keys[idx % len(self.keys)]
        elif self.mode == MODE_RANDOM:
            pool = [k for k in self.keys if k != self._last] or list(self.keys)
            choice = self._rng.choice(pool)
        else:
            choice = self.mode
        self._last = choice
        return choice

    def describe(self) -> str:
        """Mô tả ngắn để ghi vào nhật ký."""
        if self.mode == MODE_OFF:
            return "tắt"
        if self.mode == MODE_RANDOM:
            return f"ngẫu nhiên trong {len(self.keys)} hiệu ứng, không lặp liền kề"
        if self.mode == MODE_VARIETY:
            return f"luân phiên {len(self.keys)} hiệu ứng"
        anim = BY_KEY.get(self.mode)
        return anim.label.lower() if anim else self.mode


def keyframes_for(key: str) -> list[tuple[str, float, float]]:
    """Trả về [(tên thuộc tính, giá trị đầu, giá trị cuối), ...] cho 1 hiệu ứng.

    Thuộc tính không đổi sẽ bị lược bỏ, TRỪ `scale` của các hiệu ứng có dịch
    chuyển — mức phóng nền phải được ghi ra keyframe thì ảnh mới đủ dư để
    trượt mà không lộ viền đen.
    """
    anim = BY_KEY.get(key)
    if anim is None:
        return []
    out: list[tuple[str, float, float]] = []
    if anim.scale != (1.0, 1.0):
        out.append(("uniform_scale", anim.scale[0], anim.scale[1]))
    if anim.pos_x != (0.0, 0.0):
        out.append(("position_x", anim.pos_x[0], anim.pos_x[1]))
    if anim.pos_y != (0.0, 0.0):
        out.append(("position_y", anim.pos_y[0], anim.pos_y[1]))
    return out
