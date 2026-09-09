"""[A7-5] Lượt này mang yêu cầu mới, hay chỉ là một tiếng "ok" cho báo giá vừa gửi.

Sinh ra để chặn một kiểu mất ngữ cảnh: khách đọc báo giá xong nói "ok xe có vẻ
được đấy", hệ thống coi đó là một lượt như mọi lượt khác và chạy lại toàn bộ
pipeline đánh giá. Lượt đó không mang thông tin gì nên mọi cờ trong
`QuoteEvaluation` đều `None`, mà `None` theo default-deny là RỦI RO — nên một
lời khen lại bị đẩy sang tư vấn viên duyệt, hoặc bị hỏi lại slot từ đầu.

Cách phân loại là RULE-BASED và KHÔNG tốn thêm một lần gọi LLM: bằng chứng mạnh
nhất cho "không có thông tin mới" đã nằm sẵn trong state — form trước và sau khi
trích slot của chính lượt này. Giống hệt lý do `routing._turn_added_a_slot` đọc
slot thay vì đếm số lượt.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class TurnType(StrEnum):
    """Hai kết cục, và mặc định an toàn là `NEW_REQUEST`."""

    #: Có thông tin/yêu cầu mới → đánh giá lại đầy đủ như thiết kế A7-4.
    NEW_REQUEST = "new_request"
    #: Chỉ xác nhận/phản hồi báo giá vừa gửi → tái dùng đánh giá cũ.
    ACKNOWLEDGMENT = "acknowledgment"


# [GIẢ ĐỊNH] Whitelist tối thiểu, gom từ cách nói xác nhận phổ biến. Cần bổ sung
# theo log hội thoại thật khi phát hiện biến thể mới. Cố ý KHÔNG dùng LLM: một
# lần gọi LLM cho câu "ok" là đắt hơn cả việc trả lời nó.
ACK_PATTERNS: Final[tuple[str, ...]] = (
    "ok",
    "oke",
    "okay",
    "okie",
    "được đấy",
    "được rồi",
    "được ạ",
    "nghe ổn",
    "ổn đấy",
    "ừm được",
    "vậy đi",
    "chốt",
    "đồng ý",
    "hay đấy",
    "tốt rồi",
    "cảm ơn",
    "thanks",
)

# [GIẢ ĐỊNH] Câu rất ngắn mà KHÔNG sinh ra thông tin mới cũng coi là xác nhận, để
# bao các biến thể ngoài whitelist. Ngưỡng 15 ký tự là phỏng đoán, cần chỉnh theo
# log thật.
SHORT_TURN_MAX_CHARS: Final[int] = 15

# Dấu hiệu câu HỎI: câu ngắn mà là câu hỏi thì không phải xác nhận, dù nó không
# lấp được slot nào. "giá sao?" chỉ 8 ký tự nhưng là một yêu cầu thật, và trả lời
# nó bằng "anh/chị muốn đặt lịch lái thử không" là lạc đề.
_QUESTION_MARKERS: Final[tuple[str, ...]] = (
    "?",
    "sao",
    "bao nhiêu",
    "thế nào",
    "gì",
    "nào",
    "không",
    "chưa",
)

# [GIẢ ĐỊNH] Động từ/cụm nêu nhu cầu. Cần bổ sung theo log thật, cùng lý do với
# `ACK_PATTERNS`. Ưu tiên bắt nhầm sang "yêu cầu mới" — nhầm chiều đó chỉ tốn một
# lần đánh giá thừa, nhầm chiều kia là nuốt mất yêu cầu của khách.
_REQUEST_MARKERS: Final[tuple[str, ...]] = (
    "muốn",
    "cần",
    "tìm",
    "cho em",
    "cho tôi",
    "cho mình",
    "thêm",
    "đổi",
    "so sánh",
    "tư vấn",
    "xem",
    "gửi",
    "đặt",
    "hỏi",
    "còn",
)


def classify_turn(
    *,
    form_before: Mapping[str, object] | None,
    form_after: Mapping[str, object] | None,
    user_message: str,
) -> TurnType:
    """Phân loại một lượt từ state trước/sau và câu khách vừa nói.

    Thứ tự kiểm tra là cố ý, và có một chỗ CỐ Ý LỆCH khỏi thiết kế ban đầu:
    delta của form KHÔNG được xét trước một câu xác nhận tường minh.

    Lý do đo được trên hệ thống thật: bước trích slot bằng LLM ghi ra slot mà
    khách chưa từng nói. "ok xe có vẻ được đấy" làm nó ghi `vehicle_type=CAR`
    (vì có chữ "xe"), còn "được đấy" làm nó ghi thẳng `passenger_count=5` — trong
    câu không có con số nào. Nếu tin vào `form_before != form_after`, đúng hai
    câu xác nhận điển hình nhất đều bị đọc thành yêu cầu mới, tức là bug ban đầu
    vẫn còn nguyên. Delta form chỉ đáng tin khi câu khách nói KHÔNG phải một lời
    xác nhận tường minh, nên nó tụt xuống sau các dấu hiệu đọc thẳng từ lời khách.

    Delta form vẫn xét TRƯỚC độ dài câu, đúng yêu cầu: "7 chỗ" ngắn nhưng lấp
    được slot, coi nó là xác nhận sẽ nuốt mất thông tin khách vừa cho.
    """

    normalized = " ".join((user_message or "").split()).casefold()
    if not normalized:
        # Lượt rỗng không xác nhận điều gì cả; để pipeline thường xử lý.
        return TurnType.NEW_REQUEST
    if _asks_something(normalized) or _requests_something(normalized) or _carries_data(normalized):
        return TurnType.NEW_REQUEST
    if any(pattern in normalized for pattern in ACK_PATTERNS):
        return TurnType.ACKNOWLEDGMENT
    if dict(form_before or {}) != dict(form_after or {}):
        return TurnType.NEW_REQUEST
    if len(normalized) <= SHORT_TURN_MAX_CHARS:
        return TurnType.ACKNOWLEDGMENT
    # Không chắc thì đánh giá lại đầy đủ — cùng chiều an toàn với A7-4: nhầm sang
    # "đánh giá lại" chỉ tốn công, nhầm sang "bỏ qua đánh giá" là thả lọt rủi ro.
    return TurnType.NEW_REQUEST


def _asks_something(normalized: str) -> bool:
    """Câu có dấu hỏi hoặc từ để hỏi — chưa được coi là lời xác nhận."""

    return any(marker in normalized for marker in _QUESTION_MARKERS)


def _requests_something(normalized: str) -> bool:
    """Có động từ nêu nhu cầu → là yêu cầu, dù đứng cạnh một tiếng "ok".

    Đây là thứ tách "ok" khỏi "ok em muốn xe chở được nhiều đồ": cả hai đều khớp
    whitelist xác nhận, chỉ câu sau mang một yêu cầu thật.
    """

    return any(marker in normalized for marker in _REQUEST_MARKERS)


def _carries_data(normalized: str) -> bool:
    """Có chữ số → khách đang nêu một con số (chỗ ngồi, ngân sách, quãng đường).

    Dấu hiệu này đọc thẳng từ lời khách nên không bị bước trích slot làm nhiễu,
    khác hẳn delta form. Nhờ nó "ok 7 chỗ nhé" vẫn là yêu cầu mới.
    """

    return any(character.isdigit() for character in normalized)


__all__ = [
    "ACK_PATTERNS",
    "SHORT_TURN_MAX_CHARS",
    "TurnType",
    "classify_turn",
]
