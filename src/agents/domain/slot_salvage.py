"""Last-resort parsing for the exact slot asked on the previous turn."""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.budget_parsing import (
    NO_BUDGET_LIMIT_PATTERN,
    NO_BUDGET_LIMIT_VND,
    parse_budget_range,
    parse_budget_vnd,
)
from src.agents.domain.catalog_browse import requested_vehicle_types
from src.agents.domain.values import SlotName, SlotValue, VehicleType

_NON_ANSWER_PATTERN = re.compile(
    r"\b(?:chưa biết|chua biet|không biết|khong biet|chưa rõ|chua ro|không rõ|"
    r"khong ro|tùy em|tuy em|tùy bạn|tuy ban|sao cũng được|sao cung duoc|"
    r"(?:xe\s*)?nào\s*cũng\s*được|(?:xe\s*)?nao\s*cung\s*duoc|"
    r"tư\s*vấn\s*giúp|tu\s*van\s*giup|"
    r"chưa nghĩ|chua nghi|không rành|khong ranh)\b",
    re.IGNORECASE,
)
_BARE_REFUSAL_PATTERN = re.compile(
    r"^(?:anh|em|mình|minh|tôi|toi|dạ|da|ừ|u)?\s*"
    r"(?:không|khong|ko|k|thôi|thoi|chưa|chua)\s*"
    r"(?:có|co|ạ|a|đâu|dau|gì|gi)?\s*$",
    re.IGNORECASE,
)
#: Câu từ chối đứng một mình. Mở rộng 2026-08-25 (Sếp báo: khách đáp "không nhé"
#: hoặc "không cần tính năng gì" ở lượt hỏi tính năng và nhận về "ngoài phạm vi").
#:
#: Ba lỗ của bản cũ, đều là cách nói rất thường:
#: - đuôi lịch sự: "không **nhé**", "không **đâu ạ**";
#: - nêu lại TÂN NGỮ: "không cần **tính năng gì**", "không cần **gì thêm**";
#: - động từ khác: "**thôi khỏi**", "**bỏ qua**".
#:
#: Đuôi CHỈ nhận một tập từ đệm đóng, KHÔNG nhận chữ tự do.
#:
#: Bản nháp đầu dùng `[^.?!]*` cho đuôi và để `k` làm một cách viết tắt của
#: "không". Hậu quả: MỌI câu bắt đầu bằng chữ "k" thành lời từ chối — "khoá chống
#: trộm", đúng một tính năng khách hay chọn, bị đọc thành "khách không cần gì".
#: Sai theo chiều tệ nhất: nuốt mất câu trả lời thật.
#:
#: Nay `\b` buộc từ chối phải là một TỪ TRỌN VẸN, và đuôi chỉ được ghép từ những
#: từ không mang thông tin nào.
_STANDALONE_REFUSAL_PATTERN = re.compile(
    r"^(?:dạ|da|ừ|u|à)?\s*"
    r"(?:không|khong|ko|thôi|thoi)\b\s*"
    r"(?:(?:cần|can|có|co|khỏi|khoi|bỏ qua|bo qua|gì|gi|chi|nào|nao|"
    r"tính năng|tinh nang|thêm|them|đặc biệt|dac biet|nữa|nua|"
    # "không" cũng là TỪ ĐỆM hợp lệ ở đuôi: "thôi không", "thôi không cần".
    # Thiếu nó thì "thôi không" — cách từ chối rất thường — trượt, và khách nhận
    # về lời từ chối phạm vi (đo trên prod 2026-08-26).
    r"không|khong|ko|thôi|thoi|"
    r"ạ|a|đâu|dau|nhé|nhe|nha|em|anh|ah)\s*)*$",
    re.IGNORECASE,
)
_QUESTION_PATTERN = re.compile(
    r"(?:\?|bao nhiêu|bao nhieu|thế nào|the nao|khác nhau|khac nhau|là gì|la gi|"
    r"có nên|co nen|nên chọn|nen chon)",
    re.IGNORECASE,
)
_DISTANCE_UNIT_PATTERN = re.compile(r"\bkm\b", re.IGNORECASE)
_MONEY_UNIT_PATTERN = re.compile(
    r"\b(?:triệu|trieu|tr\b|tỷ|tỉ|ty|ti\b|củ|cu|nghìn|nghin)\b",
    re.IGNORECASE,
)
_WORD_NUMBERS = {
    "một": 1,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "bon": 4,
    "tư": 4,
    "năm": 5,
    "nam": 5,
    "sáu": 6,
    "sau": 6,
    "bảy": 7,
    "bay": 7,
    "tám": 8,
    "tam": 8,
    "chín": 9,
    "chin": 9,
    "mười": 10,
    "muoi": 10,
}
_SEAT_WORDS = r"(?:chỗ|cho|người|nguoi|ghế|ghe)"
_PASSENGER_PATTERN = re.compile(rf"(\d+)\s*{_SEAT_WORDS}", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"\b(\d+)\b")
_MAX_FREE_TEXT_LENGTH = 300


def salvaged_vehicle_type(user_message: str) -> VehicleType | None:
    """Nhánh xe khách vừa chọn khi được hỏi thẳng "ô tô điện hay xe máy điện?".

    Trả `None` khi câu KHÔNG chốt đúng một nhánh, và đó là ba ca khác nhau đều
    phải dẫn tới cùng một kết cục "chưa biết":

    - không nêu loại nào ("cho tôi hỏi giờ mở cửa showroom") — khách đổi chủ đề;
    - nêu cả hai ("xem cả ô tô và xe máy điện") — chưa chọn;
    - nêu thứ đúng cho cả hai ("xe điện") — VinFast bán cả hai dòng, nên đoán một
      nhánh là bịa ra một nửa cuộc tư vấn.

    Dùng chung bảng alias với nhánh xem danh mục A4-7 (`requested_vehicle_types`),
    nên chỉ có MỘT chỗ định nghĩa "người Việt gọi hai dòng xe này là gì". Bảng đó
    khớp theo RANH GIỚI TỪ, và đây là lý do không dùng
    `vehicle_type_lock.explicit_vehicle_type` cho việc này dù nó cùng chủ đề: nó
    tìm chuỗi con, nên "cho tôi hỏi giờ mở cửa showroom" khớp "o tô" trong "cho
    tôi" và biến một câu lạc đề thành một lựa chọn ô tô.
    """

    if not user_message.strip():
        return None
    requested = requested_vehicle_types(user_message)
    return requested[0] if len(requested) == 1 else None


def is_non_answer(user_message: str) -> bool:
    """Return whether text evades or plainly refuses the pending question."""

    text = _normalize(user_message)
    return (
        _NON_ANSWER_PATTERN.search(text) is not None
        or _BARE_REFUSAL_PATTERN.fullmatch(text) is not None
        or _STANDALONE_REFUSAL_PATTERN.fullmatch(text) is not None
    )


#: Vị từ "câu mơ hồ" — KHÁC `is_non_answer`: không phải lời từ chối, nhưng cũng
#: không quy được về giá trị. "tầm tầm thôi", "cũng khá xa", "chở được vài người"
#: không khớp mẫu từ chối, mà bộ trích cũng không lấy ra số nào — rơi vào khoảng
#: giữa, không ai xử. Từ khoá là TỪ TRỌN VẸN (`\b`), không có "khoảng" hay "cỡ"
#: vì hai chữ đó xuất hiện trong câu trả lời CÓ GIÁ TRỊ ("khoảng 500 triệu").
_VAGUE_ANSWER_PATTERN = re.compile(
    r"\b(?:tầm\s*tầm|tam\s*tam|"
    r"cũng\s*(?:khá|tạm)|cung\s*(?:kha|tam)|"
    r"khá\s*khá|kha\s*kha|"
    r"vài|vai|"
    r"đại\s*khái|dai\s*khai|tương\s*đối|tuong\s*doi|"
    r"khoảng\s*chừng|khoang\s*chung)\b",
    re.IGNORECASE,
)


def is_vague_answer(user_message: str) -> bool:
    """Return whether the customer answered with a vague qualifier, not a value."""

    return _VAGUE_ANSWER_PATTERN.search(_normalize(user_message)) is not None


# ── J3: LLM judge vague answer — lớp HAI sau regex (plan chống-crack) ─────────
# Bất biến như J1/J2: judge CHỈ THÊM, không gỡ. Regex `is_vague_answer` là đáy;
# judge bắt câu né giá trị bằng cách nói khác ("tính thêm đã", "tạm xem vậy").
# SHADOW mặc định: chỉ đo, không đổi kết quả. Judge lỗi → không thêm gì.
VAGUE_LLM_SHADOW_MODE: Final[bool] = True
VAGUE_CONFIDENCE_THRESHOLD: Final[float] = 0.90
VAGUE_SAMPLE_RATE: Final[float] = 0.20


class VagueFallbackReason(StrEnum):
    """Lý do judge vague fail-open về "không mơ hồ"."""

    OPTIONAL_BUDGET_EXHAUSTED = "optional_budget_exhausted"
    MISSING_API_KEY = "missing_api_key"
    TIMEOUT = "timeout"
    EMPTY_TOOL_CALL = "empty_tool_call"
    INVALID_PAYLOAD = "invalid_payload"
    PROVIDER_API_ERROR = "provider_api_error"
    UNEXPECTED_KNOWN_FAILURE = "unexpected_known_failure"


@dataclass(frozen=True, slots=True)
class VagueJudgePrediction:
    """Phán đoán của judge LLM cùng độ chắc chắn đã validate."""

    is_vague: bool
    confidence: float
    fallback_reason: VagueFallbackReason | None = None


def merge_vague_verdict(
    regex_vague: bool,
    prediction: VagueJudgePrediction | None,
    *,
    shadow_mode: bool = VAGUE_LLM_SHADOW_MODE,
    threshold: float = VAGUE_CONFIDENCE_THRESHOLD,
) -> bool:
    """Gộp hai tầng: regex bắt → luôn vague; judge chỉ thêm khi live + đủ ngưỡng."""

    if regex_vague:
        return True
    if shadow_mode or prediction is None:
        return False
    return prediction.is_vague and prediction.confidence >= threshold


def should_sample_vague() -> bool:
    """Lấy mẫu judge vague — không có turn counter rẻ tại điểm gọi."""

    return random.random() < VAGUE_SAMPLE_RATE


def salvage_slot(slot: SlotName, user_message: str, vehicle_type: VehicleType | None = None) -> SlotValue | None:
    """Parse one pending slot from customer text; return ``None`` if unsafe."""

    text = _normalize(user_message)
    if not text or (slot is SlotName.PURPOSE and _QUESTION_PATTERN.search(text)):
        return None
    if slot is SlotName.BUDGET_MAX_VND:
        if _DISTANCE_UNIT_PATTERN.search(text) and not _MONEY_UNIT_PATTERN.search(text):
            return None
        parsed = parse_budget_vnd(text)
        if parsed is not None:
            return parsed
        return NO_BUDGET_LIMIT_VND if NO_BUDGET_LIMIT_PATTERN.search(text) else None
    if is_non_answer(text):
        return None
    if slot is SlotName.PASSENGER_COUNT:
        if vehicle_type is VehicleType.ELECTRIC_MOTORBIKE:
            return None
        return _passenger_count(text)
    if slot is SlotName.PURPOSE:
        cleaned = " ".join(user_message.split())
        return cleaned if len(cleaned) <= _MAX_FREE_TEXT_LENGTH else None
    if slot is SlotName.VEHICLE_TYPE:
        return _vehicle_type(text)
    return None


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


#: Cụm chữ chỉ LOẠI XE. Xe máy xét TRƯỚC: "xe máy điện" chứa cả "xe" lẫn "điện",
#: và một mẫu ô tô lỏng tay sẽ nuốt nó.
_MOTORBIKE_TYPE_CUES: Final[tuple[str, ...]] = (
    "xe may",
    "xemay",
    "xe gan may",
    "xe so",
    "xe tay ga",
    "tay ga",
    "xe dien 2 banh",
    "hai banh",
    "2 banh",
)
_CAR_TYPE_CUES: Final[tuple[str, ...]] = (
    "o to",
    "oto",
    "otô",
    "xe hoi",
    "xe con",
    "xe 4 banh",
    "bon banh",
    "4 banh",
)


def _fold_type(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return " ".join(plain.replace("đ", "d").split())


def _vehicle_type(text: str) -> str | None:
    """Câu trả lời cho câu hỏi LOẠI XE → mã loại, hoặc `None`.

    **Vì sao cần bản đọc tất định này** (Sếp 2026-08-26, đo trên `turn_traces`
    prod): lượt "Ô tô điện" — chính chữ in trên cái nút bot vừa đưa ra — trả về
    `slots_gained={}`. Bộ trích LLM không lấy được loại xe từ câu trả lời rõ ràng
    nhất có thể, và `salvage_slot` không có nhánh nào cho slot này, nên phiên đi
    tiếp mà KHÔNG biết khách chọn gì. Luồng chỉ sống nhờ `inferred_vehicle_type`
    đoán lại từ ngân sách ở lượt sau — một phép đoán thay cho một câu trả lời.

    Chạy CHỈ khi `expected_slot` đang là `VEHICLE_TYPE` (xem `_salvaged_slots`),
    nên "xe máy của tôi hỏng rồi" giữa một cuộc tư vấn ô tô không lọt vào đây.
    """

    folded = _fold_type(text)
    if any(cue in folded for cue in _MOTORBIKE_TYPE_CUES):
        return VehicleType.ELECTRIC_MOTORBIKE.value
    if any(cue in folded for cue in _CAR_TYPE_CUES):
        return VehicleType.CAR.value
    return None


def _passenger_count(text: str) -> int | None:
    match = _PASSENGER_PATTERN.search(text)
    if match is not None:
        return int(match.group(1))
    for word, number in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\s*{_SEAT_WORDS}\b", text):
            return number
    bare = _BARE_NUMBER.search(text)
    if bare is not None and 1 <= int(bare.group(1)) <= 16:
        return int(bare.group(1))
    return None


def salvaged_budget_floor(user_message: str) -> int | None:
    """Sàn ngân sách của câu trả lời cho câu hỏi ngân sách, nếu khách nêu một khoảng.

    Tách khỏi `salvage_slot` vì hàm đó trả ĐÚNG MỘT giá trị cho ĐÚNG MỘT slot, còn
    một câu như "từ 300 đến 700 triệu" điền hai slot. Đổi chữ ký `salvage_slot` để
    trả hai giá trị sẽ kéo theo mọi chỗ gọi nó cho bảy slot còn lại.
    """

    return parse_budget_range(user_message).min_vnd


def salvaged_budget_stated(user_message: str) -> int | None:
    """Con số khách NÓI RA, khi câu trả lời ngân sách là một ước lượng.

    Cùng lý do tách khỏi `salvage_slot` với `salvaged_budget_floor`: một câu
    "khoảng 500 triệu" điền ba ô, còn `salvage_slot` trả đúng một giá trị.

    Thiếu hàm này thì bản vá "nhắc lại đúng số khách nói" chỉ chạy ở đường trích
    slot chính, còn đường CỨU SLOT (khách trả lời đúng câu hỏi ngân sách bot vừa
    đặt — tức ca phổ biến nhất) vẫn ghi trần đã nới. Đó chính là ca Sếp gặp
    2026-08-25 và là lý do bản vá đầu tiên không ăn trên prod.
    """

    return parse_budget_range(user_message).stated_vnd
