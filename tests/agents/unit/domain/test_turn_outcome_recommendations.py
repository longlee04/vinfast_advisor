"""TurnOutcome phải mang payload `recommendations` để replay trả đủ card."""

from uuid import uuid4

import pytest

from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus


def _recommendation() -> dict[str, object]:
    return {
        "vehicle_id": "20000000-0000-0000-0000-000000000101",
        "rank": 1,
        "display_name": "VF 8",
        "image_url": None,
        "starting_price_vnd": "1090000000",
        "pitch": "VF 8 đi 399 km [1].",
        "citations": [{"index": 1}],
    }


def test_turn_outcome_carries_recommendations_payload() -> None:
    recommendation = _recommendation()
    outcome = TurnOutcome(
        conversation_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        status=TurnOutcomeStatus.COMPLETED,
        answer="VF 8 đi 399 km [1].",
        recommendations=(recommendation,),
    )

    assert outcome.recommendations == (recommendation,)


def test_recommendations_do_not_count_as_customer_visible() -> None:
    """`recommendations` là metadata card, không phải nội dung chính cần check visible."""

    with pytest.raises(ValueError):
        TurnOutcome(
            conversation_id=uuid4(),
            client_turn_id=uuid4(),
            turn_number=1,
            status=TurnOutcomeStatus.COMPLETED,
            recommendations=(_recommendation(),),
        )
