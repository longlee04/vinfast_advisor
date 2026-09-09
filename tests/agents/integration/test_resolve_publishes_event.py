"""Task 7 integration tests for review-resolution turn events."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.agents.services.operations.turn_events import TurnEvent

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
DRAFT = "Noi dung tu van da duoc kiem chung"


class RecordingBroker:
    """Record events and observe committed review state during publication."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.events: list[TurnEvent] = []
        self.statuses_at_publish: list[str | None] = []

    async def publish(self, event: TurnEvent) -> None:
        self.events.append(event)
        async with self._engine.connect() as connection:
            self.statuses_at_publish.append(
                await connection.scalar(
                    select(ReviewQueueRow.status).where(ReviewQueueRow.review_id == event.review_id)
                )
            )

    def subscribe(self, _session_id: UUID) -> AbstractAsyncContextManager[AsyncIterator[TurnEvent]]:
        raise NotImplementedError


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(engine: AsyncEngine) -> tuple[UUID, UUID]:
    session_id = uuid4()
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
                run_id=uuid4(),
                session_id=session_id,
                state="PENDING_REVIEW",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        run_id = await connection.scalar(select(AgentRunRow.run_id).where(AgentRunRow.session_id == session_id))
        assert run_id is not None
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=DRAFT,
                status="PENDING",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id, session_id


def _operations(engine: AsyncEngine, broker: RecordingBroker) -> ReviewOperations:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    return ReviewOperations(unit_of_work=unit_of_work, broker=broker)


@pytest.mark.asyncio
async def test_approve_publishes_one_event_after_commit_with_review_session(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id, session_id = await _seed_review(migrated_engine)
    broker = RecordingBroker(migrated_engine)

    # When
    await _operations(migrated_engine, broker).approve(review_id, advisor_id="advisor-a")

    # Then
    assert len(broker.events) == 1
    assert broker.events[0].session_id == session_id
    assert broker.events[0].review_id == review_id
    assert broker.events[0].kind == "approved"
    assert broker.events[0].message_id is not None
    assert broker.statuses_at_publish == ["APPROVED"]


@pytest.mark.asyncio
async def test_reject_publishes_recovery_event_after_commit(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    review_id, session_id = await _seed_review(migrated_engine)
    broker = RecordingBroker(migrated_engine)

    # When
    await _operations(migrated_engine, broker).reject(review_id, advisor_id="advisor-a")

    # Then
    assert len(broker.events) == 1
    assert broker.events[0].session_id == session_id
    assert broker.events[0].review_id == review_id
    assert broker.events[0].kind == "rejected"
    assert broker.statuses_at_publish == ["REJECTED"]
