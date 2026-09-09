"""T3.5/T3.6: canonical turn-result replay survives PostgreSQL round trips."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.contracts import TurnResult
from src.agents.domain.conversation_memory import TerminalReplay, TurnOutcome, TurnOutcomeStatus
from src.agents.domain.turn_result_payload import serialize_turn_result
from src.agents.ports import ClockPort


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 9, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Transaction:
    conversations: SqlAlchemyConversationRepository
    outcomes: SqlAlchemyTurnOutcomeRepository


def _uow(factory: async_sessionmaker) -> AgentUnitOfWork[Transaction]:
    clock = FixedClock()
    return AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            SqlAlchemyConversationRepository(session, clock),
            SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )


def _result(session_id: str, *, answer: str = "Kết quả") -> TurnResult:
    return TurnResult(
        session_id=session_id,
        answer=answer,
        pending_question=None,
        terminal_reason="CATALOG_LOOKUP",
        conversation_state="ACTIVE",
        options=[{"label": "Xem xe", "value": "details"}],
    )


@pytest.mark.asyncio
async def test_postgres_finalize_new_uow_replays_full_canonical_payload(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    uow = _uow(factory)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        claim = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        result = _result(str(conversation.conversation_id))
        await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation.conversation_id,
                client_turn_id=client_turn_id,
                turn_number=claim.outcome.turn_number,
                status=TurnOutcomeStatus.COMPLETED,
                answer=result.answer,
                terminal_reason=result.terminal_reason,
                result_payload=serialize_turn_result(result),
            )
        )

    replay_uow = _uow(factory)
    async with replay_uow.transaction() as transaction:
        replay = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id,
            "customer-1",
            client_turn_id,
            lease_seconds=25,
        )

    assert isinstance(replay, TerminalReplay)
    assert replay.result == result
    assert replay.result.conversation_state == "ACTIVE"
    assert replay.result.options == [{"label": "Xem xe", "value": "details"}]


@pytest.mark.asyncio
async def test_old_null_payload_uses_typed_outcome_fallback(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    uow = _uow(factory)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        claim = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation.conversation_id,
                client_turn_id=client_turn_id,
                turn_number=claim.outcome.turn_number,
                status=TurnOutcomeStatus.COMPLETED,
                answer="Legacy result",
            )
        )

    async with _uow(factory).transaction() as transaction:
        replay = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=25
        )

    assert isinstance(replay, TerminalReplay)
    assert replay.result.answer == "Legacy result"
    assert replay.result.conversation_state is None
    assert replay.result.options is None


@pytest.mark.asyncio
async def test_malformed_payload_safely_falls_back_to_typed_outcome(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    uow = _uow(factory)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        claim = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation.conversation_id,
                client_turn_id=client_turn_id,
                turn_number=claim.outcome.turn_number,
                status=TurnOutcomeStatus.COMPLETED,
                answer="Safe typed result",
                result_payload={"version": 1, "fields": {"answer": 123}},
            )
        )

    async with _uow(factory).transaction() as transaction:
        replay = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=25
        )

    assert isinstance(replay, TerminalReplay)
    assert replay.result.answer == "Safe typed result"
    assert replay.result.conversation_state is None
    assert replay.result.options is None
