from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

from src.agents.contracts import (
    Citation,
    NavigateCenter,
    NavigateShowroomView,
    NavigateView,
    QuickReplyView,
    RecommendedVehicleView,
    SpecGroup,
    TcoCardView,
    TcoComponentView,
    TcoRatesView,
    TestDriveCardView,
    TestDriveDayView,
    TestDriveOptionView,
    TestDriveShowroomView,
    TestDriveTimeView,
    TurnResult,
    VehicleDetailsView,
    VehicleFacts,
)
from src.agents.domain.bottleneck_signal import BottleneckDetected, BottleneckDetectionStatus
from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus
from src.agents.domain.customer_profile import Bottleneck
from src.agents.domain.next_step import NextStepAction, NextStepCta, NextStepOption, NextStepPanel
from src.agents.domain.turn_result_payload import MAX_PAYLOAD_BYTES, deserialize_turn_result, serialize_turn_result
from src.agents.domain.values import VehicleType


def _outcome() -> TurnOutcome:
    return TurnOutcome(uuid4(), uuid4(), 1, TurnOutcomeStatus.COMPLETED, answer="typed answer")


def test_round_trip_preserves_customer_visible_core_fields() -> None:
    result = TurnResult(
        session_id=str(uuid4()),
        answer="answer",
        pending_question="question",
        terminal_reason="reason",
        lookup_facts=[VehicleFacts(uuid4(), "VF 5", VehicleType.CAR, Decimal("555000000"), {"range": 300})],
        recommendations=[
            RecommendedVehicleView(uuid4(), 1, "VF 5", None, "555000000", "pitch", (Citation(1, uuid4(), "source"),))
        ],
        awaiting_review=True,
        review_id=uuid4(),
        turn_status="WAITING_REVIEW",
        conversation_state="ACTIVE",
    )

    outcome = TurnOutcome(
        uuid4(),
        uuid4(),
        1,
        TurnOutcomeStatus.COMPLETED,
        answer=result.answer,
        pending_question=result.pending_question,
        terminal_reason=result.terminal_reason,
        review_id=result.review_id,
    )
    restored = deserialize_turn_result(serialize_turn_result(result), outcome)

    assert restored == replace(result, session_id=str(outcome.conversation_id))


def test_round_trip_preserves_every_nested_customer_view() -> None:
    vehicle_id = uuid4()
    result = TurnResult(
        session_id=str(uuid4()),
        answer="answer",
        pending_question=None,
        options=[{"label": "yes", "value": "yes"}],
        test_drive_card=TestDriveCardView(
            "VF 5",
            (TestDriveShowroomView("s1", "Showroom", "Address", "1 km", 1.0, 2.0, 1.0),),
            (TestDriveDayView("2026-09-01", "Today", (TestDriveTimeView(datetime(2026, 9, 1), "09:00"),)),),
            (TestDriveOptionView("s1", datetime(2026, 9, 1), "token"),),
            "s1",
            "2026-09-01",
            str(vehicle_id),
            True,
        ),
        vehicle_details=VehicleDetailsView("VF 5", (SpecGroup("Specs", (("Range", "300 km"),)),)),
        next_step_panel=NextStepPanel(
            "Next", (NextStepOption(NextStepAction.COMPARE, "Compare", True),), NextStepCta("Book", "Book VF 5")
        ),
        navigate=NavigateView(
            "map",
            str(vehicle_id),
            "vf-5",
            "/vehicles/vf-5",
            "VF 5",
            NavigateCenter(1.0, 2.0),
            (NavigateShowroomView("s1", "Showroom", "Address", 1.0, 2.0, 1.0),),
            True,
        ),
        quick_replies=[QuickReplyView("Yes", "yes")],
        tco_card=TcoCardView(
            vehicle_id,
            "VF 5",
            "500",
            (TcoComponentView("energy", "Energy", "20", "operating"),),
            30.0,
            True,
            "HN",
            "north",
            "note",
            (),
            TcoRatesView("1", "2", "3", "4", "5", "6"),
        ),
        bottleneck_detection=BottleneckDetected(
            BottleneckDetectionStatus.DETECTED, Bottleneck.PRICE, "too costly", 0.8
        ),
        bottleneck_anchor_client_turn_id=uuid4(),
    )

    outcome = TurnOutcome(uuid4(), uuid4(), 1, TurnOutcomeStatus.COMPLETED, answer=result.answer)
    restored = deserialize_turn_result(serialize_turn_result(result), outcome)

    assert restored.session_id == str(outcome.conversation_id)
    assert restored.answer == result.answer
    assert restored.test_drive_card == result.test_drive_card
    assert restored.vehicle_details == result.vehicle_details
    assert restored.next_step_panel == result.next_step_panel
    assert restored.navigate == result.navigate
    assert restored.quick_replies == result.quick_replies
    assert restored.comparison == result.comparison
    assert restored.nearby_locations == result.nearby_locations
    assert restored.tco_card == result.tco_card
    assert restored.bottleneck_detection is None
    assert restored.bottleneck_anchor_client_turn_id is None


def test_unknown_and_missing_fields_are_ignored_with_typed_fallback() -> None:
    outcome = _outcome()
    restored = deserialize_turn_result({"version": 1, "fields": {"answer": "payload", "unknown": "ignore"}}, outcome)

    assert restored.answer == "payload"
    assert restored.session_id == str(outcome.conversation_id)
    assert restored.turn_status == "COMPLETED"


def test_malformed_payload_falls_back_to_typed_outcome() -> None:
    outcome = _outcome()

    restored = deserialize_turn_result({"version": 1, "fields": "bad"}, outcome)

    assert restored.answer == "typed answer"
    assert restored.session_id == str(outcome.conversation_id)


def test_oversized_payload_is_deterministically_truncated_to_limit() -> None:
    result = TurnResult(session_id=str(uuid4()), answer="x" * (MAX_PAYLOAD_BYTES * 2), pending_question=None)

    payload = serialize_turn_result(result)

    assert payload["payload_truncated"] is True
    assert (
        len(__import__("json").dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
        <= MAX_PAYLOAD_BYTES
    )
    assert payload == serialize_turn_result(result)


def test_oversized_core_list_is_truncated_to_limit() -> None:
    result = TurnResult(
        session_id=str(uuid4()),
        answer="answer",
        pending_question=None,
        lookup_facts=[VehicleFacts(uuid4(), "VF 5", VehicleType.CAR, None, {"blob": "x" * MAX_PAYLOAD_BYTES})],
    )

    payload = serialize_turn_result(result)

    assert payload["payload_truncated"] is True
    fields = cast(dict[str, object], payload["fields"])
    assert fields["lookup_facts"] == []
    assert (
        len(__import__("json").dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
        <= MAX_PAYLOAD_BYTES
    )


def test_fallback_survives_nested_malformed_items() -> None:
    """Phần tử hỏng lồng bên trong không được giết cả đường cứu.

    Trước đây `_fallback` giải mã cả danh sách trong một biểu thức: một phần tử
    sai kiểu là ném lỗi ngay tại nhánh đáng lẽ để cứu, và lượt đi ra bằng 500.
    """

    outcome = TurnOutcome(
        conversation_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        status=TurnOutcomeStatus.COMPLETED,
        answer="Dạ em gửi anh/chị thông tin ạ.",
        pending_question=None,
        terminal_reason=None,
        lookup_facts=[{"vehicle_id": "khong-phai-uuid"}, "hoan toan khong phai dict"],
        recommendations=["rac", {"display_name": 12345}],
        error_category=None,
        review_id=None,
        message_id=None,
        result_payload={"khong": "doc duoc"},
    )

    result = deserialize_turn_result(outcome.result_payload, outcome)

    assert result.answer == "Dạ em gửi anh/chị thông tin ạ."
    assert result.lookup_facts == []
    assert result.recommendations == []
