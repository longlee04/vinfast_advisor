"""Shared expiry policy for intrusive pending questions and resumable tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class ConversationFocusPolicy:
    """Durations after which implicit context capture is no longer allowed."""

    pending_question_ttl: timedelta = timedelta(minutes=15)
    resumable_task_ttl: timedelta = timedelta(minutes=30)


DEFAULT_CONVERSATION_FOCUS_POLICY = ConversationFocusPolicy()


__all__ = ["ConversationFocusPolicy", "DEFAULT_CONVERSATION_FOCUS_POLICY"]
