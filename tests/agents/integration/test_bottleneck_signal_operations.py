"""PostgreSQL operation tests for bottleneck signal staff workflow."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import SqlAlchemyBottleneckSignalRepository
from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.bottleneck_signal import (
    BottleneckSignalStatus,
    SignalClaimDeniedError,
    SignalInsert,
    SignalVerdict,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.services.operations.bottleneck_signal import BottleneckSignalOperations

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
SESSION_ID = UUID("50000000-0000-0000-0000-000000000001")


class MutableClock:
    def __init__(self) -> None:
        self.moment = NOW

    def now(self) -> datetime:
        return self.moment


async def _seed(repository: SqlAlchemyBottleneckSignalRepository) -> UUID:
    await repository.session.execute(
        text(
            "INSERT INTO conversation_sessions "
            "(session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) "
            "VALUES (:id, 'customer', 'ACTIVE', :now, :now, :now, :now)"
        ),
        {"id": SESSION_ID, "now": NOW},
    )
    anchor = uuid4()
    current = uuid4()
    for turn_number, client_turn_id in ((1, anchor), (2, current)):
        await repository.session.execute(
            text(
                "INSERT INTO conversation_turn_outcomes "
                "(outcome_id, session_id, client_turn_id, turn_number, status, recommendations, created_at, updated_at) "
                "VALUES (:id, :session, :client, :turn, 'COMPLETED', '[]'::jsonb, :now, :now)"
            ),
            {
                "id": uuid4(),
                "session": SESSION_ID,
                "client": client_turn_id,
                "turn": turn_number,
                "now": NOW,
            },
        )
    signal = await repository.insert(
        SignalInsert(
            session_id=SESSION_ID,
            client_turn_id=current,
            anchor_client_turn_id=anchor,
            label=Bottleneck.PRICE,
            evidence_quote="Giá cao [REDACTED]",
            model_name="internal-model",
            prompt_version="internal-prompt",
        )
    )
    return signal.signal_id


@pytest.mark.asyncio
async def test_operations_filter_page_and_return_detail(agent_session: AsyncSession) -> None:
    # Given
    clock = MutableClock()
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, clock)
    signal_id = await _seed(repository)
    await agent_session.commit()
    operations = BottleneckSignalOperations(
        AgentUnitOfWork(
            async_sessionmaker(agent_session.bind, expire_on_commit=False),
            lambda session: build_agent_transaction(session, clock=clock),
        )
    )

    # When
    page = await operations.list_signals(BottleneckSignalStatus.PENDING, 10, 0)
    detail = await operations.detail(signal_id)

    # Then
    assert [item.signal_id for item in page] == [signal_id]
    assert detail.signal.signal_id == signal_id
    assert detail.matched_promotions == ()
    assert detail.adjustment_policies == ()


@pytest.mark.asyncio
async def test_claim_has_one_winner_and_expired_lease_can_be_reclaimed(
    agent_session: AsyncSession,
) -> None:
    # Given
    clock = MutableClock()
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, clock)
    signal_id = await _seed(repository)
    await agent_session.commit()
    operations = BottleneckSignalOperations(
        AgentUnitOfWork(
            async_sessionmaker(agent_session.bind, expire_on_commit=False),
            lambda session: build_agent_transaction(session, clock=clock),
        )
    )

    # When / Then
    await operations.claim(signal_id, "advisor-1")
    with pytest.raises(SignalClaimDeniedError):
        await operations.claim(signal_id, "advisor-2")
    clock.moment = NOW + timedelta(minutes=16)
    reclaimed = await operations.claim(signal_id, "advisor-2")
    assert reclaimed.claimed_by == "advisor-2"


@pytest.mark.asyncio
async def test_verdict_requires_current_holder_and_terminal_status_is_immutable(
    agent_session: AsyncSession,
) -> None:
    # Given
    clock = MutableClock()
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, clock)
    signal_id = await _seed(repository)
    await agent_session.commit()
    operations = BottleneckSignalOperations(
        AgentUnitOfWork(
            async_sessionmaker(agent_session.bind, expire_on_commit=False),
            lambda session: build_agent_transaction(session, clock=clock),
        )
    )
    await operations.claim(signal_id, "advisor-1")

    # When / Then
    with pytest.raises(SignalClaimDeniedError):
        await operations.verdict(signal_id, "advisor-2", SignalVerdict.CORRECT)
    decided = await operations.verdict(signal_id, "advisor-1", SignalVerdict.CORRECT)
    assert decided.status is BottleneckSignalStatus.CORRECT
    with pytest.raises(SignalClaimDeniedError):
        await operations.verdict(signal_id, "advisor-1", SignalVerdict.INCORRECT)
