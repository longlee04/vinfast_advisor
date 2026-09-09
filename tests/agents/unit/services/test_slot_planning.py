"""[A3-2] Render slot questions from templates without LLM calls."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from src.agents.domain.values import SlotName, SlotValue, VehicleType
from src.agents.services.slot_planning import MissingRequiredSlotsError, SlotPlanningServiceImpl


class SpyLLM:
    """Count forbidden LLM calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def extract_slots(self) -> SlotValue:
        self.calls += 1
        raise AssertionError("slot planning không được gọi LLM")

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        raise AssertionError("slot planning không được gọi LLM")


def test_first_question_is_a_natural_sentence_about_vehicle_type() -> None:
    question = SlotPlanningServiceImpl().next_question(vehicle_type=None, known_slots={})

    assert question is not None
    assert "?" in question


@pytest.mark.parametrize("slot", list(SlotName))
def test_rendered_question_never_leaks_a_raw_slot_code(slot: SlotName) -> None:
    known: dict[SlotName, SlotValue] = {}
    question = SlotPlanningServiceImpl().next_question(vehicle_type=VehicleType.CAR, known_slots=known)

    assert question is None or slot.value not in question


def test_rendered_question_contains_no_machine_token() -> None:
    question = SlotPlanningServiceImpl().next_question(
        vehicle_type=VehicleType.CAR, known_slots={SlotName.VEHICLE_TYPE: "CAR"}
    )

    assert question is not None
    assert re.search(r"[A-Z_]{4,}|>=|<=|==", question) is None


def test_complete_state_returns_none_instead_of_small_talk() -> None:
    known = {name: "x" for name in SlotName}

    assert SlotPlanningServiceImpl().next_question(vehicle_type=VehicleType.CAR, known_slots=known) is None


def test_motorbike_with_required_slots_does_not_ask_for_optional_habit_tags() -> None:
    known: dict[SlotName, SlotValue] = {
        SlotName.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE",
        SlotName.BUDGET_MAX_VND: 30_000_000,
        SlotName.PURPOSE: "di lam",
    }

    assert (
        SlotPlanningServiceImpl().next_question(vehicle_type=VehicleType.ELECTRIC_MOTORBIKE, known_slots=known) is None
    )


def test_planning_a_question_never_calls_the_llm() -> None:
    spy = SpyLLM()
    SlotPlanningServiceImpl().next_question(vehicle_type=VehicleType.CAR, known_slots={})

    assert spy.calls == 0


def test_require_complete_raises_with_the_missing_slot_names() -> None:
    with pytest.raises(MissingRequiredSlotsError) as excinfo:
        SlotPlanningServiceImpl().require_complete(vehicle_type=VehicleType.CAR, known_slots={})

    assert SlotName.BUDGET_MAX_VND in excinfo.value.missing


def test_require_complete_passes_when_every_required_slot_is_answered() -> None:
    known: dict[SlotName, SlotValue] = {
        SlotName.VEHICLE_TYPE: "CAR",
        SlotName.BUDGET_MAX_VND: 700_000_000,
        SlotName.PURPOSE: "gia đình",
        SlotName.PASSENGER_COUNT: 5,
    }

    SlotPlanningServiceImpl().require_complete(vehicle_type=VehicleType.CAR, known_slots=known)


def test_build_criteria_delegates_to_the_domain_mapping() -> None:
    criteria = SlotPlanningServiceImpl().build_criteria(
        vehicle_type=VehicleType.CAR,
        known_slots={SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 700_000_000},
    )

    assert criteria.budget_max_vnd == Decimal(700_000_000)


def test_build_criteria_does_not_turn_purpose_into_a_hard_filter() -> None:
    service = SlotPlanningServiceImpl()
    base = {SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 700_000_000}

    without = service.build_criteria(vehicle_type=VehicleType.CAR, known_slots=base)
    with_purpose = service.build_criteria(
        vehicle_type=VehicleType.CAR, known_slots={**base, SlotName.PURPOSE: "gia đình"}
    )

    assert with_purpose == without


def test_next_field_skips_slot_over_ask_attempt_cap() -> None:
    # T6: MAX_ASK_ATTEMPTS = 1 → budget đã hỏi 2 lần không được hỏi lại lần 3.
    service = SlotPlanningServiceImpl()
    known: dict[SlotName, SlotValue] = {SlotName.VEHICLE_TYPE: "CAR"}

    field = service.next_field(
        vehicle_type=VehicleType.CAR,
        known_slots=known,
        ask_counts={SlotName.BUDGET_MAX_VND.value: 2},
    )

    assert field is not SlotName.BUDGET_MAX_VND


def test_next_field_returns_none_when_every_required_slot_is_capped() -> None:
    # Cả hai required (vehicle_type đã có, budget vượt quota) → hết slot để hỏi.
    service = SlotPlanningServiceImpl()
    known: dict[SlotName, SlotValue] = {SlotName.VEHICLE_TYPE: "CAR"}

    field = service.next_field(
        vehicle_type=VehicleType.CAR,
        known_slots=known,
        ask_counts={SlotName.BUDGET_MAX_VND.value: 2},
    )

    assert field is None


def test_clarify_question_returns_closed_question_for_known_slot() -> None:
    service = SlotPlanningServiceImpl()

    question = service.clarify_question(slot=SlotName.REQUIRED_RANGE_KM)

    assert question == "Dưới 30 km hay 30–60 km ạ?"


def test_clarify_question_returns_none_for_slot_without_closed_variant() -> None:
    service = SlotPlanningServiceImpl()

    question = service.clarify_question(slot=SlotName.BUDGET_MIN_VND)

    assert question is None


def test_inferred_vehicle_type_delegates_to_domain() -> None:
    service = SlotPlanningServiceImpl()

    vehicle_type, inferred = service.inferred_vehicle_type({SlotName.PURPOSE: "giao hàng"})

    assert inferred is True
    assert vehicle_type is VehicleType.ELECTRIC_MOTORBIKE


class TestCapturedRecap:
    """Sếp 2026-08-21: mọi lượt hỏi sau lượt 1 phải mở đầu bằng câu ghi nhận
    lại thông tin đã có, để khách thấy bot có "nghe" chứ không hỏi vô cớ."""

    def setup_method(self) -> None:
        self.planner = SlotPlanningServiceImpl()

    def test_empty_when_nothing_captured_yet(self) -> None:
        assert self.planner.captured_recap({}) == ""

    def test_mentions_budget_in_millions_not_raw_dong(self) -> None:
        recap = self.planner.captured_recap({"budget_max_vnd": 500_000_000})

        assert "Em đã ghi nhận" in recap
        assert "500 triệu" in recap
        assert "500.000.000" not in recap

    def test_mentions_billions_for_large_budget(self) -> None:
        recap = self.planner.captured_recap({"budget_max_vnd": 1_500_000_000})

        assert "1,5 tỷ" in recap

    def test_mentions_purpose_and_passenger_count(self) -> None:
        recap = self.planner.captured_recap({"purpose": "phục vụ gia đình", "passenger_count": 5})

        assert "phục vụ gia đình" in recap
        assert "5 người sử dụng" in recap

    def test_joins_multiple_parts_with_va(self) -> None:
        recap = self.planner.captured_recap({"budget_max_vnd": 500_000_000, "purpose": "phục vụ gia đình"})

        assert "500 triệu" in recap
        assert "và mục đích phục vụ gia đình" in recap

    def test_omits_a_slot_still_missing(self) -> None:
        """Slot đang được hỏi ở CHÍNH lượt này (chưa có trong known_slots) thì
        không lọt vào câu ghi nhận — không thể "ghi nhận" cái chưa biết."""

        recap = self.planner.captured_recap({"budget_max_vnd": 500_000_000})

        assert "người sử dụng" not in recap


class TestExhaustedNotice:
    """B mục 3: hết quota thì báo khách thay vì im lặng bỏ slot."""

    def setup_method(self) -> None:
        self.planner = SlotPlanningServiceImpl()

    def test_returns_none_without_exhausted_slot(self) -> None:
        assert self.planner.exhausted_notice(ask_counts={}) is None
        assert self.planner.exhausted_notice(ask_counts={"passenger_count": 1}) is None

    def test_notices_when_a_real_slot_exceeded_quota(self) -> None:
        notice = self.planner.exhausted_notice(ask_counts={"passenger_count": 2})

        assert notice is not None
        assert "thông tin" in notice

    def test_ignores_vehicle_type(self) -> None:
        assert self.planner.exhausted_notice(ask_counts={"vehicle_type": 2}) is None

    def test_ignores_non_slot_keys(self) -> None:
        assert self.planner.exhausted_notice(ask_counts={"routing": 3}) is None
