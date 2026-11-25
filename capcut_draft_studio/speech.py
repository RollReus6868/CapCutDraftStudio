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


# --------------------------------------------------------------------------- #
# mốc thời gian THẬT của từng từ (0.6.3)
# --------------------------------------------------------------------------- #
#: tên khung ID3 TXXX mà TTS Clone Studio 3.3+ ghi vào MP3
TIMING_TAG = "WORD_TIMINGS"
#: khớp lời thoại với mốc dưới mức này thì dùng thẳng các từ trong mốc
MIN_COVERAGE = 0.5


def _syncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3_txxx(path: Path, name: str) -> str | None:
    """Giá trị khung ID3v2.3/2.4 TXXX có mô tả `name` (None nếu không có)."""
    import struct
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if len(head) < 10 or head[:3] != b"ID3":
                return None
            ver, flags = head[3], head[5]
            body = f.read(_syncsafe(head[6:10]))
    except OSError:
        return None
    pos = 0
    if flags & 0x40 and len(body) >= 4:
        pos = _syncsafe(body[:4]) if ver == 4 else struct.unpack(">I", body[:4])[0] + 4
    while pos + 10 <= len(body):
        fid = body[pos:pos + 4]
        if fid == b"\0\0\0\0":
            break
        raw = body[pos + 4:pos + 8]
        size = _syncsafe(raw) if ver == 4 else struct.unpack(">I", raw)[0]
        data = body[pos + 10:pos + 10 + size]
        pos += 10 + size
        if fid != b"TXXX" or not data:
            continue
        enc, rest = data[0], data[1:]
        if enc in (1, 2):
            codec, sep = ("utf-16" if enc == 1 else "utf-16-be"), b"\0\0"
            i = 0
            while True:
                i = rest.find(sep, i)
                if i < 0 or i % 2 == 0:
                    break
                i += 1
        else:
            codec, sep = ("latin-1" if enc == 0 else "utf-8"), b"\0"
            i = rest.find(sep)
        if i < 0 or rest[:i].decode(codec, "replace") != name:
            continue
        return rest[i + len(sep):].decode(codec, "replace").rstrip("\0")
    return None


def _parse_timings(raw: str | None):
    import json
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("words"), list):
        return None
    out = []
    for item in obj["words"]:
        try:
            w, s, e = str(item[0]), float(item[1]), float(item[2])
        except (IndexError, TypeError, ValueError):
            continue
        if w.strip() and s >= 0:
            out.append((w, s, max(s, e)))
    if not out:
        return None
    return str(obj.get("engine") or ""), out


@lru_cache(maxsize=512)
def _read_timings(path: str, mtime: float, side_mtime: float = 0.0):
    p = Path(path)
    side = p.with_name(p.stem + ".words.json")
    if side.is_file():
        try:
            got = _parse_timings(side.read_text(encoding="utf-8-sig"))
        except OSError:
            got = None
        if got:
            return got
    if p.suffix.lower() == ".mp3":
        return _parse_timings(_id3_txxx(p, TIMING_TAG))
    return None


def read_timings(audio) -> tuple[str, list[tuple[str, float, float]]] | None:
    """(bộ máy, [(từ, bắt đầu, kết thúc)]) mà TTS Clone Studio ghi vào file giọng
    (khung ID3 WORD_TIMINGS) hoặc file `<tên>.words.json` cạnh nó. None = không có."""
    if not audio:
        return None
    p = Path(audio)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    side = p.with_name(p.stem + ".words.json")
    try:
        side_mtime = side.stat().st_mtime
    except OSError:
        side_mtime = 0.0
    return _read_timings(str(p), mtime, side_mtime)


def _split_timed(timed) -> list[tuple[str, float, float]]:
    """Mốc từng từ → từ đã chuẩn hoá; một mục thành nhiều từ (seventy-two) thì
    chia đều thời gian của nó."""
    out = []
    for w, s, e in timed:
        parts = norm_words(w)
        if not parts:
            continue
        step = (e - s) / len(parts)
        for k, part in enumerate(parts):
            out.append((part, s + k * step, s + (k + 1) * step))
    return out


def align(text: str, timed) -> tuple[list[tuple[str, float, float]], float]:
    """Gán mốc thật cho từng từ của lời thoại `text`.

    Từ khớp với mốc lấy đúng giờ của mốc; từ không khớp (số viết khác, lời
    thoại sửa một chút) được chia trong khoảng giữa hai từ khớp hai bên — sai số
    chỉ còn trong một khe rất ngắn. Trả về (danh sách, tỉ lệ từ khớp)."""
    from difflib import SequenceMatcher
    tk = _split_timed(timed)
    units: list[tuple[str, float]] = []
    for raw in re.split(r"\s+", str(text or "").strip()):
        parts = norm_words(raw)
        wt = _weight(raw) if parts else 0.0
        for part in parts:
            units.append((part, wt / len(parts)))
    if not units or not tk:
        return [], 0.0
    a, b = [u[0] for u in units], [t[0] for t in tk]
    match: dict[int, int] = {}
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            match[blk.a + k] = blk.b + k
    out: list[tuple[str, float, float] | None] = [None] * len(a)
    for i, j in match.items():
        out[i] = (a[i], tk[j][1], tk[j][2])
    i = 0
    while i < len(a):
        if out[i] is not None:
            i += 1
            continue
        k = i
        while k < len(a) and out[k] is None:
            k += 1
        # khe [i, k): giữa từ khớp i-1 và k
        jl = match.get(i - 1, -1)
        jr = match.get(k, len(tk))
        gap = tk[jl + 1:jr]
        if i == 0 and k < len(a):            # đầu lời: chỉ lấy từng ấy mốc ngay trước từ khớp
            gap = gap[-(k - i):]
        elif k == len(a) and i > 0:          # cuối lời: chỉ lấy từng ấy mốc ngay sau từ khớp
            gap = gap[:k - i]
        if gap:
            lo, hi = gap[0][1], gap[-1][2]
        else:
            lo = tk[jl][2] if jl >= 0 else (tk[jr][1] if jr < len(tk) else 0.0)
            hi = tk[jr][1] if jr < len(tk) else lo
        hi = max(lo, hi)
        total = sum(units[x][1] for x in range(i, k)) or 1.0
        acc = 0.0
        for x in range(i, k):
            s0 = lo + (hi - lo) * acc / total
            acc += units[x][1]
            out[x] = (a[x], s0, lo + (hi - lo) * acc / total)
        i = k
    return [o for o in out if o is not None], len(match) / len(a)


#: nhãn nguồn mốc thời gian (báo cáo khớp giọng)
SOURCE_LABELS = {
    "exact": "Mốc chính xác từ file giọng",
    "silence": "Ước lượng (khoảng lặng + độ dài chữ)",
    "plain": "Ước lượng (độ dài chữ + dấu câu)",
}


def scene_timing(text: str, audio, duration: float, ffmpeg: str | None):
    """(thời gian từng từ, nguồn, bộ máy) cho một cảnh.

    Ưu tiên mốc THẬT trong file giọng (TTS Clone Studio 3.3+); không có thì ước
    lượng như 0.6.2 (đo quãng lặng bằng ffmpeg, chia theo độ dài chữ)."""
    got = read_timings(audio)
    if got:
        engine, timed = got
        timed = [(w, min(s, duration), min(e, duration)) for w, s, e in timed] if duration > 0 else timed
        if text and str(text).strip():
            words, cov = align(text, timed)
            if words and cov >= MIN_COVERAGE:
                return words, "exact", engine
        return _split_timed(timed), "exact", engine
    if not text or not str(text).strip():
        return [], "", ""
    words = scene_word_times(text, audio, duration, ffmpeg)
    measured = bool(ffmpeg and audio and Path(audio).is_file())
    return words, ("silence" if measured else "plain"), ""
