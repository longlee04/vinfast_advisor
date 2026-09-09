"""[A3-3] Slot -> cot (muc 7.0 schema). Preference khong duoc thanh hard filter."""

from __future__ import annotations

from decimal import Decimal

from src.agents.domain.slot_mapping import preference_weights, purpose_bucket_for, to_filter_criteria
from src.agents.domain.values import PurposeBucket, SlotName, VehicleType

_BASE_CAR = {
    SlotName.VEHICLE_TYPE: "CAR",
    SlotName.BUDGET_MAX_VND: 700_000_000,
    SlotName.PASSENGER_COUNT: 7,
}


def test_family_purpose_does_not_add_any_hard_filter() -> None:
    without = to_filter_criteria(VehicleType.CAR, _BASE_CAR)
    with_purpose = to_filter_criteria(VehicleType.CAR, {**_BASE_CAR, SlotName.PURPOSE: "gia đình"})

    assert with_purpose == without


def test_family_purpose_only_changes_the_ranking_weights() -> None:
    weights = preference_weights({**_BASE_CAR, SlotName.PURPOSE: "gia đình"})

    assert weights and all(value > 0 for value in weights.values())


def test_habit_need_tags_never_add_a_hard_filter() -> None:
    without = to_filter_criteria(VehicleType.CAR, _BASE_CAR)
    with_habit = to_filter_criteria(VehicleType.CAR, {**_BASE_CAR, SlotName.HABIT_NEED_TAGS: ["URBAN_TRAFFIC"]})

    assert with_habit == without


def test_habit_need_tags_are_present_in_the_ranking_weights() -> None:
    weights = preference_weights({SlotName.HABIT_NEED_TAGS: ["URBAN_TRAFFIC"]})

    assert "URBAN_TRAFFIC" in weights


def test_delivery_purpose_makes_max_load_a_hard_filter() -> None:
    criteria = to_filter_criteria(
        VehicleType.ELECTRIC_MOTORBIKE,
        {
            SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE",
            SlotName.PURPOSE: "giao hàng",
            SlotName.MAX_LOAD_KG: 80,
        },
    )

    assert criteria.required_load_kg == 80


def test_non_delivery_purpose_ignores_max_load_even_when_present() -> None:
    criteria = to_filter_criteria(
        VehicleType.ELECTRIC_MOTORBIKE,
        {
            SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE",
            SlotName.PURPOSE: "đi làm",
            SlotName.MAX_LOAD_KG: 80,
        },
    )

    assert criteria.required_load_kg is None


def test_persisted_delivery_purpose_bucket_makes_max_load_a_hard_filter_without_keyword() -> None:
    """Final whole-branch review (2026-08-22): `_is_delivery` là nơi DUY NHẤT
    phân loại nhóm mục đích là hard filter (không chỉ ranking), nên phải ưu
    tiên slot LLM đã đóng gói (`PURPOSE_BUCKET`) qua `purpose_bucket_for`,
    không được chỉ khớp keyword trên `PURPOSE` thô — khách nói cách khác,
    không có từ khoá giao hàng nào, nhưng LLM đã suy đúng là giao hàng."""

    criteria = to_filter_criteria(
        VehicleType.ELECTRIC_MOTORBIKE,
        {
            SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE",
            SlotName.PURPOSE: "tôi cần xe chở đồ ăn cho quán",
            SlotName.PURPOSE_BUCKET: "delivery",
            SlotName.MAX_LOAD_KG: 80,
        },
    )

    assert criteria.required_load_kg == 80


def test_car_slots_map_to_budget_seat_and_range_columns() -> None:
    criteria = to_filter_criteria(VehicleType.CAR, {**_BASE_CAR, SlotName.REQUIRED_RANGE_KM: 300})

    assert criteria.budget_max_vnd == Decimal(700_000_000)
    assert criteria.passenger_count == 7
    assert criteria.required_range_km == 300


def test_passenger_count_from_a_motorbike_state_is_dropped() -> None:
    criteria = to_filter_criteria(
        VehicleType.ELECTRIC_MOTORBIKE,
        {SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE", SlotName.PASSENGER_COUNT: 7},
    )

    assert criteria.passenger_count is None


def test_empty_state_produces_criteria_without_any_filter() -> None:
    criteria = to_filter_criteria(VehicleType.CAR, {})

    assert criteria.budget_max_vnd is None
    assert criteria.passenger_count is None
    assert criteria.required_range_km is None
    assert criteria.required_load_kg is None


def test_purpose_bucket_for_prefers_persisted_slot_over_keyword_guess() -> None:
    known = {SlotName.PURPOSE: "đi chợ", SlotName.PURPOSE_BUCKET: "work"}
    assert purpose_bucket_for(known) is PurposeBucket.WORK


def test_purpose_bucket_for_falls_back_to_keyword_when_no_persisted_slot() -> None:
    known = {SlotName.PURPOSE: "chở gia đình đi chơi"}
    assert purpose_bucket_for(known) is PurposeBucket.FAMILY
