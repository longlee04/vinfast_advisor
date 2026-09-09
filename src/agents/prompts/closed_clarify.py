"""Câu hỏi đóng khi khách đã trả lời mơ hồ (T4).

Khác `QUESTION_VARIANTS` (biến thể câu MỞ — hỏi lại khi chưa rõ): đây là câu
ĐÓNG đưa sẵn khoảng/mốc cho khách chọn, dùng khi khách CÓ trả lời nhưng bộ trích
xuất không lấy được giá trị rõ ràng.

`RANGE_UNIT_CLARIFY` (T2 Lớp 3, design doc `docs/designs/luong-hoi-nhu-cau-
3-luot.md` mục "Quy đổi đơn vị quãng đường") là câu đóng riêng cho quãng đường
bị từ chối: giá trị vượt ngưỡng hợp lý một ngày hoặc tính theo chuyến → không
ghi slot, hỏi lại đúng đơn vị để khách chốt.
"""

from __future__ import annotations

from typing import Final

from src.agents.domain.range_normalizer import MAX_PLAUSIBLE_DAILY_KM
from src.agents.domain.values import SlotName
from src.agents.prompts.persona import CUSTOMER_ADDRESS

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

#: Lý do từ `normalize_range_km` → câu xác nhận đơn vị. Khoá là chuỗi lý do
#: (không phải `SlotName`) vì cùng một slot có nhiều cách bị từ chối, mỗi cách
#: cần một câu khác nhau.
RANGE_UNIT_CLARIFY: Final[dict[str, str]] = {
    "daily_km_above_ceiling": (
        f"Mỗi ngày {CUSTOMER_ADDRESS} chạy hơn {MAX_PLAUSIBLE_DAILY_KM} km ạ, hay đó là con số theo tuần?"
    ),
    "trip_period_needs_confirmation": f"Mỗi ngày {CUSTOMER_ADDRESS} đi khoảng bao nhiêu km ạ?",
}


def closed_clarify_question(slot: SlotName) -> str | None:
    """Trả câu đóng cho slot; `None` khi slot không có câu đóng (giữ câu mở)."""
    return CLOSED_CLARIFY.get(slot)


def range_unit_clarify_question(reason: str) -> str | None:
    """Câu xác nhận đơn vị quãng đường; `None` với lý do không biết."""
    return RANGE_UNIT_CLARIFY.get(reason)
