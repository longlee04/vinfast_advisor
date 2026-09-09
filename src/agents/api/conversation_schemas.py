"""Public Pydantic contracts for server-backed customer conversations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationResponse(BaseModel):
    """One customer-owned conversation without internal memory state."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    state: str
    created_at: datetime
    last_activity_at: datetime
    archived_at: datetime | None


class ConversationListResponse(BaseModel):
    """Stable page of customer-owned conversations."""

    model_config = ConfigDict(frozen=True)

    items: list[ConversationResponse]
    next_cursor: str | None


class ConversationMessageResponse(BaseModel):
    """One durable customer-visible transcript message."""

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    role: str
    content: str
    order: int
    created_at: datetime
    client_turn_id: UUID | None
    review_id: UUID | None


class ConversationMessageListResponse(BaseModel):
    """Chronological page of visible transcript messages."""

    model_config = ConfigDict(frozen=True)

    items: list[ConversationMessageResponse]
    next_cursor: str | None


class ConversationTurnRequest(BaseModel):
    """One idempotent customer submission."""

    model_config = ConfigDict(frozen=True)

    client_turn_id: UUID
    message: str = Field(min_length=1, max_length=10_000)


class ConversationTurnResponse(BaseModel):
    """Exact customer-safe result returned and replayed for one client key."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    client_turn_id: UUID
    status: str
    answer: str | None
    pending_question: str | None
    lookup_facts: list[dict[str, object]]
    terminal_reason: str | None
    review_id: UUID | None
