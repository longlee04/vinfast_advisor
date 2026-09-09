"""A8-4 acceptance tests — internal notices with per-advisor read state."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import NoticeReadRow
from src.agents.services.operations.notices import NoticeNotFoundError, NoticeOperations

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


class FrozenClock:
    """Deterministic `ClockPort` so `read_at` is exact, not wall-clock dependent."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _operations(engine: AsyncEngine) -> NoticeOperations:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FrozenClock(NOW)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=clock),
    )
    return NoticeOperations(unit_of_work=unit_of_work)


async def _count_reads(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        total = await connection.scalar(select(func.count()).select_from(NoticeReadRow))
    return int(total or 0)


@pytest.mark.asyncio
async def test_two_advisors_reading_one_notice_create_independent_rows(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    operations = _operations(migrated_engine)
    notice_id = await operations.publish(
        title="Chinh sach bao hanh moi",
        content="Ap dung tu thang sau",
        priority="NORMAL",
        created_by="admin-1",
    )

    # When
    await operations.mark_read(notice_id, advisor_id="advisor-a")
    await operations.mark_read(notice_id, advisor_id="advisor-b")

    # Then
    assert await _count_reads(migrated_engine) == 2
    async with migrated_engine.connect() as connection:
        advisors = (
            await connection.execute(select(NoticeReadRow.advisor_id).where(NoticeReadRow.notice_id == notice_id))
        ).scalars()
    assert sorted(advisors) == ["advisor-a", "advisor-b"]


@pytest.mark.asyncio
async def test_same_advisor_reading_twice_keeps_one_row(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — negative case: repeated acknowledgement must not append
    operations = _operations(migrated_engine)
    notice_id = await operations.publish(
        title="Nhac lich hop",
        content="9h sang thu Hai",
        priority="NORMAL",
        created_by="admin-1",
    )

    # When
    await operations.mark_read(notice_id, advisor_id="advisor-a")
    await operations.mark_read(notice_id, advisor_id="advisor-a")

    # Then
    assert await _count_reads(migrated_engine) == 1


@pytest.mark.asyncio
async def test_marking_an_unknown_notice_is_rejected(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given — negative case: nothing published for this identifier
    operations = _operations(migrated_engine)

    # When / Then
    with pytest.raises(NoticeNotFoundError):
        await operations.mark_read(uuid4(), advisor_id="advisor-a")

    assert await _count_reads(migrated_engine) == 0


@pytest.mark.asyncio
async def test_listing_reports_read_state_per_advisor(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given
    operations = _operations(migrated_engine)
    notice_id = await operations.publish(
        title="Cap nhat bang gia",
        content="Xem phu luc",
        priority="URGENT",
        created_by="admin-1",
    )
    await operations.mark_read(notice_id, advisor_id="advisor-a")

    # When
    for_a = await operations.list_for(advisor_id="advisor-a")
    for_b = await operations.list_for(advisor_id="advisor-b")

    # Then
    assert [item.read for item in for_a] == [True]
    assert [item.read for item in for_b] == [False]
