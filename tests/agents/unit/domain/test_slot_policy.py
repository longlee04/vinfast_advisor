"""[A3-2] `next_slot` trả tối đa MỘT câu; đủ slot bắt buộc thì trả None."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations

import pytest

from src.agents.domain.slot_policy import (
    REQUIRED_SLOTS,
    missing_required,
    next_slot,
)
from src.agents.domain.slot_tree import SLOT_ORDER
from src.agents.domain.values import SlotName, VehicleType

_CAR_REQUIRED = {
    SlotName.VEHICLE_TYPE,
    SlotName.BUDGET_MAX_VND,
}
_MOTORBIKE_REQUIRED = {SlotName.VEHICLE_TYPE, SlotName.BUDGET_MAX_VND}


def test_required_slot_sets_match_the_spec() -> None:
    assert REQUIRED_SLOTS[VehicleType.CAR] == frozenset(_CAR_REQUIRED)
    assert REQUIRED_SLOTS[VehicleType.ELECTRIC_MOTORBIKE] == frozenset(_MOTORBIKE_REQUIRED)


def _all_states(vehicle_type: VehicleType) -> Iterator[dict[SlotName, str]]:
    slots = SLOT_ORDER[vehicle_type]
    for size in range(len(slots) + 1):
        for subset in combinations(slots, size):
            yield {name: "x" for name in subset}


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_every_valid_state_yields_at_most_one_slot(vehicle_type: VehicleType) -> None:
    for known in _all_states(vehicle_type):
        result = next_slot(vehicle_type, known)

        assert result is None or isinstance(result, SlotName)


def test_vehicle_type_already_known_is_never_asked_again() -> None:
    known = {SlotName.VEHICLE_TYPE: "CAR"}

    assert next_slot(VehicleType.CAR, known) is not SlotName.VEHICLE_TYPE


def test_vehicle_type_and_budget_are_enough_to_retrieve_a_price_first_list() -> None:
    known = {name: "x" for name in _CAR_REQUIRED}

    assert next_slot(VehicleType.CAR, known) is None


def test_fully_answered_state_returns_none() -> None:
    known = {name: "x" for name in SLOT_ORDER[VehicleType.CAR]}

    assert next_slot(VehicleType.CAR, known) is None


def test_unknown_vehicle_type_always_asks_vehicle_type() -> None:
    assert next_slot(None, {}) is SlotName.VEHICLE_TYPE


def test_missing_required_lists_only_required_gaps() -> None:
    known = {SlotName.VEHICLE_TYPE: "CAR", SlotName.HABIT_NEED_TAGS: ["URBAN_TRAFFIC"]}

    result = set(missing_required(VehicleType.CAR, known))

    assert result == _CAR_REQUIRED - {SlotName.VEHICLE_TYPE}


def test_none_valued_slot_counts_as_missing_not_as_answered() -> None:
    known = {SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: None}

    assert SlotName.BUDGET_MAX_VND in missing_required(VehicleType.CAR, known)
