"""Câu hỏi đóng khi khách đã trả lời mơ hồ (T4).

Khác `QUESTION_VARIANTS` (biến thể câu MỞ — hỏi lại khi chưa rõ): đây là câu
ĐÓNG đưa sẵn khoảng/mốc cho khách chọn, dùng khi khách CÓ trả lời nhưng bộ trích
xuất không lấy được giá trị rõ ràng.
"""

from __future__ import annotations

from typing import Final

from src.agents.domain.values import SlotName

CLOSED_CLARIFY: Final[dict[SlotName, str]] = {
    SlotName.REQUIRED_RANGE_KM: "Dưới 30 km hay 30–60 km ạ?",
    SlotName.HOME_CHARGING: "Nhà anh/chị có ổ cắm ở chỗ để xe không ạ?",
    SlotName.PASSENGER_COUNT: "Thường 4–5 người hay nhiều hơn ạ?",
    SlotName.BUDGET_MAX_VND: "Dưới 500 triệu hay trên 500 triệu ạ?",
    SlotName.VEHICLE_TYPE: "Ô tô điện hay xe máy điện ạ?",
    SlotName.PURPOSE: "Đi làm, giao hàng hay đi cá nhân ạ?",
    SlotName.MAX_LOAD_KG: "Dưới 50 kg hay trên 50 kg mỗi chuyến ạ?",
    SlotName.HABIT_NEED_TAGS: "Có cần tính năng đặc biệt nào như chống trộm hay không ạ?",
}


def closed_clarify_question(slot: SlotName) -> str | None:
    """Trả câu đóng cho slot; `None` khi slot không có câu đóng (giữ câu mở)."""
    return CLOSED_CLARIFY.get(slot)
