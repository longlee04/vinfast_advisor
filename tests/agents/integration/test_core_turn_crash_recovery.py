"""T2.7/T2.8: crash recovery cho lease-based core turn."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api import conversation_routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.domain.conversation_memory import CoreTurnLease, TurnOutcome, TurnOutcomeStatus
from src.agents.errors import CoreTurnLeaseStaleError
from src.agents.models import ConversationTurnOutcomeRow
from src.agents.ports import ClockPort
from src.agents.services.conversation import ConversationLifecycleService

LEASE_SECONDS = 25


class ManualClock(ClockPort):
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value += timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class Transaction:
    conversations: SqlAlchemyConversationRepository
    outcomes: SqlAlchemyTurnOutcomeRepository


class SimulatedCrashError(RuntimeError):
    """Crash giữa core writes, buộc AgentUnitOfWork rollback."""


def _uow(factory: async_sessionmaker[AsyncSession], clock: ManualClock) -> AgentUnitOfWork[Transaction]:
    return AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            conversations=SqlAlchemyConversationRepository(session, clock),
            outcomes=SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )


async def _client(uow: AgentUnitOfWork[Transaction], customer_id: str) -> AsyncClient:
    app = FastAPI()
    app.include_router(conversation_routes.router, prefix="/api/v1")
    app.state.agent = SimpleNamespace(operations=SimpleNamespace(conversations=ConversationLifecycleService(uow)))
    app.dependency_overrides[get_current_customer_id] = lambda: customer_id
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://agent-test")


async def _create_conversation(uow: AgentUnitOfWork[Transaction], customer_id: str):
    async with uow.transaction() as transaction:
        return await transaction.conversations.create(customer_id)


async def _claim(
    uow: AgentUnitOfWork[Transaction], conversation_id: UUID, customer_id: str, client_turn_id: UUID
) -> CoreTurnLease:
    async with uow.transaction() as transaction:
        lease = await transaction.outcomes.acquire_core_turn_lease(
            conversation_id, customer_id, client_turn_id, lease_seconds=LEASE_SECONDS
        )
    assert isinstance(lease, CoreTurnLease)
    return lease


async def _finalize(uow: AgentUnitOfWork[Transaction], lease: CoreTurnLease, customer_id: str, *, answer: str) -> None:
    async with uow.transaction() as transaction:
        await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=lease.session_id,
                client_turn_id=lease.client_turn_id,
                turn_number=lease.turn_number,
                status=TurnOutcomeStatus.COMPLETED,
                answer=answer,
            )
        )


@pytest.mark.asyncio
async def test_crash_after_claim_leaves_no_terminal_result_and_lease_is_reclaimable(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    first = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    async with uow.transaction() as transaction:
        before_takeover = await transaction.outcomes.get(conversation.conversation_id, "customer-1", client_turn_id)
    assert before_takeover is not None
    assert before_takeover.status is TurnOutcomeStatus.IN_PROGRESS
    assert before_takeover.answer is None
    assert before_takeover.message_id is None

    clock.advance(LEASE_SECONDS + 1)
    taken = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    assert taken.turn_number == first.turn_number
    assert taken.claim_token != first.claim_token


@pytest.mark.asyncio
async def test_stale_worker_cannot_commit_after_takeover(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    first = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    clock.advance(LEASE_SECONDS + 1)
    await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    with pytest.raises(CoreTurnLeaseStaleError, match="token_replaced"):
        async with uow.transaction() as transaction:
            await transaction.outcomes.assert_core_turn_lease(first)


@pytest.mark.asyncio
async def test_mid_commit_crash_rolls_back_terminal_write_and_retry_creates_one_outcome(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    first = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    with pytest.raises(SimulatedCrashError):
        async with uow.transaction() as transaction:
            await transaction.outcomes.finalize(
                TurnOutcome(
                    conversation_id=first.session_id,
                    client_turn_id=first.client_turn_id,
                    turn_number=first.turn_number,
                    status=TurnOutcomeStatus.COMPLETED,
                    answer="must roll back",
                )
            )
            raise SimulatedCrashError("trace write failed")

    async with uow.transaction() as transaction:
        after_crash = await transaction.outcomes.get(conversation.conversation_id, "customer-1", client_turn_id)
    assert after_crash is not None
    assert after_crash.status is TurnOutcomeStatus.IN_PROGRESS
    assert after_crash.answer is None

    clock.advance(LEASE_SECONDS + 1)
    taken = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)
    await _finalize(uow, taken, "customer-1", answer="result after retry")

    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ConversationTurnOutcomeRow)
            .where(
                ConversationTurnOutcomeRow.session_id == conversation.conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == client_turn_id,
            )
        )
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome_status", "expected_status", "expected_code"),
    [
        (TurnOutcomeStatus.IN_PROGRESS, 202, "TURN_IN_PROGRESS"),
        (TurnOutcomeStatus.COMPLETED, 200, None),
        (TurnOutcomeStatus.FAILED, 409, "TURN_PREVIOUSLY_FAILED"),
    ],
)
async def test_recovery_get_maps_durable_outcome_status(
    migrated_engine: AsyncEngine,
    clean_agent_database: None,
    outcome_status: TurnOutcomeStatus,
    expected_status: int,
    expected_code: str | None,
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    lease = await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)
    if outcome_status is TurnOutcomeStatus.COMPLETED:
        await _finalize(uow, lease, "customer-1", answer="durable answer")
    elif outcome_status is TurnOutcomeStatus.FAILED:
        async with uow.transaction() as transaction:
            await transaction.outcomes.fail(conversation.conversation_id, client_turn_id, error_category="LLM_ERROR")

    async with await _client(uow, "customer-1") as client:
        response = await client.get(f"/api/v1/conversations/{conversation.conversation_id}/turns/{client_turn_id}")

    assert response.status_code == expected_status, response.text
    if expected_code is not None:
        assert response.json()["detail"]["code"] == expected_code
    else:
        assert response.json()["answer"] == "durable answer"


@pytest.mark.asyncio
async def test_recovery_get_missing_and_foreign_customer_are_not_found(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)

    async with await _client(uow, "customer-1") as client:
        missing = await client.get(f"/api/v1/conversations/{conversation.conversation_id}/turns/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "TURN_NOT_FOUND"

    async with await _client(uow, "customer-2") as client:
        foreign = await client.get(f"/api/v1/conversations/{conversation.conversation_id}/turns/{client_turn_id}")
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_recovery_get_expired_lease_returns_409(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    conversation = await _create_conversation(uow, "customer-1")
    client_turn_id = uuid4()
    await _claim(uow, conversation.conversation_id, "customer-1", client_turn_id)
    clock.advance(LEASE_SECONDS + 1)

    async with await _client(uow, "customer-1") as client:
        response = await client.get(f"/api/v1/conversations/{conversation.conversation_id}/turns/{client_turn_id}")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "TURN_LEASE_EXPIRED"
