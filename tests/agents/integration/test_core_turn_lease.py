"""T1.5/T1.6: acquire_core_turn_lease trên PostgreSQL thật — claim/replay/takeover."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.conversation_memory import (
    CoreTurnLease,
    LeaseBusy,
    TerminalReplay,
    TurnOutcomeStatus,
)
from src.agents.ports import ClockPort

LEASE_SECONDS = 25
RETRY_AFTER = 2


class ManualClock(ClockPort):
    """Clock tay — test không cần sleep thật."""

    def __init__(self, start: datetime) -> None:
        self.now_value = start

    def now(self) -> datetime:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value = self.now_value + timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class Transaction:
    conversations: SqlAlchemyConversationRepository
    outcomes: SqlAlchemyTurnOutcomeRepository


def _uow(factory: async_sessionmaker, clock: ManualClock) -> AgentUnitOfWork[Transaction]:
    return AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            SqlAlchemyConversationRepository(session, clock),
            SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )


@pytest.mark.asyncio
async def test_first_claim_returns_lease_and_turn_number(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    client_turn_id = uuid4()

    async with uow.transaction() as transaction:
        result = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id,
            "customer-1",
            client_turn_id,
            lease_seconds=LEASE_SECONDS,
        )

    assert isinstance(result, CoreTurnLease)
    assert result.session_id == conversation.conversation_id
    assert result.client_turn_id == client_turn_id
    assert result.turn_number == 1
    assert result.claim_token is not None
    assert result.lease_expires_at == result.claimed_at + timedelta(seconds=LEASE_SECONDS)


@pytest.mark.asyncio
async def test_same_client_turn_terminal_returns_terminal_replay(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        outcome = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        await transaction.outcomes.finalize(_completed(outcome.outcome, "kết quả terminal"))
    clock.advance(1)

    async with uow.transaction() as transaction:
        result = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id,
            "customer-1",
            client_turn_id,
            lease_seconds=LEASE_SECONDS,
        )

    assert isinstance(result, TerminalReplay)
    assert result.result.answer == "kết quả terminal"
    assert not isinstance(result, CoreTurnLease)


@pytest.mark.asyncio
async def test_same_client_turn_live_returns_lease_busy(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Raw TurnClaim(IN_PROGRESS) không được thoát repository boundary."""
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    client_turn_id = uuid4()
    async with uow.transaction() as transaction:
        first = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(first, CoreTurnLease)
    clock.advance(5)

    async with uow.transaction() as transaction:
        result = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )

    assert isinstance(result, LeaseBusy)
    assert result.retry_after_seconds == RETRY_AFTER


@pytest.mark.asyncio
async def test_other_turn_same_session_returns_lease_busy(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Hai turn khác ID trong cùng session không chạy song song."""
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    first_id = uuid4()
    second_id = uuid4()
    async with uow.transaction() as transaction:
        first = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", first_id, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(first, CoreTurnLease)
    clock.advance(5)

    async with uow.transaction() as transaction:
        result = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", second_id, lease_seconds=LEASE_SECONDS
        )

    assert isinstance(result, LeaseBusy)


@pytest.mark.asyncio
async def test_expired_lease_takeover_keeps_turn_number_and_changes_token(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    client_turn_id = uuid4()
    async with uow.transaction() as transaction:
        first = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(first, CoreTurnLease)
    clock.advance(LEASE_SECONDS + 1)

    async with uow.transaction() as transaction:
        taken = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )

    assert isinstance(taken, CoreTurnLease)
    assert taken.turn_number == first.turn_number
    assert taken.claim_token != first.claim_token


@pytest.mark.asyncio
async def test_expired_turn_cannot_take_over_while_another_turn_holds_session(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Lượt hết hạn KHÔNG được giành lại phiên khi lượt khác đang giữ.

    Đua thật đã đọc được trên source: nhánh trùng mã lượt takeover TRƯỚC khi hỏi
    phiên, nên chuỗi dưới đây từng cho ra HAI chủ lease cùng lúc — cả hai đều ghi
    được, đúng lớp lỗi mất-ghi mà lease sinh ra để chặn.
    """

    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    turn_a = uuid4()
    turn_b = uuid4()

    async with uow.transaction() as transaction:
        lease_a = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", turn_a, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(lease_a, CoreTurnLease)

    # A hết hạn, B chiếm phiên bằng một mã lượt khác.
    clock.advance(LEASE_SECONDS + 1)
    async with uow.transaction() as transaction:
        lease_b = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", turn_b, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(lease_b, CoreTurnLease)

    # A thử lại đúng mã cũ: phải nhận busy, KHÔNG được takeover.
    async with uow.transaction() as transaction:
        retry_a = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", turn_a, lease_seconds=LEASE_SECONDS
        )

    assert isinstance(retry_a, LeaseBusy)

    # Và B vẫn là chủ duy nhất — token của B còn hiệu lực.
    async with uow.transaction() as transaction:
        await transaction.outcomes.assert_core_turn_lease(lease_b)


@pytest.mark.asyncio
async def test_old_token_is_rejected_after_takeover(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    """assert_core_turn_lease phải reject token cũ sau takeover."""
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = ManualClock(datetime(2026, 9, 1, tzinfo=UTC))
    uow = _uow(factory, clock)
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    client_turn_id = uuid4()
    async with uow.transaction() as transaction:
        first = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(first, CoreTurnLease)
    clock.advance(LEASE_SECONDS + 1)
    async with uow.transaction() as transaction:
        taken = await transaction.outcomes.acquire_core_turn_lease(
            conversation.conversation_id, "customer-1", client_turn_id, lease_seconds=LEASE_SECONDS
        )
        assert isinstance(taken, CoreTurnLease)

    with pytest.raises(Exception):
        async with uow.transaction() as transaction:
            await transaction.outcomes.assert_core_turn_lease(first)


def _completed(outcome, answer: str):
    from src.agents.domain.conversation_memory import TurnOutcome

    return TurnOutcome(
        conversation_id=outcome.conversation_id,
        client_turn_id=outcome.client_turn_id,
        turn_number=outcome.turn_number,
        status=TurnOutcomeStatus.COMPLETED,
        answer=answer,
    )
