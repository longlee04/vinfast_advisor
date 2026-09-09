"""Bản ghi chờ cho bước "khách hỏi giá lăn bánh mà chưa nêu mẫu xe".

BUG THẬT trên prod 2026-08-28: *"tính giá lăn bánh"* trơ trọi trả về **ba xe
mới**. `classify_pricing_intent` nhận đúng `ON_ROAD_PRICE_LOOKUP`, nhưng không
có tên xe nên `reconcile_intents` bỏ `CATALOG_LOOKUP` và không nhánh nào nhận —
`route_intent` trả `{}`, `ask_or_retrieve` ép `ADVISORY`, và bảng điểm chạy lại.

Vì sao KHÔNG mượn intent `ON_ROAD_PRICE_LOOKUP` cho bước này
------------------------------------------------------------
`chain._run_pending_tool` rẽ **theo intent**:

    if service is None or resolution.intent != "ON_ROAD_PRICE_LOOKUP":
        return _PendingToolOutcome()
    variant, province = form.get("vehicle_variant"), form.get("province")

Mượn intent cũ thì lượt sau khách gõ *"VF 5"* rơi thẳng vào nhánh tính giá với
`vehicle_variant` và `province` đều rỗng → outcome trống → **lượt chết im
lặng**. Đúng họ lỗi đang phải dọn, nên bước này mang intent riêng.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from src.agents.domain.pending_slot import PendingSlotRequest

#: Intent RIÊNG cho bước hỏi mẫu xe. Xem docstring module về lý do.
ON_ROAD_VEHICLE_INTENT: Final[str] = "ON_ROAD_VEHICLE"
#: Slot đang chờ: tên mẫu xe cần tính giá lăn bánh.
ON_ROAD_VEHICLE_SLOT: Final[str] = "on_road_vehicle"


def pending_for_on_road_vehicle(*, user_message: str, asked_at: datetime) -> PendingSlotRequest:
    """Bản ghi chờ cho câu hỏi "anh/chị muốn tính giá lăn bánh mẫu nào".

    Giữ nguyên câu gốc: bước sau còn phải đọc lại nó để biết khách hỏi giá lăn
    bánh hay chi phí sử dụng, và lúc đó lượt hỏi mẫu đã trôi qua.
    """

    return PendingSlotRequest(
        intent=ON_ROAD_VEHICLE_INTENT,
        missing_slot=ON_ROAD_VEHICLE_SLOT,
        partial_form={"original_message": user_message},
        asked_at=asked_at,
    )
