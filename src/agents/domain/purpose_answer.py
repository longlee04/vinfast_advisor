"""Đọc TẤT ĐỊNH câu trả lời cho câu hỏi "mua xe để dùng vào mục đích gì".

BUG THẬT trên prod 2026-08-28 (phiên `456c34e1`): bot hỏi mục đích, khách đáp
*"đi làm thôi"*, bot **hỏi lại** đúng câu đó bằng lời khác, khách phải nói lần
hai là *"đi làm"* mới đi tiếp. Chữ "thôi" ở cuối là khác biệt duy nhất.

Nguyên nhân: `purpose` không nằm trong `DEFAULT_EXTRACTORS`, nên
`PendingSlotServiceImpl.can_resolve("purpose")` trả `False`, `chain._advisory_pending`
không mở bản ghi chờ, và lượt sau không còn dấu vết nào cho biết câu của khách
đang trả lời cái gì — trông cả vào LLM, LLM trượt là mất lượt.

Vì sao KHÔNG dùng thẳng `slot_salvage.salvage_slot(PURPOSE, ...)`
--------------------------------------------------------------
Nó nhận gần như MỌI chuỗi ngắn (chỉ loại câu hỏi và câu vô nghĩa). Cắm bộ đó vào
`extractors` là biến *"VF 5 giá bao nhiêu"* — gõ lúc câu hỏi mục đích còn treo —
thành mục đích của khách, và lượt hỏi giá chết theo. Đổi một lỗi hỏi lại hai lần
lấy một lỗi tệ hơn.

Nên bộ này HẸP: chỉ nhận câu thật sự nêu một mục đích, đo bằng chính bộ từ khoá
mà `slot_mapping.purpose_bucket` đang dùng để chấm điểm. Không thêm bảng từ thứ
hai — hai bảng cho một khái niệm sẽ lệch nhau ngay lần sửa sau.
"""

from __future__ import annotations

from typing import Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.slot_mapping import (
    DELIVERY_BUCKET_KEYWORDS,
    FAMILY_PURPOSE_KEYWORDS,
    LONG_TRIP_PURPOSE_KEYWORDS,
    SERVICE_PURPOSE_KEYWORDS,
    WORK_PURPOSE_KEYWORDS,
)

#: Trần độ dài, cùng tinh thần với `slot_salvage`: một đoạn văn dài không phải
#: câu trả lời cho một câu hỏi chọn mục đích.
_MAX_LENGTH: Final[int] = 120

_PURPOSE_KEYWORDS: Final[frozenset[str]] = frozenset(
    FAMILY_PURPOSE_KEYWORDS
    | WORK_PURPOSE_KEYWORDS
    | SERVICE_PURPOSE_KEYWORDS
    | DELIVERY_BUCKET_KEYWORDS
    | LONG_TRIP_PURPOSE_KEYWORDS
)

#: Câu MANG từ khoá mục đích nhưng là lời TỪ CHỐI, không phải câu trả lời.
_REFUSAL_MARKERS: Final[tuple[str, ...]] = ("thôi không", "thoi khong", "không cần", "khong can")


def purpose_from_answer(user_message: str, canonical: CanonicalText) -> str | None:
    """Nguyên văn mục đích khách vừa nói, hoặc `None` khi câu không nói mục đích.

    Trả NGUYÊN VĂN chứ không nắn về nhãn: `purpose_bucket` tự suy nhóm khi chấm
    điểm, còn câu gốc còn được dùng lại để dựng lời tư vấn.
    """

    cleaned = " ".join((user_message or "").split())
    if not cleaned or len(cleaned) > _MAX_LENGTH:
        return None
    folded = canonical.folded or cleaned.casefold()
    if any(marker in folded for marker in _REFUSAL_MARKERS):
        return None
    # Có CON SỐ ⇒ câu này khai nhiều slot cùng lúc (ngân sách, quãng đường, số
    # người), không phải câu trả lời riêng cho câu hỏi mục đích.
    #
    # REGRESSION THẬT do chính bộ này sinh ra: bắt luôn `purpose` từ câu
    # *"nha 5 nguoi, ngan sach 800 trieu, … di lam moi ngay 30km"* khiến hồ sơ
    # đầy sớm và agent BỎ QUA câu hỏi tính năng — trái luật Sếp chốt 2026-08-21.
    #
    # Cứu ngữ cảnh là cho câu NGẮN TRƠ TRỌI ("đi làm thôi"). Câu khai đủ nhu cầu
    # đã có bộ trích trong graph lo, và nó lo tốt hơn vì thấy cả lượt.
    if any(ch.isdigit() for ch in cleaned):
        return None
    lowered = cleaned.casefold()
    if any(keyword in lowered or keyword in folded for keyword in _PURPOSE_KEYWORDS):
        return cleaned
    return None
