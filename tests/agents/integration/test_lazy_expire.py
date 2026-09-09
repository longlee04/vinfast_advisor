"""[T13.5] Cờ tuổi hàng đợi + lazy expire mục PENDING quá hạn khi khách poll.

Không có cron: mốc quá hạn chỉ được thu hồi đúng lúc khách quay lại hỏi, nên
đường đọc của khách (`/agent/deliveries/{session_id}` và cửa uỷ quyền SSE) là
nơi duy nhất kích hoạt `expire_stale`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import (
    SqlAlchemyReviewQueueRepository,
    build_agent_transaction,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.review_routes import review_operations
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import (
    DEFAULT_PENDING_SLA_MINUTES,
    EXPIRED_CUSTOMER_MESSAGE,
    ReviewOperations,
    pending_sla_minutes,
)
from src.api.router import api_router

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
CUSTOMER_ID = "customer-1"


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(
    engine: AsyncEngine,
    *,
    status: str,
    content: str,
    created_at: datetime,
    session_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    resolved_session_id = session_id or uuid4()
    run_id = uuid4()
    review_id = uuid4()
    async with engine.begin() as connection:
        if session_id is None:
            await connection.execute(
                insert(ConversationSessionRow).values(
                    session_id=resolved_session_id,
                    customer_id=CUSTOMER_ID,
                    started_at=NOW,
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=resolved_session_id,
                state="PENDING_REVIEW",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=resolved_session_id,
                run_id=run_id,
                content=content,
                status=status,
                created_at=created_at,
                updated_at=created_at,
            )
        )
    return resolved_session_id, review_id


async def _status_of(engine: AsyncEngine, review_id: UUID) -> str:
    async with engine.begin() as connection:
        return await connection.scalar(select(ReviewQueueRow.status).where(ReviewQueueRow.review_id == review_id))


def _operations(engine: AsyncEngine) -> ReviewOperations:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    return ReviewOperations(unit_of_work)


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[get_current_customer_id] = lambda: CUSTOMER_ID
    application.dependency_overrides[review_operations] = lambda: _operations(migrated_engine)
    return application


async def _get(app: FastAPI, path: str) -> tuple[int, dict[str, object]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


# --- Cờ tuổi ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_reports_age_minutes_from_created_at(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    _session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Ban nhap cho duyet",
        created_at=NOW - timedelta(minutes=90),
    )

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await SqlAlchemyReviewQueueRepository(session, FrozenClock()).list_pending()

    # Then
    assert [entry.review_id for entry in entries] == [review_id]
    assert entries[0].age_minutes == 90


@pytest.mark.asyncio
async def test_list_by_status_reports_age_minutes(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given
    await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Vua vao hang doi",
        created_at=NOW,
    )
    await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Da cho 45 phut",
        created_at=NOW - timedelta(minutes=45),
    )

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await SqlAlchemyReviewQueueRepository(session, FrozenClock()).list_by_status(
            ("PENDING",), limit=50, offset=0
        )

    # Then
    assert [entry.age_minutes for entry in entries] == [45, 0]


@pytest.mark.asyncio
async def test_queue_entries_expose_age_minutes_to_the_advisor_screen(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Ban nhap cho duyet",
        created_at=NOW - timedelta(minutes=31),
    )

    # When
    entries = await _operations(migrated_engine).queue_entries()

    # Then
    assert [entry.age_minutes for entry in entries] == [31]


# --- Ngưỡng SLA ------------------------------------------------------------


def test_pending_sla_defaults_to_sixty_minutes() -> None:
    # Then
    assert DEFAULT_PENDING_SLA_MINUTES == 60
    assert pending_sla_minutes({}) == 60


def test_pending_sla_reads_environment_override() -> None:
    # Then
    assert pending_sla_minutes({"HITL_PENDING_SLA_MINUTES": "15"}) == 15


def test_pending_sla_ignores_unusable_override() -> None:
    # Then
    assert pending_sla_minutes({"HITL_PENDING_SLA_MINUTES": "khong-phai-so"}) == 60
    assert pending_sla_minutes({"HITL_PENDING_SLA_MINUTES": "0"}) == 60


# --- Lazy expire -----------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_poll_expires_pending_past_sla_and_returns_apology(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Ban nhap noi bo khong duoc lo",
        created_at=NOW - timedelta(minutes=90),
    )

    # When
    status_code, body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 200
    assert await _status_of(migrated_engine, review_id) == "EXPIRED"
    items = body["items"]
    assert [(item["review_id"], item["status"]) for item in items] == [(str(review_id), "EXPIRED")]
    assert items[0]["content"] == EXPIRED_CUSTOMER_MESSAGE
    assert "Ban nhap noi bo" not in items[0]["content"]


@pytest.mark.asyncio
async def test_customer_poll_keeps_pending_within_sla(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Moi vao hang doi 10 phut",
        created_at=NOW - timedelta(minutes=10),
    )

    # When
    status_code, body = await _get(app, f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert status_code == 200
    assert body["items"] == []
    assert await _status_of(migrated_engine, review_id) == "PENDING"


@pytest.mark.asyncio
async def test_pending_stays_pending_while_nobody_polls(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    _session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Qua han nhung khach chua quay lai",
        created_at=NOW - timedelta(minutes=90),
    )

    # When
    entries = await _operations(migrated_engine).queue_entries()

    # Then
    assert [entry.status for entry in entries] == ["PENDING"]
    assert await _status_of(migrated_engine, review_id) == "PENDING"


@pytest.mark.asyncio
async def test_sse_authorization_also_expires_stale_pending(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content="Ban nhap qua han",
        created_at=NOW - timedelta(minutes=90),
    )

    # When
    await _operations(migrated_engine).authorize_customer_session(session_id, CUSTOMER_ID)

    # Then
    assert await _status_of(migrated_engine, review_id) == "EXPIRED"


@pytest.mark.asyncio
async def test_expire_stale_leaves_already_resolved_items_alone(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    _session_id, approved_id = await _seed_review(
        migrated_engine,
        status="APPROVED",
        content="Da duyet tu lau",
        created_at=NOW - timedelta(minutes=180),
    )

    # When
    expired = await _operations(migrated_engine).expire_stale()

    # Then
    assert expired == []
    assert await _status_of(migrated_engine, approved_id) == "APPROVED"
