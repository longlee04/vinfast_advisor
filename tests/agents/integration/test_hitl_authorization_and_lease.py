"""Integration tests for HITL Concurrency Claim, Ownership Resolve, Lease Expiry, and Admin Override."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.agents.services.operations.turn_events import TurnEvent
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
DRAFT = "Xe VF 8 dat tieu chuan an toan 5 sao"


class MockBroker:
    def __init__(self) -> None:
        self.events: list[TurnEvent] = []

    async def publish(self, event: TurnEvent) -> None:
        self.events.append(event)

    def subscribe(self, _session_id: UUID) -> AbstractAsyncContextManager[AsyncIterator[TurnEvent]]:
        raise NotImplementedError


class FrozenClock:
    def __init__(self, current_time: datetime = NOW) -> None:
        self.current_time = current_time

    def now(self) -> datetime:
        return self.current_time


async def _seed_review_item(
    engine: AsyncEngine,
    *,
    claimed_by: str | None = None,
    lease_expires_at: datetime | None = None,
    status: str = "PENDING",
) -> tuple[UUID, UUID]:
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
        claimed_at = NOW if claimed_by is not None else None
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=DRAFT,
                status=status,
                claimed_by=claimed_by,
                claimed_at=claimed_at,
                lease_expires_at=lease_expires_at,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id, session_id


def _build_test_app(
    engine: AsyncEngine,
    staff_id: str,
    role: Role,
    clock: FrozenClock,
) -> FastAPI:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=clock),
    )
    operations = ReviewOperations(unit_of_work=unit_of_work, broker=MockBroker())

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[review_operations] = lambda: operations
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id=staff_id, role=role)
    return application


@pytest.mark.asyncio
async def test_hitl_concurrency_claim(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given: A pending unassigned review item
    review_id, _ = await _seed_review_item(migrated_engine)
    clock = FrozenClock(NOW)

    app_advisor_a = _build_test_app(migrated_engine, "advisor-a", Role.ADVISOR, clock)
    app_advisor_b = _build_test_app(migrated_engine, "advisor-b", Role.ADVISOR, clock)

    # When: Advisor A claims first
    transport_a = ASGITransport(app=app_advisor_a)
    async with AsyncClient(transport=transport_a, base_url="http://test") as client_a:
        res_a = await client_a.post(f"/agent/review/{review_id}/claim")
    assert res_a.status_code == 200
    assert res_a.json() == {"granted": True, "rejection": None}

    # When: Advisor B tries to claim the same item while Advisor A holds lease
    transport_b = ASGITransport(app=app_advisor_b)
    async with AsyncClient(transport=transport_b, base_url="http://test") as client_b:
        res_b = await client_b.post(f"/agent/review/{review_id}/claim")
    assert res_b.status_code == 200
    assert res_b.json() == {"granted": False, "rejection": "ALREADY_CLAIMED"}


@pytest.mark.asyncio
async def test_hitl_resolve_denied_for_other_advisor(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given: Review item claimed by advisor-a
    lease_expires = NOW + timedelta(minutes=15)
    review_id, _ = await _seed_review_item(migrated_engine, claimed_by="advisor-a", lease_expires_at=lease_expires)
    clock = FrozenClock(NOW)

    app_advisor_b = _build_test_app(migrated_engine, "advisor-b", Role.ADVISOR, clock)
    transport_b = ASGITransport(app=app_advisor_b)

    # When: Advisor B tries to approve advisor-a's ticket
    async with AsyncClient(transport=transport_b, base_url="http://test") as client_b:
        res_approve = await client_b.post(f"/agent/review/{review_id}/approve", json={"edited_content": None})
    assert res_approve.status_code == 403
    assert "Mục duyệt này thuộc tư vấn viên khác" in res_approve.json()["detail"]

    # When: Advisor B tries to reject advisor-a's ticket
    async with AsyncClient(transport=transport_b, base_url="http://test") as client_b:
        res_reject = await client_b.post(f"/agent/review/{review_id}/reject")
    assert res_reject.status_code == 403
    assert "Mục duyệt này thuộc tư vấn viên khác" in res_reject.json()["detail"]


@pytest.mark.asyncio
async def test_hitl_resolve_denied_when_lease_expired(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given: Review item claimed by advisor-a with expired lease
    lease_expires = NOW - timedelta(minutes=1)
    review_id, _ = await _seed_review_item(migrated_engine, claimed_by="advisor-a", lease_expires_at=lease_expires)
    clock = FrozenClock(NOW)

    app_advisor_a = _build_test_app(migrated_engine, "advisor-a", Role.ADVISOR, clock)
    transport_a = ASGITransport(app=app_advisor_a)

    # When: Advisor A tries to approve after lease expired
    async with AsyncClient(transport=transport_a, base_url="http://test") as client_a:
        res = await client_a.post(f"/agent/review/{review_id}/approve", json={"edited_content": None})
    assert res.status_code == 409
    assert "Thời hạn 15 phút duyệt của mục này đã hết hạn" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_override_hitl_resolve(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given: Review item claimed by advisor-a
    lease_expires = NOW + timedelta(minutes=15)
    review_id, _ = await _seed_review_item(migrated_engine, claimed_by="advisor-a", lease_expires_at=lease_expires)
    clock = FrozenClock(NOW)

    app_admin = _build_test_app(migrated_engine, "admin-1", Role.ADMIN, clock)
    transport_admin = ASGITransport(app=app_admin)

    # When: Admin approves
    async with AsyncClient(transport=transport_admin, base_url="http://test") as client:
        res = await client.post(f"/agent/review/{review_id}/approve", json={"edited_content": None})
    assert res.status_code == 200
    assert res.json()["review_id"] == str(review_id)
