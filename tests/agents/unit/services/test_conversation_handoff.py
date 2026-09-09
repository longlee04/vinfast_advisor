"""A: máy trạng thái sở hữu phiên — service đọc/ghi ownership."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.services.conversation import ConversationServiceImpl


class _SessionsStub:
    def __init__(self, ownership: str | None) -> None:
        self._ownership = ownership

    async def get_ownership(self, session_id: str) -> str | None:
        return self._ownership

    async def set_ownership(self, session_id: str, ownership: str) -> bool:
        self._ownership = ownership
        return True


class _TransactionStub:
    def __init__(self, sessions: _SessionsStub) -> None:
        self.sessions = sessions


class _UowStub:
    def __init__(self, sessions: _SessionsStub) -> None:
        self._sessions = sessions

    def transaction(self) -> _ContextManagerStub:
        return _ContextManagerStub(self._sessions)


class _ContextManagerStub:
    def __init__(self, sessions: _SessionsStub) -> None:
        self._sessions = sessions

    async def __aenter__(self) -> _TransactionStub:
        return _TransactionStub(self._sessions)

    async def __aexit__(self, *args: Any) -> bool:
        return False


@pytest.mark.asyncio
async def test_load_handoff_state_true_when_pending_handoff() -> None:
    service = ConversationServiceImpl(_UowStub(_SessionsStub("PENDING_HANDOFF")))  # type: ignore[arg-type]

    assert await service.load_handoff_state("s") is True


@pytest.mark.asyncio
async def test_load_handoff_state_true_when_human() -> None:
    service = ConversationServiceImpl(_UowStub(_SessionsStub("HUMAN")))  # type: ignore[arg-type]

    assert await service.load_handoff_state("s") is True


@pytest.mark.asyncio
async def test_load_handoff_state_false_when_ai() -> None:
    service = ConversationServiceImpl(_UowStub(_SessionsStub("AI")))  # type: ignore[arg-type]

    assert await service.load_handoff_state("s") is False


@pytest.mark.asyncio
async def test_load_handoff_state_false_when_session_missing() -> None:
    service = ConversationServiceImpl(_UowStub(_SessionsStub(None)))  # type: ignore[arg-type]

    assert await service.load_handoff_state("s") is False


@pytest.mark.asyncio
async def test_set_handoff_pending_and_resolve_handoff_transition() -> None:
    sessions = _SessionsStub("AI")
    service = ConversationServiceImpl(_UowStub(sessions))  # type: ignore[arg-type]

    assert await service.set_handoff_pending("s") is True
    assert sessions._ownership == "PENDING_HANDOFF"
    assert await service.resolve_handoff("s") is True
    assert sessions._ownership == "AI"
