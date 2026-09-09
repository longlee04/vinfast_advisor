"""[A3-1] Cây slot là bảng tra cứu tường minh — LLM không quyết định hỏi gì tiếp."""

from __future__ import annotations

import pytest

from src.agents.domain.slot_tree import (
    FIRST_SLOT,
    SLOT_ORDER,
    is_applicable,
    slot_sequence,
)
from src.agents.domain.values import SlotName, VehicleType


def test_empty_state_asks_vehicle_type_first_not_budget() -> None:
    assert slot_sequence(None) == (SlotName.VEHICLE_TYPE,)
    assert FIRST_SLOT is SlotName.VEHICLE_TYPE


def test_motorbike_branch_never_contains_passenger_count() -> None:
    assert SlotName.PASSENGER_COUNT not in SLOT_ORDER[VehicleType.ELECTRIC_MOTORBIKE]


def test_motorbike_branch_never_asks_purpose_twice() -> None:
    sequence = SLOT_ORDER[VehicleType.ELECTRIC_MOTORBIKE]

    assert sequence.count(SlotName.PURPOSE) == 1


def test_car_branch_follows_documented_order() -> None:
    assert SLOT_ORDER[VehicleType.CAR] == (
        SlotName.VEHICLE_TYPE,
        SlotName.PASSENGER_COUNT,
        SlotName.REQUIRED_RANGE_KM,
        SlotName.HOME_CHARGING,
        SlotName.BUDGET_MAX_VND,
        SlotName.PURPOSE,
        SlotName.HABIT_NEED_TAGS,
    )


def test_habit_need_tags_is_the_last_open_slot_on_both_branches() -> None:
    for sequence in SLOT_ORDER.values():
        assert sequence[-1] is SlotName.HABIT_NEED_TAGS


def test_passenger_count_is_not_applicable_to_motorbike() -> None:
    assert is_applicable(VehicleType.ELECTRIC_MOTORBIKE, SlotName.PASSENGER_COUNT) is False


def test_max_load_kg_is_not_applicable_to_car() -> None:
    assert is_applicable(VehicleType.CAR, SlotName.MAX_LOAD_KG) is False


#: Slot hỏi được ngay khi CHƯA biết loại xe.
_TYPE_AGNOSTIC_WHEN_UNKNOWN = frozenset(
    {
        SlotName.VEHICLE_TYPE,
        SlotName.BUDGET_MAX_VND,
        SlotName.REQUIRED_RANGE_KM,
        SlotName.HOME_CHARGING,
    }
)

#: Không nằm trong `SLOT_ORDER` nên không bao giờ được HỎI, nhưng phải
#: `is_applicable` ở MỌI nhánh — nếu không `_drop_unsupported_slots` xoá ngay
#: sau khi trích được. `BUDGET_MIN_VND` đi kèm câu trả lời trần; `PURPOSE_BUCKET`
#: là kết quả LLM đóng gói của `purpose`; `BUDGET_STATED_VND` là con số khách nói
#: ra, giữ để nhắc lại đúng lời họ (Sếp 2026-08-25).
#: Slot không bao giờ nằm trong `SLOT_ORDER` nhưng phải sống sót qua
#: `_applicable_slots` ở MỌI nhánh — kể cả khi chưa biết loại xe.
#:
#: `REGISTRATION_PROVINCE` vào nhóm này 2026-08-26: tỉnh đăng ký không phụ thuộc
#: loại xe, và nó được suy từ vị trí trình duyệt ngay từ lượt đầu — trước cả khi
#: khách chọn ô tô hay xe máy. Không cho nó qua thì `_drop_unsupported_slots`
#: xoá nó TRONG IM LẶNG, đúng lỗi đã xảy ra với `BUDGET_STATED_VND`.
_NEVER_ASKED_ALWAYS_APPLICABLE = frozenset(
    {
        SlotName.BUDGET_MIN_VND,
        SlotName.PURPOSE_BUCKET,
        SlotName.BUDGET_STATED_VND,
        SlotName.REGISTRATION_PROVINCE,
    }
)


@pytest.mark.parametrize("slot", list(SlotName))
def test_unknown_vehicle_type_only_accepts_type_agnostic_opening_slots(
    slot: SlotName,
) -> None:
    """Chưa biết loại xe vẫn hỏi được ngân sách/km/sạc — chỉ PASSENGER_COUNT
    (và các slot đặc thù khác) phải chờ biết loại xe (T-skip-vehicle-type)."""

    if slot in _NEVER_ASKED_ALWAYS_APPLICABLE:
        assert is_applicable(None, slot) is True
        return
    assert is_applicable(None, slot) is (slot in _TYPE_AGNOSTIC_WHEN_UNKNOWN)


@pytest.mark.parametrize("vehicle_type", [None, *list(VehicleType)])
@pytest.mark.parametrize("slot", sorted(_NEVER_ASKED_ALWAYS_APPLICABLE, key=str))
def test_never_asked_slots_are_applicable_on_every_branch(vehicle_type, slot) -> None:
    """Không có luật này thì `_drop_unsupported_slots` xoá chúng ngay sau khi
    trích được, và một câu "từ 300 đến 700 triệu" lại chỉ còn cái trần."""

    assert is_applicable(vehicle_type, slot) is True


def test_never_asked_slots_are_never_their_own_question() -> None:
    """Hỏi riêng "sàn ngân sách của anh/chị" là một câu không ai muốn nghe."""

    for vehicle_type in VehicleType:
        for slot in _NEVER_ASKED_ALWAYS_APPLICABLE:
            assert slot not in slot_sequence(vehicle_type)
