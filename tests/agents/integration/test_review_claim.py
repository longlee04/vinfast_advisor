"""A7-2 acceptance tests — compare-and-set claim with a 15-minute lease."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Update, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.repositories import SqlAlchemyReviewQueueRepository, build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import (
    DEFAULT_LEASE_MINUTES,
    ClaimableReviewQueue,
    ClaimRejection,
    ReviewOperations,
)

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


class FrozenClock:
    """Deterministic `ClockPort` so lease boundaries are exact, not wall-clock dependent."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class BarrierSession:
    """Hold both transactions right before their write so the race really overlaps.

    `asyncio.gather` alone is not enough: one claim still runs to completion
    before the other starts, so the test stays green even when the repository
    reads first and writes second. Blocking at the `UPDATE` guarantees both
    transactions have already read the row before either one writes — the only
    arrangement that tells a real compare-and-set apart from read-then-write.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        self._session = session
        self._barrier = barrier
        self._released = False

    async def _release_once_before_writing(self, statement: Any) -> None:
        if not self._released and isinstance(statement, Update):
            self._released = True
            await self._barrier.wait()

    async def execute(self, statement: Any) -> Any:
        await self._release_once_before_writing(statement)
        return await self._session.execute(statement)

    async def scalar(self, statement: Any) -> Any:
        await self._release_once_before_writing(statement)
        return await self._session.scalar(statement)


@dataclass(frozen=True)
class RacingTransaction:
    review_queue: ClaimableReviewQueue


class RacingUnitOfWork:
    """Unit of work whose transactions all pause at the barrier before touching the row."""

    def __init__(self, engine: AsyncEngine, clock: FrozenClock, barrier: asyncio.Barrier) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._clock = clock
        self._barrier = barrier

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RacingTransaction]:
        async with self._session_factory() as session, session.begin():
            repository = SqlAlchemyReviewQueueRepository(
                BarrierSession(session, self._barrier),  # type: ignore[arg-type]
                self._clock,
            )
            yield RacingTransaction(review_queue=repository)


async def _seed_review(engine: AsyncEngine, **review_values: object) -> UUID:
    session_id = uuid4()
    run_id = uuid4()
    review_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="PENDING_REVIEW",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content="ban nhap cho tu van vien duyet",
                status="PENDING",
                created_at=NOW,
                updated_at=NOW,
                **review_values,
            )
        )
    return review_id


def _operations(engine: AsyncEngine, moment: datetime = NOW) -> ReviewOperations:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FrozenClock(moment)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=clock),
    )
    return ReviewOperations(unit_of_work=unit_of_work)


def _racing_operations(engine: AsyncEngine, moment: datetime = NOW) -> tuple[ReviewOperations, ReviewOperations]:
    """Two use cases sharing one barrier: neither can finish before the other starts."""
    barrier = asyncio.Barrier(2)
    clock = FrozenClock(moment)
    return (
        ReviewOperations(unit_of_work=RacingUnitOfWork(engine, clock, barrier)),
        ReviewOperations(unit_of_work=RacingUnitOfWork(engine, clock, barrier)),
    )


@pytest.mark.asyncio
async def test_concurrent_claims_grant_exactly_one_advisor(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine)
    first_ops, second_ops = _racing_operations(migrated_engine)

    # When — two real transactions racing in parallel, not simulated sequentially
    first, second = await asyncio.gather(
        first_ops.claim(review_id, advisor_id="advisor-a"),
        second_ops.claim(review_id, advisor_id="advisor-b"),
    )

    # Then
    assert [first.granted, second.granted].count(True) == 1


@pytest.mark.asyncio
async def test_losing_advisor_is_told_the_item_is_already_claimed(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine)
    first_ops, second_ops = _racing_operations(migrated_engine)

    # When
    first, second = await asyncio.gather(
        first_ops.claim(review_id, advisor_id="advisor-a"),
        second_ops.claim(review_id, advisor_id="advisor-b"),
    )

    # Then
    loser = first if not first.granted else second
    assert loser.rejection is ClaimRejection.ALREADY_CLAIMED


@pytest.mark.asyncio
async def test_expired_lease_lets_another_advisor_claim_again(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — a stale claim whose lease ran out; `claimed_by` is still on the row
    review_id = await _seed_review(
        migrated_engine,
        claimed_by="advisor-a",
        claimed_at=NOW - timedelta(minutes=30),
        lease_expires_at=NOW - timedelta(minutes=15),
    )
    operations = _operations(migrated_engine)

    # When
    outcome = await operations.claim(review_id, advisor_id="advisor-b")

    # Then
    assert outcome.granted is True
    async with migrated_engine.connect() as connection:
        claimed_by = await connection.scalar(
            select(ReviewQueueRow.claimed_by).where(ReviewQueueRow.review_id == review_id)
        )
    assert claimed_by == "advisor-b"


@pytest.mark.asyncio
async def test_live_lease_blocks_a_second_advisor(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given — negative case: the lease is still valid
    review_id = await _seed_review(
        migrated_engine,
        claimed_by="advisor-a",
        claimed_at=NOW,
        lease_expires_at=NOW + timedelta(minutes=DEFAULT_LEASE_MINUTES),
    )
    operations = _operations(migrated_engine)

    # When
    outcome = await operations.claim(review_id, advisor_id="advisor-b")

    # Then
    assert outcome.granted is False
    assert outcome.rejection is ClaimRejection.ALREADY_CLAIMED


@pytest.mark.asyncio
async def test_claiming_an_unknown_review_is_rejected_as_not_found(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — negative case: nothing seeded for this identifier
    operations = _operations(migrated_engine)

    # When
    outcome = await operations.claim(uuid4(), advisor_id="advisor-a")

    # Then
    assert outcome.granted is False
    assert outcome.rejection is ClaimRejection.NOT_FOUND


@pytest.mark.asyncio
async def test_granted_claim_writes_a_fifteen_minute_lease(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id = await _seed_review(migrated_engine)
    operations = _operations(migrated_engine)

    # When
    outcome = await operations.claim(review_id, advisor_id="advisor-a")

    # Then
    assert outcome.granted is True
    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(
                select(ReviewQueueRow.claimed_at, ReviewQueueRow.lease_expires_at).where(
                    ReviewQueueRow.review_id == review_id
                )
            )
        ).one()
    assert row.lease_expires_at - row.claimed_at == timedelta(minutes=15)
