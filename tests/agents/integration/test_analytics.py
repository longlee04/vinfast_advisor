"""A9-1 — funnel dashboard endpoint with the 7-day / 30-day / custom filter."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.analytics_routes import analytics_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import ConversationSessionRow
from src.agents.services.operations.analytics import AnalyticsOperations
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


async def _seed_session_started_at(engine: AsyncEngine, started_at: datetime) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=uuid4(),
                customer_id=f"customer-{uuid4().hex[:8]}",
                started_at=started_at,
                last_activity_at=started_at,
                created_at=started_at,
                updated_at=started_at,
            )
        )


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FrozenClock(NOW)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=clock),
    )
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[analytics_operations] = lambda: AnalyticsOperations(
        unit_of_work=unit_of_work, clock=clock
    )
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="admin-1", role=Role.ADMIN)
    return application


async def _funnel(app: FastAPI, **params: Any) -> tuple[int, Any]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/agent/analytics/funnel", params=params)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_the_seven_day_window_leaves_out_older_sessions(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=2))
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=20))

    # When
    status_code, body = await _funnel(app, window="7d")

    # Then
    assert status_code == 200
    assert sum(row["sessions_started"] for row in body) == 1


@pytest.mark.asyncio
async def test_the_thirty_day_window_includes_both_sessions(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=2))
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=20))

    # When
    status_code, body = await _funnel(app, window="30d")

    # Then
    assert status_code == 200
    assert sum(row["sessions_started"] for row in body) == 2


@pytest.mark.asyncio
async def test_a_custom_range_uses_the_given_dates(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=2))
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=20))

    # When
    status_code, body = await _funnel(
        app,
        window="custom",
        date_from=(NOW - timedelta(days=25)).date().isoformat(),
        date_to=(NOW - timedelta(days=15)).date().isoformat(),
    )

    # Then
    assert status_code == 200
    assert sum(row["sessions_started"] for row in body) == 1


@pytest.mark.asyncio
async def test_a_custom_range_without_dates_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: custom means the caller must say which dates
    # When
    status_code, _body = await _funnel(app, window="custom")

    # Then
    assert status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_window_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case
    # When
    status_code, _body = await _funnel(app, window="1y")

    # Then
    assert status_code == 422


@pytest.mark.asyncio
async def test_an_empty_window_returns_an_empty_report(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: sessions exist, but all outside the window
    await _seed_session_started_at(migrated_engine, NOW - timedelta(days=90))

    # When
    status_code, body = await _funnel(app, window="7d")

    # Then
    assert status_code == 200
    assert body == []


@pytest.mark.asyncio
async def test_an_advisor_cannot_read_the_funnel_dashboard(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: the dashboard is an Admin screen
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)

    # When
    status_code, _body = await _funnel(app, window="7d")

    # Then
    assert status_code == 403
