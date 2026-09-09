"""PostgreSQL behavior tests for session offer repository."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.session_offer_repository import SqlAlchemySessionOfferRepository

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
SESSION_ID = UUID("30000000-0000-0000-0000-000000000001")


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


async def _seed_session(session: AsyncSession, session_id: UUID = SESSION_ID) -> None:
    await session.execute(
        text(
            "INSERT INTO conversation_sessions (session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) VALUES (:id, 'customer', 'ACTIVE', :now, :now, :now, :now)"
        ),
        {"id": session_id, "now": NOW},
    )


@pytest.mark.asyncio
async def test_insert_then_active_for_session_returns_offer(agent_session: AsyncSession) -> None:
    await _seed_session(agent_session)
    repository = SqlAlchemySessionOfferRepository(agent_session, FixedClock())

    offer = await repository.insert(
        session_id=SESSION_ID,
        source_kind="BOTTLENECK_SIGNAL",
        promotion_code="PRICE-10",
        value_snapshot={"display_name": "Giảm 10 triệu", "amount_vnd": 10_000_000},
        approved_by="advisor-1",
        expires_at=None,
    )

    active = await repository.active_for_session(str(SESSION_ID))
    assert [o.offer_id for o in active] == [offer.offer_id]
    assert active[0].status == "ACTIVE"
    assert active[0].display_name == "Giảm 10 triệu"


@pytest.mark.asyncio
async def test_active_for_session_excludes_expired_and_other_session(agent_session: AsyncSession) -> None:
    await _seed_session(agent_session)
    other_id = UUID("30000000-0000-0000-0000-000000000002")
    await _seed_session(agent_session, other_id)
    repository = SqlAlchemySessionOfferRepository(agent_session, FixedClock())

    await repository.insert(
        session_id=SESSION_ID,
        source_kind="BOTTLENECK_SIGNAL",
        promotion_code="A",
        value_snapshot={"display_name": "a"},
        approved_by="advisor-1",
        expires_at=NOW + timedelta(days=7),
    )
    await repository.insert(
        session_id=SESSION_ID,
        source_kind="BOTTLENECK_SIGNAL",
        promotion_code="B",
        value_snapshot={"display_name": "b"},
        approved_by="advisor-1",
        expires_at=NOW - timedelta(days=1),
    )
    await repository.insert(
        session_id=other_id,
        source_kind="BOTTLENECK_SIGNAL",
        promotion_code="C",
        value_snapshot={"display_name": "c"},
        approved_by="advisor-1",
        expires_at=None,
    )

    active = await repository.active_for_session(str(SESSION_ID))
    assert [o.promotion_code for o in active] == ["A"]


@pytest.mark.asyncio
async def test_insert_status_is_always_active(agent_session: AsyncSession) -> None:
    await _seed_session(agent_session)
    repository = SqlAlchemySessionOfferRepository(agent_session, FixedClock())

    offer = await repository.insert(
        session_id=SESSION_ID,
        source_kind="CONTENT_REVIEW",
        promotion_code="REVIEW-1",
        value_snapshot={"display_name": "review offer"},
        approved_by="advisor-1",
        expires_at=None,
        source_review_id=UUID("30000000-0000-0000-0000-000000000003"),
    )

    assert offer.status == "ACTIVE"
    assert offer.source_kind == "CONTENT_REVIEW"
