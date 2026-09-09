"""[A3-2] Bộ slot bắt buộc, luật chọn slot kế tiếp và chế độ truy xuất — thuần, không I/O.

Trả TỐI ĐA một slot. Hai nguyên tắc: (a) đi theo thứ tự cây A3-1, slot đầu tiên
chưa có giá trị là slot cần hỏi; (b) slot có giá trị `None` tính là CHƯA trả lời
— `None` là "khách chưa nói", khác `False`/`0` là "khách đã nói".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from src.agents.domain.slot_tree import (
    FIRST_SLOT,
    HARD_FILTER_SLOTS,
    REFINEMENT_SLOTS,
    slot_sequence,
)
from src.agents.domain.values import SlotName, SlotValue, VehicleType


class RetrievalMode(StrEnum):
    """Ba chế độ truy xuất thay cho cổng nhị phân `do_retrieve`."""

    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"


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


def _all_slots(vehicle_type: VehicleType | None) -> tuple[SlotName, ...]:
    """Tất cả slot của nhánh, hoặc chỉ `FIRST_SLOT` nếu chưa biết nhánh."""

    if vehicle_type is None:
        return (FIRST_SLOT,)
    return HARD_FILTER_SLOTS[vehicle_type] + REFINEMENT_SLOTS[vehicle_type]


def missing_all_slots(
    vehicle_type: VehicleType | None, known_slots: Mapping[SlotName, SlotValue]
) -> tuple[SlotName, ...]:
    """Trả mọi slot còn thiếu của nhánh, theo thứ tự ưu tiên."""

    return tuple(slot for slot in _all_slots(vehicle_type) if not _is_answered(known_slots, slot))


def decide_retrieval_mode(vehicle_type: VehicleType | None, known_slots: Mapping[SlotName, SlotValue]) -> RetrievalMode:
    """Quyết định chế độ truy xuất dựa trên số lượng slot định lượng đã có."""

    has_any_hard_filter = any(
        s in known_slots for s in (SlotName.BUDGET_MAX_VND, SlotName.VEHICLE_TYPE, SlotName.PASSENGER_COUNT)
    )
    all_slots = _all_slots(vehicle_type)
    has_all_required = all(_is_answered(known_slots, slot) for slot in all_slots)

    if has_all_required:
        return RetrievalMode.FULL
    if has_any_hard_filter:
        return RetrievalMode.PARTIAL
    return RetrievalMode.NONE


def _entropy(values: Sequence[SlotValue]) -> float:
    """Entropy tần suất đơn giản; dùng để chọn slot phân nhánh tốt nhất."""

    from math import log

    total = len(values)
    if total < 2:
        return 0.0
    counts: dict[object, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * log(p)
    return entropy


def next_best_question(
    vehicle_type: VehicleType | None,
    known_slots: Mapping[SlotName, SlotValue],
    candidate_values: Mapping[SlotName, Sequence[SlotValue]] | None = None,
) -> SlotName | None:
    """Chọn slot kế tiếp có khả năng phân nhánh mạnh nhất trên candidates.

    Khi chưa có candidates, trả slot đầu tiên còn thiếu theo thứ tự cây.
    """

    missing = missing_all_slots(vehicle_type, known_slots)
    if not missing:
        return None
    if candidate_values:
        best_slot: SlotName | None = None
        best_entropy = -1.0
        for slot in missing:
            values = candidate_values.get(slot)
            if not values:
                continue
            entropy = _entropy(values)
            if entropy > best_entropy:
                best_entropy = entropy
                best_slot = slot
        if best_slot is not None:
            return best_slot
    return missing[0]
