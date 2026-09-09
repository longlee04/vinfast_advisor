"""Declined open slots round-trip through the repository text column."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from src.agents.adapters.conversation_repository import _slot_value
from src.agents.domain.values import DECLINED_SLOT_VALUE, SlotName
from src.agents.models import ConversationSlotRow


def _row(text: str) -> ConversationSlotRow:
    now = datetime.now(UTC)
    return ConversationSlotRow(
        session_id=uuid4(),
        slot_name=SlotName.HABIT_NEED_TAGS.value,
        slot_value_text=text,
        slot_value_number=None,
        confirmed_at=now,
        updated_at=now,
    )


def test_declined_habit_tags_are_not_json_decoded() -> None:
    assert _slot_value(SlotName.HABIT_NEED_TAGS, _row(DECLINED_SLOT_VALUE)) == DECLINED_SLOT_VALUE


def test_real_habit_tags_still_decode() -> None:
    assert _slot_value(SlotName.HABIT_NEED_TAGS, _row('["URBAN_TRAFFIC"]')) == ["URBAN_TRAFFIC"]
