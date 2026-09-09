"""PostgreSQL behavior tests for bottleneck signal repository."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.bottleneck_signal_repository import SqlAlchemyBottleneckSignalRepository
from src.agents.domain.bottleneck_signal import (
    BottleneckSignalStatus,
    SignalClaimDeniedError,
    SignalInsert,
    SignalVerdict,
)
from src.agents.domain.customer_profile import Bottleneck

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
SESSION_ID = UUID("30000000-0000-0000-0000-000000000001")


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


async def _seed_session(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO conversation_sessions (session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) VALUES (:id, 'customer', 'ACTIVE', :now, :now, :now, :now)"
        ),
        {"id": SESSION_ID, "now": NOW},
    )


async def _outcome(session: AsyncSession, turn: int, recommendations: str = "[]") -> UUID:
    client_turn_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO conversation_turn_outcomes (outcome_id, session_id, client_turn_id, turn_number, status, recommendations, created_at, updated_at) VALUES (:id, :session, :client, :turn, 'COMPLETED', CAST(:recommendations AS jsonb), :now, :now)"
        ),
        {
            "id": uuid4(),
            "session": SESSION_ID,
            "client": client_turn_id,
            "turn": turn,
            "recommendations": recommendations,
            "now": NOW,
        },
    )
    return client_turn_id


def _signal(
    current: UUID, anchor: UUID, *, label: Bottleneck = Bottleneck.PRICE, quote: str = "token=[REDACTED]"
) -> SignalInsert:
    return SignalInsert(
        session_id=SESSION_ID,
        client_turn_id=current,
        anchor_client_turn_id=anchor,
        label=label,
        evidence_quote=quote,
        model_name="model",
        prompt_version="v1",
    )


@pytest.mark.asyncio
async def test_anchor_returns_none_then_latest_prior_eligible(agent_session: AsyncSession) -> None:
    # Given
    await _seed_session(agent_session)
    first = await _outcome(agent_session, 1)
    latest = await _outcome(agent_session, 2, '[{"vehicle_id":"vf8"}]')
    current = await _outcome(agent_session, 3)
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, FixedClock())

    # When / Then
    assert await repository.latest_recommendation_anchor(SESSION_ID, first) is None
    assert await repository.latest_recommendation_anchor(SESSION_ID, current) == latest


@pytest.mark.asyncio
async def test_insert_list_detail_and_one_signal_per_turn(agent_session: AsyncSession) -> None:
    # Given
    await _seed_session(agent_session)
    anchor = await _outcome(agent_session, 1, '[{"vehicle_id":"vf8"}]')
    current = await _outcome(agent_session, 2)
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, FixedClock())

    # When
    created = await repository.insert(_signal(current, anchor))

    # Then
    assert (await repository.get(created.signal_id)) == created
    assert await repository.list_pending() == (created,)
    assert await repository.insert(_signal(current, anchor)) == created


@pytest.mark.asyncio
async def test_correct_projection_is_ordered_and_preserves_redaction(agent_session: AsyncSession) -> None:
    # Given
    await _seed_session(agent_session)
    anchor = await _outcome(agent_session, 1, '[{"vehicle_id":"vf8"}]')
    second = await _outcome(agent_session, 2)
    third = await _outcome(agent_session, 3)
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, FixedClock())
    later = await repository.insert(_signal(third, anchor, label=Bottleneck.RANGE, quote="later"))
    earlier = await repository.insert(_signal(second, anchor))
    await repository.claim(earlier.signal_id, "advisor", lease_minutes=15)
    await repository.decide(earlier.signal_id, "advisor", SignalVerdict.CORRECT)
    await repository.claim(later.signal_id, "advisor", lease_minutes=15)
    await repository.decide(later.signal_id, "advisor", SignalVerdict.INCORRECT)

    # When
    evidence = await repository.confirmed_evidence(SESSION_ID, anchor)

    # Then
    assert [(item.label, item.evidence_quote) for item in evidence] == [(Bottleneck.PRICE, "token=[REDACTED]")]


@pytest.mark.asyncio
async def test_claim_cas_reclaim_and_terminal_verdict_rules(agent_session: AsyncSession) -> None:
    # Given
    await _seed_session(agent_session)
    anchor = await _outcome(agent_session, 1, '[{"vehicle_id":"vf8"}]')
    current = await _outcome(agent_session, 2)
    clock = FixedClock()
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, clock)
    signal = await repository.insert(_signal(current, anchor))

    # When / Then
    assert await repository.claim(signal.signal_id, "advisor-1", lease_minutes=15)
    assert not await repository.claim(signal.signal_id, "advisor-2", lease_minutes=15)
    clock.now_value = NOW + timedelta(minutes=16)
    assert await repository.claim(signal.signal_id, "advisor-2", lease_minutes=15)
    with pytest.raises(SignalClaimDeniedError):
        await repository.decide(signal.signal_id, "advisor-1", SignalVerdict.CORRECT)
    decided = await repository.decide(signal.signal_id, "advisor-2", SignalVerdict.CORRECT)
    assert decided.status is BottleneckSignalStatus.CORRECT
    with pytest.raises(SignalClaimDeniedError):
        await repository.decide(signal.signal_id, "advisor-2", SignalVerdict.INCORRECT)


@pytest.mark.asyncio
async def test_opportunities_aggregate_only_correct_labels(agent_session: AsyncSession) -> None:
    # Given
    await _seed_session(agent_session)
    anchor = await _outcome(agent_session, 1, '[{"vehicle_id":"vf8"}]')
    price_turn = await _outcome(agent_session, 2)
    range_turn = await _outcome(agent_session, 3)
    repository = SqlAlchemyBottleneckSignalRepository(agent_session, FixedClock())
    price_signal = await repository.insert(_signal(price_turn, anchor))
    range_signal = await repository.insert(_signal(range_turn, anchor, label=Bottleneck.RANGE))
    for signal in (price_signal, range_signal):
        await repository.claim(signal.signal_id, "advisor", lease_minutes=15)
        await repository.decide(signal.signal_id, "advisor", SignalVerdict.CORRECT)

    # When
    opportunities = await repository.list_opportunities(since=NOW - timedelta(hours=24), limit=100)

    # Then
    assert opportunities[0].session_id == SESSION_ID
    assert opportunities[0].labels == frozenset({Bottleneck.PRICE, Bottleneck.RANGE})
    assert opportunities[0].correct_signal_count == 2
