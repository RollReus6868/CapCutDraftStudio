"""Chuyển động của đồ họa chữ (0.6.4): hiện/tắt mượt bằng keyframe có gia tốc.

Mỗi đồ họa có một kiểu chuyển động (`Motion`): lúc hiện thì từ trạng thái đầu
(trong suốt, lệch vị trí, to/nhỏ hơn) về trạng thái chuẩn theo đường cong chậm
dần (ease-out), lúc tắt thì ngược lại theo đường nhanh dần (ease-in).

Một bộ công thức dùng chung cho cả hai đường ra:

* draft CapCut: `keyframes()` lấy mẫu đường cong thành nhiều keyframe tuyến tính
  (alpha, vị trí, tỉ lệ) — CapCut nội suy thẳng giữa các điểm nên dày điểm ở
  đoạn đầu là thành đường cong mượt;
* render ffmpeg: `ffmpeg_exprs()` viết cùng công thức thành biểu thức theo `t`.

Phóng to/thu nhỏ quanh TÂM CỦA ĐỒ HỌA (không phải tâm khung hình): vị trí được
bù (1 − s)·(tâm đồ họa − tâm khung).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

#: hệ số easeOutBack của kiểu "slam" (càng lớn càng nảy)
BACK = 1.25


@dataclass(frozen=True)
class Motion:
    din: float = 0.0         # thời gian chuyển động lúc hiện (giây)
    dout: float = 0.0        # thời gian lúc tắt
    ain: float = 0.0         # thời gian alpha 0 → 1 (≤ din); 0 = không mờ dần
    dx: float = 0.0          # lệch lúc bắt đầu hiện, theo bề ngang khung (dương = sang phải)
    dy: float = 0.0          # lệch lúc bắt đầu hiện, theo chiều cao khung (dương = xuống)
    s0: float = 1.0          # tỉ lệ lúc bắt đầu hiện
    drift: float = 0.0       # phóng to thêm chừng này trong suốt thời gian hiện (rất chậm)
    ox: float = 0.0          # lệch khi tắt xong
    oy: float = 0.0
    so: float = 1.0          # tỉ lệ khi tắt xong
    fade_out: bool = True    # tắt bằng mờ dần (thanh khung điện ảnh thì trượt ra)
    back: bool = False       # nảy nhẹ khi về tỉ lệ chuẩn (dấu mộc đóng xuống)

    @property
    def moves(self) -> bool:
        return bool(self.dx or self.dy or self.ox or self.oy)

    @property
    def scales(self) -> bool:
        return self.s0 != 1.0 or self.so != 1.0 or bool(self.drift)


NONE = Motion()

#: các kiểu chuyển động (tên dùng trong lịch, giữ tiếng Anh cho ổn định)
PRESETS: dict[str, Motion] = {
    "none": NONE,
    "fade": Motion(0.45, 0.35, 0.40),
    "rise": Motion(0.60, 0.35, 0.40, dy=0.028),
    "slide_left": Motion(0.60, 0.35, 0.40, dx=-0.045),
    "slide_right": Motion(0.60, 0.35, 0.40, dx=0.045),
    "drop": Motion(0.60, 0.35, 0.40, dy=-0.03),
    "pop": Motion(0.55, 0.35, 0.40, s0=0.92),
    "settle": Motion(0.90, 0.40, 0.50, s0=1.07, drift=0.025),
    "slam": Motion(0.42, 0.30, 0.12, s0=1.65, back=True),
    # khung điện ảnh: dy/oy được điền theo cỡ thanh (bar_motion)
    "bar_top": Motion(0.70, 0.55, 0.0, fade_out=False),
    "bar_bottom": Motion(0.70, 0.55, 0.0, fade_out=False),
}


def bar_motion(name: str, bar_frac: float) -> Motion:
    """Thanh đen trên/dưới trượt vào từ mép khung và trượt ra khi tắt."""
    d = -bar_frac if name == "bar_top" else bar_frac
    return replace(PRESETS[name], dy=d, oy=d)


def get(name: str | None) -> Motion:
    return PRESETS.get(name or "none", NONE)


def _clip(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def ease_out(p: float) -> float:
    return 1.0 - (1.0 - p) ** 3


def ease_back(p: float) -> float:
    q = p - 1.0
    return 1.0 + (BACK + 1.0) * q ** 3 + BACK * q ** 2


def ease_in(p: float) -> float:
    return p ** 3


def durations(m: Motion, length: float) -> tuple[float, float, float]:
    """(din, ain, dout) co lại cho vừa đoạn ngắn: hiện ≤ 45 %, tắt ≤ 40 % độ dài."""
    din = min(m.din, length * 0.45)
    k = din / m.din if m.din else 0.0
    return din, m.ain * k, min(m.dout, length * 0.40)


def state(m: Motion, t: float, length: float, fade_in: bool = True,
          fade_out: bool = True) -> tuple[float, float, float, float]:
    """(alpha, dx, dy, s) tại giây t (0 = đầu đoạn). dx, dy theo phần khung."""
    din, ain, dout = durations(m, length)
    e = 1.0
    a = 1.0
    if fade_in and din > 0:
        p = _clip(t / din)
        e = ease_back(p) if m.back else ease_out(p)
        if ain > 0:
            a = ease_out(_clip(t / ain))
    eo = 0.0
    if fade_out and dout > 0:
        eo = ease_in(_clip((t - (length - dout)) / dout))
        if m.fade_out:
            a *= 1.0 - eo
    s = (m.s0 + (1.0 - m.s0) * e) * (1.0 + m.drift * _clip(t / length if length else 0.0))
    s *= 1.0 + (m.so - 1.0) * eo
    dx = m.dx * (1.0 - e) + m.ox * eo
    dy = m.dy * (1.0 - e) + m.oy * eo
    return a, dx, dy, s


#: số điểm lấy mẫu cho mỗi lần hiện / tắt (CapCut nội suy thẳng giữa các điểm)
IN_SAMPLES = 9
OUT_SAMPLES = 6


def sample_times(m: Motion, length: float, fade_in: bool = True, fade_out: bool = True) -> list[float]:
    """Các mốc (giây trong đoạn) cần keyframe."""
    din, ain, dout = durations(m, length)
    ts = {0.0, length}
    if fade_in and din > 0:
        for i in range(IN_SAMPLES + 1):
            # dày điểm ở đầu, nơi đường cong đổi nhanh
            ts.add(din * (i / IN_SAMPLES) ** 1.6)
        if ain > 0:
            ts.add(ain)
    if fade_out and dout > 0:
        for i in range(OUT_SAMPLES + 1):
            ts.add(length - dout + dout * (i / OUT_SAMPLES) ** 0.7)
    return sorted(t for t in ts if 0.0 <= t <= length)


def keyframes(m: Motion, length: float, size: tuple[int, int], anchor: tuple[float, float],
              piece: tuple[float, float] | None = None, fade_in: bool = True,
              fade_out: bool = True) -> dict[str, list[tuple[float, float]]]:
    """Keyframe cho CapCut: {"alpha"|"x"|"y"|"scale": [(giây trong mẩu, giá trị)]}.

    x, y theo đơn vị của pycapcut (nửa bề ngang / nửa chiều cao khung, y dương =
    lên). `anchor` = tâm đồ họa (px) tính từ góc trên trái. `piece` = (từ, dài)
    khi đoạn bị quảng cáo cắt làm nhiều mẩu — chỉ lấy phần rơi vào mẩu đó."""
    w, h = size
    ax, ay = anchor[0] - w / 2.0, anchor[1] - h / 2.0
    p0, plen = piece if piece else (0.0, length)
    times = [t for t in sample_times(m, length, fade_in, fade_out) if p0 - 1e-9 <= t <= p0 + plen + 1e-9]
    times = sorted({p0, p0 + plen, *times})
    out: dict[str, list[tuple[float, float]]] = {"alpha": [], "x": [], "y": [], "scale": []}
    for t in times:
        a, dx, dy, s = state(m, t, length, fade_in, fade_out)
        px = dx * w + (1.0 - s) * ax
        py = dy * h + (1.0 - s) * ay
        lt = t - p0
        out["alpha"].append((lt, round(a, 4)))
        out["x"].append((lt, round(px / (w / 2.0), 5)))
        out["y"].append((lt, round(-py / (h / 2.0), 5)))
        out["scale"].append((lt, round(s, 5)))
    # bỏ thuộc tính không đổi (đỡ rối timeline CapCut)
    for key, neutral in (("alpha", 1.0), ("x", 0.0), ("y", 0.0), ("scale", 1.0)):
        vals = {v for _, v in out[key]}
        if vals == {neutral}:
            out[key] = []
    return out


# --------------------------------------------------------------------------- #
# ffmpeg
# --------------------------------------------------------------------------- #
def _f(v: float) -> str:
    return f"{v:.5f}"


def ffmpeg_exprs(m: Motion, a: float, length: float, fade_in: bool = True,
                 fade_out: bool = True) -> dict[str, str]:
    """Biểu thức theo `t` (giây của clip cảnh) cho: s (tỉ lệ), dx, dy (phần khung).
    `a` = giây bắt đầu của đồ họa trong clip (có thể âm nếu bắt đầu ở cảnh trước)."""
    din, _ain, dout = durations(m, length)
    T = f"(t-({_f(a)}))"
    if fade_in and din > 0:
        p = f"clip({T}/{_f(din)},0,1)"
        if m.back:
            e = f"(1+{_f(BACK + 1)}*pow({p}-1,3)+{_f(BACK)}*pow({p}-1,2))"
        else:
            e = f"(1-pow(1-{p},3))"
    else:
        e = "1"
    eo = f"pow(clip(({T}-{_f(length - dout)})/{_f(dout)},0,1),3)" if (fade_out and dout > 0) else "0"
    s = f"(({_f(m.s0)}+{_f(1 - m.s0)}*{e})"
    if m.drift:
        s += f"*(1+{_f(m.drift)}*clip({T}/{_f(length)},0,1))"
    if m.so != 1.0:
        s += f"*(1+{_f(m.so - 1)}*{eo})"
    s += ")"
    dx = f"({_f(m.dx)}*(1-{e})+{_f(m.ox)}*{eo})"
    dy = f"({_f(m.dy)}*(1-{e})+{_f(m.oy)}*{eo})"
    return {"s": s if m.scales else "1", "dx": dx if (m.dx or m.ox) else "0",
            "dy": dy if (m.dy or m.oy) else "0"}
