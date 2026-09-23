"""[A3-2] Bộ slot bắt buộc, luật chọn slot kế tiếp và chế độ truy xuất — thuần, không I/O.

Trả TỐI ĐA một slot. Hai nguyên tắc: (a) đi theo thứ tự cây A3-1, slot đầu tiên
chưa có giá trị là slot cần hỏi; (b) slot có giá trị `None` tính là CHƯA trả lời
— `None` là "khách chưa nói", khác `False`/`0` là "khách đã nói".
"""

from __future__ import annotations

from collections.abc import Mapping

from src.agents.domain.slot_tree import (
    FIRST_SLOT,
    slot_sequence,
)
from src.agents.domain.values import SlotName, SlotValue, VehicleType

REQUIRED_SLOTS: dict[VehicleType, frozenset[SlotName]] = {
    VehicleType.CAR: frozenset(
        {
            SlotName.VEHICLE_TYPE,
            SlotName.BUDGET_MAX_VND,
        }
    ),
    VehicleType.ELECTRIC_MOTORBIKE: frozenset({SlotName.VEHICLE_TYPE, SlotName.BUDGET_MAX_VND}),
}


def _is_answered(known_slots: Mapping[SlotName, SlotValue], slot: SlotName) -> bool:
    return slot in known_slots and known_slots[slot] is not None


def missing_required(
    vehicle_type: VehicleType | None, known_slots: Mapping[SlotName, SlotValue]
) -> tuple[SlotName, ...]:
    """Trả slot bắt buộc còn thiếu, theo thứ tự cây."""
    if vehicle_type is None:
        return (FIRST_SLOT,)
    required = REQUIRED_SLOTS[vehicle_type]
    return tuple(
        slot for slot in slot_sequence(vehicle_type) if slot in required and not _is_answered(known_slots, slot)
    )


def next_slot(vehicle_type: VehicleType | None, known_slots: Mapping[SlotName, SlotValue]) -> SlotName | None:
    """Trả slot kế tiếp cần hỏi, hoặc `None` khi cây đã đi hết."""
    required = None if vehicle_type is None else REQUIRED_SLOTS.get(vehicle_type)
    for slot in slot_sequence(vehicle_type):
        if (required is None or slot in required) and not _is_answered(known_slots, slot):
            return slot
    return None
