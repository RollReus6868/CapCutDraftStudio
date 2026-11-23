"""Ước lượng lúc từng từ được đọc trong file giọng đọc của một cảnh (0.6.2).

Dùng để đồ họa chữ hiện ĐÚNG lúc giọng đọc nói tới nó, thay vì luôn hiện ở đầu
cảnh. Không cần nhận dạng giọng nói:

1. ffmpeg `silencedetect` tìm các quãng lặng trong file (đầu, cuối và giữa câu);
2. phần còn lại là thời gian đang nói; mỗi từ của lời thoại được chia một phần
   thời gian nói tỉ lệ với độ dài của nó (số chữ cái, số đọc thành chữ);
3. quãng lặng nằm đúng chỗ ngắt câu nên các câu sau một quãng nghỉ tự rơi về
   đúng chỗ — sai số chỉ còn trong phạm vi một câu.

Không có ffmpeg hoặc đọc lỗi → chia đều trên cả file, kèm thêm "trọng lượng"
cho dấu câu (chỗ ngắt nghỉ).

Phần so khớp chữ (`norm_words`, `locate`, `num_words`) là thuần, test rẻ.
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

#: ngưỡng coi là lặng — giọng TTS sạch nên -38 dB, tối thiểu 0,12 s
SILENCE_DB = -38
SILENCE_MIN = 0.12

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _below_1000(n: int) -> list[str]:
    out: list[str] = []
    h, r = divmod(n, 100)
    if h:
        out += [_ONES[h], "hundred"]
    if r:
        if r < 20:
            out.append(_ONES[r])
        else:
            t, o = divmod(r, 10)
            out.append(_TENS[t])
            if o:
                out.append(_ONES[o])
    return out


def num_words(n: int) -> list[list[str]]:
    """Các cách đọc tiếng Anh của một số nguyên: 11 → [[eleven]],
    1964 → [[one thousand nine hundred sixty four], [nineteen sixty four]]."""
    if n < 0 or n > 999_999:
        return []
    if n == 0:
        return [["zero"]]
    th, r = divmod(n, 1000)
    plain = (_below_1000(th) + ["thousand"] if th else []) + _below_1000(r)
    forms = [plain]
    if 1100 <= n <= 1999 or 2010 <= n <= 2099:
        hi, lo = divmod(n, 100)
        year = _below_1000(hi) + (["hundred"] if lo == 0 else
                                  (["oh"] + _below_1000(lo) if lo < 10 else _below_1000(lo)))
        if year != plain:
            forms.append(year)
    if 2000 <= n <= 2009:
        forms.append(["two", "thousand"] + (_below_1000(n - 2000) if n > 2000 else []))
    return forms


def _strip(word: str) -> str:
    w = unicodedata.normalize("NFC", word.lower())
    w = w.replace("’", "'").replace("‘", "'")
    w = re.sub(r"'s$", "", w)
    return "".join(ch for ch in w if ch.isalnum())


def norm_words(text: str) -> list[str]:
    """'Seventy-two, "Elect of God"!' → [seventy, two, elect, of, god]."""
    out = []
    for raw in re.split(r"[\s\-–—/]+", str(text or "")):
        w = _strip(raw)
        if w:
            out.append(w)
    return out


def item_variants(text: str) -> list[list[str]]:
    """Các cách đọc của chữ trên hình: số viết bằng chữ số được đổi ra chữ."""
    base = norm_words(text)
    variants = [base]
    if any(w.isdigit() for w in base):
        alt: list[list[str]] = [[]]
        for w in base:
            if w.isdigit() and len(w) <= 6:
                forms = num_words(int(w)) or [[w]]
                alt = [a + f for a in alt for f in forms][:8]
            else:
                alt = [a + [w] for a in alt]
        variants += [a for a in alt if a != base]
    return [v for v in variants if v]


def locate(item_words: list[str], seq: list[str]) -> tuple[int, int, int] | None:
    """Tìm chữ trên hình trong chuỗi lời đọc.

    Trả (vị trí trong seq, vị trí tương ứng trong item, số từ khớp liền nhau),
    hoặc None. Ưu tiên khớp trọn; không có thì lấy đoạn khớp liền dài nhất
    (≥ 2 từ, hoặc 1 từ dài ≥ 4 chữ cái khi chữ trên hình chỉ 1–2 từ)."""
    n, m = len(item_words), len(seq)
    if not n or not m:
        return None
    if n == 1 and len(item_words[0]) < 4:
        return None                      # một từ ngắn (the, of…) không đủ tin
    for i in range(m - n + 1):
        if seq[i:i + n] == item_words:
            return i, 0, n
    best = None
    for i in range(m):
        for j in range(n):
            k = 0
            while i + k < m and j + k < n and seq[i + k] == item_words[j + k]:
                k += 1
            if k and (best is None or k > best[2]):
                best = (i, j, k)
    if best is None:
        return None
    need = 2 if n > 2 else 1
    if best[2] < need:
        return None
    if best[2] == 1 and len(item_words[best[1]]) < 4:
        return None
    return best


# --------------------------------------------------------------------------- #
# thời gian từng từ
# --------------------------------------------------------------------------- #
def _weight(word: str) -> float:
    """Thời lượng đọc tương đối: số chữ cái, số được đọc thành chữ."""
    w = _strip(word)
    if w.isdigit() and len(w) <= 6:
        forms = num_words(int(w))
        if forms:
            return sum(len(x) for x in forms[-1]) + len(forms[-1])
    return max(1.0, len(w)) + 1.0


def _pause_weight(word: str) -> float:
    """Chỉ dùng khi không đo được quãng lặng: dấu câu ≈ một chỗ ngắt nghỉ."""
    if re.search(r"[.!?…]['\"”’)]*$", word):
        return 7.0
    if re.search(r"[,;:—–]['\"”’)]*$", word):
        return 3.5
    return 0.0


@lru_cache(maxsize=512)
def silences(path: str, mtime: float, ffmpeg: str) -> tuple[tuple[float, float], ...]:
    """Các quãng lặng (bắt đầu, kết thúc) theo ffmpeg silencedetect."""
    from .render import _no_window
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-i", path, "-af",
           f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                            encoding="utf-8", errors="replace", **_no_window())
    except Exception:
        return ()
    out: list[tuple[float, float]] = []
    start = None
    for line in cp.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:
        out.append((start, float("inf")))
    return tuple(out)


def speech_spans(duration: float, quiet) -> list[tuple[float, float]]:
    """Phần đang nói = [0, duration] trừ các quãng lặng."""
    spans, t = [], 0.0
    for a, b in sorted(quiet):
        a, b = max(0.0, a), min(duration, b)
        if b <= a:
            continue
        if a > t:
            spans.append((t, a))
        t = max(t, b)
    if t < duration:
        spans.append((t, duration))
    spans = [(a, b) for a, b in spans if b - a > 0.02]
    return spans or [(0.0, duration)]


def word_times(text: str, duration: float, quiet=None) -> list[tuple[str, float, float]]:
    """[(từ đã chuẩn hoá, bắt đầu, kết thúc)] tính từ đầu file giọng đọc.

    `quiet` = các quãng lặng đo được (None = không đo được → chia theo dấu câu)."""
    raw = [w for w in re.split(r"\s+", str(text or "").strip()) if w]
    if not raw or duration <= 0:
        return []
    # mỗi từ thô có thể sinh nhiều từ chuẩn hoá (seventy-two → seventy, two)
    units: list[tuple[str, float, float]] = []      # (từ, trọng lượng, nghỉ sau)
    for w in raw:
        parts = norm_words(w)
        if not parts:
            continue
        wt = _weight(w)
        for k, p in enumerate(parts):
            pause = _pause_weight(w) if (quiet is None and k == len(parts) - 1) else 0.0
            units.append((p, wt / len(parts), pause))
    if not units:
        return []
    spans = speech_spans(duration, quiet or ())
    if quiet is None:
        spans = [(0.0, duration)]
    talk = sum(b - a for a, b in spans)
    total = sum(u[1] + u[2] for u in units)

    def at(frac: float, start: bool) -> float:
        """Vị trí `frac` (0..1) của thời gian nói → giây trong file. Từ bắt đầu
        đúng ở mép một quãng lặng thì tính sang đầu đoạn nói kế tiếp."""
        left = max(0.0, min(1.0, frac)) * talk
        for k, (a, b) in enumerate(spans):
            ln = b - a
            if left < ln - 1e-9 or (not start and left <= ln + 1e-9) or k == len(spans) - 1:
                return a + min(left, ln)
            left -= ln
        return spans[-1][1]

    out, acc = [], 0.0
    for word, wt, pause in units:
        s = at(acc / total, True)
        acc += wt
        e = at(acc / total, False)
        acc += pause
        out.append((word, s, e))
    return out


def scene_word_times(text: str, audio: Path, duration: float, ffmpeg: str | None):
    """word_times cho một cảnh, đo quãng lặng nếu có ffmpeg."""
    quiet = None
    if ffmpeg and audio and Path(audio).is_file():
        try:
            st = Path(audio).stat()
            found = silences(str(audio), st.st_mtime, ffmpeg)
            quiet = list(found)
        except Exception:
            quiet = None
    return word_times(text, duration, quiet)
