"""Quyết định khoảng nghỉ giữa hai cảnh dựa trên LỜI THOẠI.

Vấn đề: chèn cùng một khoảng nghỉ sau mọi cảnh làm hai câu vốn nối nhau bị
tách ra, nghe rời rạc. Nhưng tool đã có sẵn lời thoại từng cảnh (Texts/,
_manifest.json hoặc Excel), nên đoán được chỗ nào là hết ý, chỗ nào là câu
đang dở.

Bốn mức, tính theo bội số của "nghỉ đủ" (`Settings.scene_gap`):

    join  ×0.0   câu chưa kết thúc  → nối liền, không nghỉ
    short ×0.5   hết câu nhưng câu sau mở đầu bằng từ nối → nghỉ ngắn
    full  ×1.0   hết câu bình thường
    long  ×1.6   sang ý mới / đoạn mới

Toàn bộ logic ở đây là hàm thuần, không đụng file lẫn giao diện, để test được.
"""
from __future__ import annotations

import re
import unicodedata

JOIN = "join"
SHORT = "short"
FULL = "full"
LONG = "long"

LEVELS = (JOIN, SHORT, FULL, LONG)

#: nhãn tiếng Việt cho giao diện
LEVEL_LABELS = {
    JOIN: "Nối liền",
    SHORT: "Nghỉ ngắn",
    FULL: "Nghỉ đủ",
    LONG: "Nghỉ dài",
}

#: hệ số mặc định so với "nghỉ đủ"
DEFAULT_MULTIPLIERS = {JOIN: 0.0, SHORT: 0.5, FULL: 1.0, LONG: 1.6}

#: dấu kết thúc một câu trọn vẹn
SENTENCE_END = ".!?"

#: dấu cho thấy câu còn dở
CONTINUING = ",;:-–—"

#: từ nối mở đầu câu sau → hai câu vẫn cùng một mạch
CONNECTORS = {
    # một từ
    "và", "nhưng", "rồi", "nên", "vì", "mà", "còn", "thì", "song", "hoặc",
    "hay", "vậy", "thế", "nhờ", "dù", "tuy", "bởi", "cho", "để",
    # hai từ
    "sau đó", "tiếp theo", "tiếp đó", "ngoài ra", "hơn nữa", "tuy nhiên",
    "do đó", "vì vậy", "vì thế", "bởi vậy", "thế nhưng", "thế là", "vậy là",
    "lúc này", "lúc đó", "khi đó", "nhờ đó", "đồng thời", "mặt khác",
    "trong khi", "không những", "chẳng những", "thực ra", "thật ra",
    "dĩ nhiên", "đương nhiên", "cụ thể", "chính vì", "nghĩa là", "tức là",
    "rốt cuộc", "cuối cùng", "đặc biệt", "thậm chí", "nói chung",
    # ba từ
    "kết quả là", "chính vì thế", "chính vì vậy", "nói cách khác",
    "không chỉ vậy", "không những thế", "một lúc sau", "ngay sau đó",
}

#: mở đầu báo hiệu sang phần mới hẳn → nghỉ dài
TOPIC_STARTERS = {"chương", "phần", "tập", "tóm lại", "kết luận"}

_WS = re.compile(r"\s+")
_LEAD_PUNCT = re.compile(r"^[\s\"'“”‘’(\[\-–—…·•*]+")


def normalize(text: str) -> str:
    return _WS.sub(" ", str(text or "")).strip()


def _last_meaningful_char(text: str) -> str:
    """Ký tự cuối, bỏ qua ngoặc và ngoặc kép đóng."""
    stripped = normalize(text).rstrip("\"'”’)]»")
    return stripped[-1] if stripped else ""


def _first_alpha(text: str) -> str:
    for ch in _LEAD_PUNCT.sub("", normalize(text)):
        if ch.isalpha():
            return ch
    return ""


def _lead_words(text: str, count: int = 3) -> list[str]:
    cleaned = _LEAD_PUNCT.sub("", normalize(text)).lower()
    words = re.findall(r"[^\W\d_]+", cleaned, re.UNICODE)
    return words[:count]


def _is_lower(ch: str) -> bool:
    """Chữ thường có dấu vẫn phải nhận ra đúng."""
    if not ch:
        return False
    return ch.islower() and unicodedata.category(ch) == "Ll"


def starts_with_connector(text: str) -> str:
    """Trả về cụm từ nối ở đầu câu, rỗng nếu không có."""
    words = _lead_words(text, 3)
    for size in (3, 2, 1):
        if len(words) >= size:
            phrase = " ".join(words[:size])
            if phrase in CONNECTORS:
                return phrase
    return ""


def starts_new_topic(text: str) -> str:
    words = _lead_words(text, 2)
    for size in (2, 1):
        if len(words) >= size:
            phrase = " ".join(words[:size])
            if phrase in TOPIC_STARTERS:
                return phrase
    return ""


def classify(current: str, following: str) -> tuple[str, str]:
    """(mức nghỉ, lý do bằng tiếng Việt) cho khoảng giữa hai cảnh."""
    cur = normalize(current)
    nxt = normalize(following)
    if not cur and not nxt:
        return FULL, "không có lời thoại để đối chiếu"
    if not cur:
        return FULL, "cảnh này không có lời thoại"

    last = _last_meaningful_char(cur)

    # 1) câu còn dở — dấu phẩy, hai chấm, gạch nối, hoặc không có dấu kết câu
    if last in CONTINUING:
        return JOIN, f"câu chưa kết thúc (kết thúc bằng “{last}”)"
    if last and last not in SENTENCE_END and last != "…":
        return JOIN, "câu chưa kết thúc (không có dấu chấm câu)"

    # 2) bỏ lửng — người đọc thường ngắt hơi dài ở đây
    if last == "…":
        return LONG, "lời thoại bỏ lửng"

    if not nxt:
        return FULL, "cảnh sau không có lời thoại"

    # 3) câu sau viết thường => vẫn là phần tiếp của câu trước
    if _is_lower(_first_alpha(nxt)):
        return JOIN, "cảnh sau bắt đầu bằng chữ thường"

    # 4) sang phần mới hẳn
    topic = starts_new_topic(nxt)
    if topic:
        return LONG, f"cảnh sau mở sang phần mới (“{topic}”)"

    # 5) cùng một mạch ý
    connector = starts_with_connector(nxt)
    if connector:
        return SHORT, f"cảnh sau nối ý bằng “{connector}”"

    return FULL, "hết câu, sang ý khác"


def seconds(level: str, base_gap: float, multipliers: dict | None = None) -> float:
    mul = dict(DEFAULT_MULTIPLIERS)
    if multipliers:
        mul.update({k: float(v) for k, v in multipliers.items() if k in DEFAULT_MULTIPLIERS})
    return max(0.0, float(base_gap) * mul.get(level, 1.0))


def parse_override(raw) -> tuple[str, float | None]:
    """Đọc một giá trị người dùng đặt riêng cho một cảnh.

    Trả về (mức, số giây cố định). Một trong hai sẽ là rỗng/None:
    tên mức ('join'/'short'/'full'/'long') hoặc một con số giây.
    """
    text = str(raw or "").strip().lower().replace(",", ".")
    if not text or text == "auto":
        return "", None
    if text in LEVELS:
        return text, None
    try:
        return "", max(0.0, float(text))
    except ValueError:
        return "", None


def plan_gap(current: str, following: str, base_gap: float, *,
             mode: str = "smart", multipliers: dict | None = None,
             override=None) -> tuple[float, str, str]:
    """(số giây, mức, lý do) — điểm vào duy nhất mà `media.validate` dùng."""
    level, seconds_value = parse_override(override)
    if seconds_value is not None:
        return seconds_value, "manual", f"bạn đặt riêng {seconds_value:.2f}s"
    if level:
        return (seconds(level, base_gap, multipliers), level,
                f"bạn đặt riêng: {LEVEL_LABELS.get(level, level)}")
    if str(mode).lower() != "smart":
        return max(0.0, float(base_gap)), FULL, "nghỉ cố định"
    detected, reason = classify(current, following)
    return seconds(detected, base_gap, multipliers), detected, reason
