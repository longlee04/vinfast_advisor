"""T12 — API `GET /agent/sales-opportunities` (C7).

Đi qua service thật + DB thật: màn Cơ hội bán hàng chỉ đáng tin nếu `bottlenecks`
và `snapshot` ra tới JSON đúng như service dựng, không phải như fake dựng.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.clock import SystemClock
from src.agents.api.sales_opportunity_routes import (
    router,
    sales_opportunity_service,
)
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import ConversationSessionRow
from src.agents.services.sales_opportunity import SalesOpportunityService
from src.auth.domain.authorization import Role
from tests.agents.integration.test_bottleneck_opportunity_query import _seed_signal

NOW = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)


class FakeTranscript:
    """Transcript/slots theo phiên — mô phỏng nút thắt khách nói ra."""

    def __init__(self, sessions: dict[str, list[str]]) -> None:
        self._sessions = sessions

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50):
        return [type("M", (), {"role": "USER", "content": text})() for text in self._sessions.get(session_id, [])]

    async def load_slots(self, session_id: str, customer_id: str) -> dict:
        return {}


class FrozenService:
    """Service thật, `at` cố định — route dùng đồng hồ hệ thống.

    Session mở/đóng gọn trong mỗi lượt đọc: giữ session sống qua nhiều request
    thì transaction treo và `TRUNCATE` khi dọn database sẽ chờ khoá vô hạn.
    """

    def __init__(self, session_factory: async_sessionmaker, transcript: FakeTranscript) -> None:
        self._session_factory = session_factory
        self._transcript = transcript

    async def list_opportunities(self, at: datetime, limit: int = 50):
        async with self._session_factory() as session:
            service = SalesOpportunityService(
                repository=SqlAlchemyBottleneckSignalRepository(session, clock=SystemClock()),
            )
            return await service.list_opportunities(NOW, limit)


async def _seed_session(
    engine: AsyncEngine,
    *,
    customer_id: str,
    last_activity_at: datetime,
    status: str = "ACTIVE",
) -> str:
    session_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id=customer_id,
                status=status,
                started_at=NOW,
                last_activity_at=last_activity_at,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return session_id


def _build_app(
    engine: AsyncEngine,
    transcript: FakeTranscript,
    *,
    identity: StaffIdentity | None = None,
    authenticated: bool = True,
) -> FastAPI:
    service = FrozenService(async_sessionmaker(engine, expire_on_commit=False), transcript)
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[sales_opportunity_service] = lambda: service
    if authenticated:
        application.dependency_overrides[current_staff] = lambda: (
            identity or StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
        )
    return application


async def _call(app: FastAPI, path: str) -> tuple[int, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(path)
    body = response.json() if response.content else None
    return response.status_code, body


# --- QA happy ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_sessions_with_two_bottlenecks(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    await _seed_session(migrated_engine, customer_id="c-a", last_activity_at=NOW)
    single = await _seed_session(migrated_engine, customer_id="c-b", last_activity_at=NOW)
    hot = await _seed_session(migrated_engine, customer_id="c-c", last_activity_at=NOW)
    await _seed_signal(migrated_engine, UUID(single), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(hot), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(hot), turn_number=2, label=Bottleneck.RANGE)
    app = _build_app(migrated_engine, FakeTranscript({}))

    code, body = await _call(app, "/agent/sales-opportunities")

    assert code == 200
    assert len(body) == 1
    row = body[0]
    assert row["session_id"] == hot
    assert row["customer_id"] == "c-c"
    assert set(row["bottlenecks"]) == {"PRICE", "RANGE"}
    assert {b["bottleneck"] for b in row["snapshot"]["bottlenecks"]} == {"PRICE", "RANGE"}
    assert row["snapshot"]["offer_state"] == "BOTTLENECK_NO_OFFER"
    assert row["last_active_at"].startswith("2026-08-19T09:00")


@pytest.mark.asyncio
async def test_list_orders_by_last_active_desc_and_honours_limit(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    older = await _seed_session(migrated_engine, customer_id="c-old", last_activity_at=NOW - timedelta(hours=3))
    newer = await _seed_session(migrated_engine, customer_id="c-new", last_activity_at=NOW - timedelta(minutes=5))
    await _seed_signal(migrated_engine, UUID(older), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(older), turn_number=2, label=Bottleneck.RANGE)
    await _seed_signal(migrated_engine, UUID(newer), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(newer), turn_number=2, label=Bottleneck.CHARGING)
    app = _build_app(migrated_engine, FakeTranscript({}))

    code, body = await _call(app, "/agent/sales-opportunities")

    assert code == 200
    assert [row["session_id"] for row in body] == [newer, older]

    code, body = await _call(app, "/agent/sales-opportunities?limit=1")

    assert code == 200
    assert [row["session_id"] for row in body] == [newer]


# --- QA failure -------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_role_is_forbidden(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    app = _build_app(
        migrated_engine,
        FakeTranscript({}),
        identity=StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER),
    )

    code, _ = await _call(app, "/agent/sales-opportunities")

    assert code == 403


@pytest.mark.asyncio
async def test_missing_staff_auth_is_unauthorized(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    app = _build_app(migrated_engine, FakeTranscript({}), authenticated=False)

    code, _ = await _call(app, "/agent/sales-opportunities")

    assert code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_out_of_range_is_bad_request(
    migrated_engine: AsyncEngine, clean_agent_database: None, limit: int
) -> None:
    app = _build_app(migrated_engine, FakeTranscript({}))

    code, _ = await _call(app, f"/agent/sales-opportunities?limit={limit}")

    assert code == 400
