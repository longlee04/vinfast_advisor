"""Repository phai liet ke duoc muc PENDING cho hang doi tu van vien."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import SqlAlchemyReviewQueueRepository
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(
    engine: AsyncEngine,
    *,
    status: str,
    content: str,
    created_at: datetime,
    claimed_by: str | None = None,
) -> UUID:
    session_id = uuid4()
    run_id = uuid4()
    review_id = uuid4()
    values: dict[str, object] = {
        "review_id": review_id,
        "session_id": session_id,
        "run_id": run_id,
        "content": content,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if claimed_by is not None:
        values |= {
            "claimed_by": claimed_by,
            "claimed_at": created_at,
            "lease_expires_at": created_at + timedelta(minutes=15),
        }
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
        await connection.execute(insert(ReviewQueueRow).values(**values))
    return review_id


@pytest.mark.asyncio
async def test_list_pending_returns_only_unresolved_items_oldest_first(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    newer = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Ban nhap moi hon",
        created_at=NOW + timedelta(minutes=5),
    )
    older = await _seed_review(migrated_engine, status="PENDING", content="Ban nhap cu hon", created_at=NOW)
    await _seed_review(migrated_engine, status="APPROVED", content="Da duyet", created_at=NOW)
    await _seed_review(migrated_engine, status="REJECTED", content="Da tu choi", created_at=NOW)

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await SqlAlchemyReviewQueueRepository(session, FrozenClock()).list_pending()

    # Then
    assert [entry.review_id for entry in entries] == [older, newer]
    assert [entry.content for entry in entries] == ["Ban nhap cu hon", "Ban nhap moi hon"]


@pytest.mark.asyncio
async def test_list_pending_reports_who_is_holding_the_lease(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    claimed = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Da co nguoi nhan",
        created_at=NOW,
        claimed_by="advisor-7",
    )

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await SqlAlchemyReviewQueueRepository(session, FrozenClock()).list_pending()

    # Then
    assert len(entries) == 1
    assert entries[0].review_id == claimed
    assert entries[0].claimed_by == "advisor-7"
    assert entries[0].lease_expires_at == NOW + timedelta(minutes=15)
