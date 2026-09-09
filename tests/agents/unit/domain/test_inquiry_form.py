"""Mục 5 prompt multi-slot: schema form, merge, và chọn field kế tiếp."""

from __future__ import annotations

import pytest

from src.agents.domain.budget_parsing import NO_BUDGET_LIMIT_VND
from src.agents.domain.inquiry_form import (
    SlotAnswer,
    VehicleInquiryForm,
    get_next_missing_field,
)
from src.agents.domain.values import DECLINED_SLOT_VALUE, VehicleType


def test_multi_slot_in_one_sentence_fills_every_field_it_mentions() -> None:
    """ "xe điện 5 chỗ tầm 700 triệu" → 3 field cùng lúc trong 1 lượt."""

    form = VehicleInquiryForm.from_slots({"vehicle_type": "CAR", "passenger_count": 5, "budget_max_vnd": 700_000_000})

    assert form.vehicle_type is VehicleType.CAR
    assert form.passenger_count is not None and form.passenger_count.value == 5
    assert form.budget_max_vnd is not None and form.budget_max_vnd.value == 700_000_000


def test_single_slot_answer_never_erases_fields_from_earlier_turns() -> None:
    """Lượt sau chỉ nói 1 field: các field cũ phải còn nguyên.

    Thiếu luật này thì mỗi câu trả lời ngắn sẽ xoá sạch form và hội thoại quay
    về vạch xuất phát — đúng vòng lặp đang gặp trên production.
    """

    current = VehicleInquiryForm.from_slots({"vehicle_type": "CAR", "passenger_count": 5})
    updates = VehicleInquiryForm.from_slots({"budget_max_vnd": 700_000_000})

    merged = current.merge(updates)

    assert merged.vehicle_type is VehicleType.CAR
    assert merged.passenger_count is not None and merged.passenger_count.value == 5
    assert merged.budget_max_vnd is not None and merged.budget_max_vnd.value == 700_000_000


def test_unknown_answer_does_not_overwrite_a_known_field() -> None:
    current = VehicleInquiryForm.from_slots({"passenger_count": 5})
    updates = VehicleInquiryForm(passenger_count=SlotAnswer(kind="unknown"))

    merged = current.merge(updates)

    assert merged.passenger_count is not None and merged.passenger_count.value == 5


def test_open_ended_budget_is_answered_and_moves_to_the_next_field() -> None:
    """ "tiền không thành vấn đề" → `kind="open"`, KHÔNG hỏi lại ngân sách."""

    form = VehicleInquiryForm.from_slots(
        {
            "vehicle_type": "CAR",
            "passenger_count": 5,
            "purpose": "đi làm",
            "budget_max_vnd": NO_BUDGET_LIMIT_VND,
        }
    )

    assert form.budget_max_vnd is not None
    assert form.budget_max_vnd.kind == "open"
    assert form.budget_max_vnd.is_answered
    assert get_next_missing_field(form) != "budget_max_vnd"


def test_declined_slot_reads_back_as_open_not_as_missing() -> None:
    form = VehicleInquiryForm.from_slots({"vehicle_type": "CAR", "purpose": DECLINED_SLOT_VALUE})

    assert get_next_missing_field(form) != "purpose"


def test_next_missing_field_starts_at_vehicle_type_on_an_empty_form() -> None:
    assert get_next_missing_field(VehicleInquiryForm()) == "vehicle_type"


@pytest.mark.parametrize(
    "slots",
    [
        {"vehicle_type": "CAR", "passenger_count": 4, "budget_max_vnd": 700_000_000, "purpose": "đi làm"},
        {"vehicle_type": "ELECTRIC_MOTORBIKE", "budget_max_vnd": 20_000_000, "purpose": "đi học"},
    ],
)
def test_round_trip_through_slots_keeps_downstream_shape(slots: dict[str, object]) -> None:
    """`to_slots()` phải trả về đúng hình dạng repository/Lớp 1 đang đọc."""

    restored = VehicleInquiryForm.from_slots(slots).to_slots()

    assert restored == slots
