"""Hop dong HTTP cho man hang doi duyet cua tu van vien."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.review_routes import review_operations
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.api.router import api_router
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(engine: AsyncEngine, *, status: str, content: str) -> UUID:
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
                content=content,
                status=status,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return review_id


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(unit_of_work)
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-1", role=Role.ADVISOR)
    return application


@pytest.mark.asyncio
async def test_advisor_sees_only_pending_items_with_draft_content(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    pending_id = await _seed_review(migrated_engine, status="PENDING", content="Ban nhap cho duyet")
    await _seed_review(migrated_engine, status="APPROVED", content="Da duyet")

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/api/v1/agent/review")

    # Then
    assert response.status_code == 200
    body = response.json()
    assert [item["review_id"] for item in body] == [str(pending_id)]
    assert body[0]["content"] == "Ban nhap cho duyet"
    assert body[0]["status"] == "PENDING"
    assert body[0]["claimed_by"] is None


@pytest.mark.asyncio
async def test_customer_role_cannot_read_the_review_queue(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    await _seed_review(migrated_engine, status="PENDING", content="Ban nhap cho duyet")
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/api/v1/agent/review")

    # Then
    assert response.status_code == 403
