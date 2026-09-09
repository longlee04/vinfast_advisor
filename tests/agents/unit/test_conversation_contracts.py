"""Frozen conversation contracts require customer ownership for session creation."""

from __future__ import annotations

from inspect import Parameter, signature

from src.agents.ports import SessionRepository
from src.agents.services.registry import ConversationService


def test_session_repository_requires_customer_id_to_ensure_session() -> None:
    parameters = signature(SessionRepository.ensure_session).parameters

    assert parameters["customer_id"].kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["customer_id"].default is Parameter.empty


def test_conversation_service_requires_customer_id_to_save_turn() -> None:
    parameters = signature(ConversationService.save_turn).parameters

    assert parameters["customer_id"].kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["customer_id"].default is Parameter.empty
