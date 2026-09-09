from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationCursor,
    ConversationMessage,
    ConversationPage,
    ConversationState,
    MemoryMessage,
    MessageCursor,
    MessagePage,
    TurnOutcome,
    TurnOutcomeStatus,
    WorkingMemoryProjection,
    decode_conversation_cursor,
    decode_message_cursor,
    encode_conversation_cursor,
    encode_message_cursor,
)


def test_conversation_contract_keeps_public_identity_and_archive_state() -> None:
    conversation_id = uuid4()
    created_at = datetime(2026, 8, 15, tzinfo=UTC)

    conversation = Conversation(
        conversation_id=conversation_id,
        customer_id="customer-1",
        state=ConversationState.ACTIVE,
        created_at=created_at,
        last_activity_at=created_at,
    )

    assert conversation.conversation_id == conversation_id
    assert conversation.state is ConversationState.ACTIVE
    assert conversation.archived_at is None


def test_visible_message_can_carry_stable_server_and_correlation_ids() -> None:
    conversation_id = uuid4()
    client_turn_id = uuid4()
    message_id = uuid4()

    message = ConversationMessage(
        role="USER",
        content="Tôi cần xe gia đình.",
        turn_index=1,
        message_id=message_id,
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        created_at=datetime(2026, 8, 15, tzinfo=UTC),
    )

    assert message.message_id == message_id
    assert message.conversation_id == conversation_id
    assert message.client_turn_id == client_turn_id


def test_turn_outcome_rejects_completed_state_without_customer_result() -> None:
    with pytest.raises(ValueError, match="completed turn outcome"):
        TurnOutcome(
            conversation_id=uuid4(),
            client_turn_id=uuid4(),
            turn_number=1,
            status=TurnOutcomeStatus.COMPLETED,
        )


def test_turn_outcome_keeps_exact_replay_payload() -> None:
    outcome = TurnOutcome(
        conversation_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=2,
        status=TurnOutcomeStatus.COMPLETED,
        terminal_reason="CATALOG_LOOKUP",
        lookup_facts=({"vehicle_id": str(uuid4()), "display_name": "VF 7"},),
    )

    assert outcome.lookup_facts[0]["display_name"] == "VF 7"
    assert outcome.terminal_reason == "CATALOG_LOOKUP"


def test_working_memory_projection_preserves_roles_and_current_message() -> None:
    projection = WorkingMemoryProjection(
        slots={"vehicle_type": "CAR"},
        summary="Khách đang cân nhắc VF 7.",
        recent_messages=(
            MemoryMessage("USER", "VF 7 đi được bao xa?"),
            MemoryMessage("ASSISTANT", "Thông tin quãng đường VF 7."),
        ),
        pending_features=("camera 360",),
        current_user_message="Con đó giá bao nhiêu?",
    )

    assert [message.role for message in projection.recent_messages] == ["USER", "ASSISTANT"]
    assert projection.current_user_message == "Con đó giá bao nhiêu?"


def test_pagination_cursors_are_opaque_and_round_trip() -> None:
    conversation_cursor = ConversationCursor(
        last_activity_at=datetime(2026, 8, 15, tzinfo=UTC),
        conversation_id=uuid4(),
    )
    message_cursor = MessageCursor(turn_index=12, message_id=uuid4())

    encoded_conversation = encode_conversation_cursor(conversation_cursor)
    encoded_message = encode_message_cursor(message_cursor)

    assert decode_conversation_cursor(encoded_conversation) == conversation_cursor
    assert decode_message_cursor(encoded_message) == message_cursor
    assert ":" not in encoded_conversation


def test_pages_require_positive_limit_and_matching_next_cursor() -> None:
    with pytest.raises(ValueError, match="page limit"):
        ConversationPage(items=(), limit=0)
    with pytest.raises(ValueError, match="page limit"):
        MessagePage(items=(), limit=0)


@pytest.mark.parametrize("status", [TurnOutcomeStatus.IN_PROGRESS, TurnOutcomeStatus.FAILED])
def test_non_completed_turn_outcome_cannot_contain_visible_success(status: TurnOutcomeStatus) -> None:
    with pytest.raises(ValueError, match="non-completed turn outcome"):
        TurnOutcome(
            conversation_id=uuid4(),
            client_turn_id=uuid4(),
            turn_number=1,
            status=status,
            answer="Không được phép có câu trả lời thành công.",
        )
