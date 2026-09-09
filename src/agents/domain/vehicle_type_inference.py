"""Suy loại xe từ known_slots khi khách chưa nói loại xe (T3)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from src.agents.domain.slot_mapping import DELIVERY_PURPOSE_KEYWORDS
from src.agents.domain.values import SlotName, SlotValue, VehicleType

#: Ngân sách tối đa coi là xe máy (biên `<`).
MOTORBIKE_BUDGET_CEILING_VND = Decimal("100_000_000")
#: Ô tô rẻ nhất trong catalog (T1 — từ DB: min CAR 188tr).
CAR_MIN_PRICE_VND = Decimal("188_000_000")


def _int_or_none(value: SlotValue) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _budget(value: SlotValue) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    return None


def _is_delivery(purpose: SlotValue) -> bool:
    if not isinstance(purpose, str):
        return False
    lowered = purpose.casefold()
    return any(keyword in lowered for keyword in DELIVERY_PURPOSE_KEYWORDS)


def infer_vehicle_type(
    known_slots: Mapping[SlotName, SlotValue],
) -> tuple[VehicleType | None, bool]:
    """Suy loại xe; trả `(None, False)` khi không đủ tín hiệu hoặc xung đột.

    `inferred=True` nghĩa là đủ căn cứ để nêu lại loại xe ở câu mở lượt 2.
    """

    passenger_count = _int_or_none(known_slots.get(SlotName.PASSENGER_COUNT))
    budget = _budget(known_slots.get(SlotName.BUDGET_MAX_VND))
    purpose = known_slots.get(SlotName.PURPOSE)
    delivery = _is_delivery(purpose)

    has_budget_for_bike = budget is not None and budget < MOTORBIKE_BUDGET_CEILING_VND
    has_budget_for_car = budget is not None and budget >= CAR_MIN_PRICE_VND

    car_signal = (passenger_count is not None and passenger_count >= 3) or has_budget_for_car
    bike_signal = delivery or (passenger_count in (1, 2) and has_budget_for_bike)

    # Xung đột rõ: khách cần 3 chỗ (ô tô) nhưng ngân sách không đủ mua ô tô.
    if passenger_count is not None and passenger_count >= 3 and budget is not None and not has_budget_for_car:
        return None, False

    if car_signal and bike_signal:
        return None, False
    if car_signal:
        return VehicleType.CAR, True
    if bike_signal:
        return VehicleType.ELECTRIC_MOTORBIKE, True
    return None, False
