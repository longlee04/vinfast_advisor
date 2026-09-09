"""Đổi chuỗi thô ở `AgentState` sang value object của `domain/`.

`nodes/` bị cấm import `domain/` (mục 6.5b) nên state chỉ mang chuỗi. Việc đổi
chuỗi → enum phải nằm ở biên trong của `services/`, và phải **bỏ qua chuỗi lạ
thay vì raise**: LLM trả một khoá slot sai chính tả không được làm chết lượt
(A2-3, "không làm chết lượt").
"""

from __future__ import annotations

from collections.abc import Mapping

from src.agents.domain.values import SlotName, SlotValue, VehicleType


def coerce_slots(known_slots: Mapping[str, SlotValue]) -> dict[SlotName, SlotValue]:
    """Giữ lại đúng những khoá khớp `SlotName`; khoá lạ bị bỏ im lặng."""

    resolved: dict[SlotName, SlotValue] = {}
    for name, value in known_slots.items():
        try:
            resolved[SlotName(name)] = value
        except ValueError:
            continue
    return resolved


def encode_slots(known_slots: Mapping[SlotName, SlotValue]) -> dict[str, SlotValue]:
    """Chiều ngược lại — repository trả `SlotName`, state cần chuỗi."""

    return {name.value: value for name, value in known_slots.items()}


def coerce_vehicle_type(value: object) -> VehicleType | None:
    """`None` khi chưa biết hoặc khi chuỗi không khớp loại phương tiện nào."""

    if isinstance(value, VehicleType):
        return value
    if isinstance(value, str):
        try:
            return VehicleType(value)
        except ValueError:
            return None
    return None
