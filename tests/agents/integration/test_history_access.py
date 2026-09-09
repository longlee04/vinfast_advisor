"""A8-3 acceptance tests — advisory history is readable only by the right people."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.history_routes import history_operations, router
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.history import HistoryOperations
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


async def _seed_customer_handled_by(
    engine: AsyncEngine, customer_id: str, advisor_id: str, *, started_at: datetime = NOW
) -> UUID:
    """One customer whose queue item was processed by `advisor_id`."""
    session_id = uuid4()
    run_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id=customer_id,
                started_at=started_at,
                last_activity_at=started_at,
                created_at=started_at,
                updated_at=started_at,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="APPROVED",
                created_at=started_at,
                updated_at=started_at,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=uuid4(),
                session_id=session_id,
                run_id=run_id,
                content="ban nhap",
                status="APPROVED",
                advisor_id=advisor_id,
                processed_at=started_at,
                created_at=started_at,
                updated_at=started_at,
            )
        )
    return session_id


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    """Small app wired to the real service and the real database."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock(NOW)),
    )
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[history_operations] = lambda: HistoryOperations(unit_of_work=unit_of_work)
    return application


def _sign_in(app: FastAPI, staff_id: str, role: Role) -> None:
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id=staff_id, role=role)


async def _get_history(app: FastAPI, customer_id: str) -> tuple[int, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/agent/history/{customer_id}")
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_advisor_reading_another_advisors_customer_is_forbidden(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given — the main test of this task: customer-b belongs to advisor-b
    await _seed_customer_handled_by(migrated_engine, "customer-b", "advisor-b")
    _sign_in(app, "advisor-a", Role.ADVISOR)

    # When
    status_code, _ = await _get_history(app, "customer-b")

    # Then
    assert status_code == 403


@pytest.mark.asyncio
async def test_advisor_reads_their_own_customer(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_customer_handled_by(migrated_engine, "customer-a", "advisor-a")
    _sign_in(app, "advisor-a", Role.ADVISOR)

    # When
    status_code, body = await _get_history(app, "customer-a")

    # Then
    assert status_code == 200
    assert len(body) == 1


@pytest.mark.asyncio
async def test_customer_reads_their_own_history(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_customer_handled_by(migrated_engine, "customer-a", "advisor-a")
    _sign_in(app, "customer-a", Role.CUSTOMER)

    # When
    status_code, _ = await _get_history(app, "customer-a")

    # Then
    assert status_code == 200


@pytest.mark.asyncio
async def test_customer_reading_another_customer_is_forbidden(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: customers are not staff
    await _seed_customer_handled_by(migrated_engine, "customer-b", "advisor-b")
    _sign_in(app, "customer-a", Role.CUSTOMER)

    # When
    status_code, _ = await _get_history(app, "customer-b")

    # Then
    assert status_code == 403


@pytest.mark.asyncio
async def test_admin_reads_any_customer(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_customer_handled_by(migrated_engine, "customer-b", "advisor-b")
    _sign_in(app, "admin-1", Role.ADMIN)

    # When
    status_code, _ = await _get_history(app, "customer-b")

    # Then
    assert status_code == 200


@pytest.mark.asyncio
async def test_history_is_sorted_with_the_most_recent_session_first(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    await _seed_customer_handled_by(migrated_engine, "customer-a", "advisor-a", started_at=NOW - timedelta(days=2))
    await _seed_customer_handled_by(migrated_engine, "customer-a", "advisor-a", started_at=NOW)
    _sign_in(app, "advisor-a", Role.ADVISOR)

    # When
    _, body = await _get_history(app, "customer-a")

    # Then
    started = [item["started_at"] for item in body]
    assert started == sorted(started, reverse=True)


@pytest.mark.asyncio
async def test_history_of_an_unknown_customer_is_empty_for_admin(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: nothing seeded at all
    _sign_in(app, "admin-1", Role.ADMIN)

    # When
    status_code, body = await _get_history(app, "khong-ton-tai")

    # Then
    assert status_code == 200
    assert body == []
