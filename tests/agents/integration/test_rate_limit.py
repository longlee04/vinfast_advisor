"""[T7a] Spam lượt chết ở cửa API, không chết trong hàng duyệt.

Không có chốt này thì một script gửi 500 lượt "cho em gặp tư vấn viên" biến hàng
duyệt thành bãi rác — và cap PENDING (T7b) chỉ giấu triệu chứng, vì mỗi lượt vẫn
tốn một vòng pipeline đầy đủ. Chặn ở cửa là chỗ rẻ nhất.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api.dependencies import get_agent, get_current_customer_id
from src.agents.api.routes import router
from src.agents.services.registry import AgentServices

CUSTOMER_ID = "customer-spam"
TURNS_PER_WINDOW = 20


class _StubGraph:
    async def ainvoke(self, state: dict) -> dict:
        return {}


class _CountingLimiter:
    """Bộ đếm cửa sổ cố định trong bộ nhớ — cùng hợp đồng với bản Postgres."""

    def __init__(self, *, attempts: int = TURNS_PER_WINDOW) -> None:
        self.attempts = attempts
        self.seen: list[str] = []

    async def allow(self, key: str, *, now: datetime | None = None) -> bool:
        del now
        self.seen.append(key)
        return self.seen.count(key) <= self.attempts


class _StubAgent:
    def __init__(self, limiter: _CountingLimiter | None) -> None:
        self.graph = _StubGraph()
        self.services = AgentServices()
        self.rate_limiter = limiter


@pytest.fixture
def session_id() -> str:
    return str(uuid4())


def _app(limiter: _CountingLimiter | None) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_agent] = lambda: _StubAgent(limiter)
    application.dependency_overrides[get_current_customer_id] = lambda: CUSTOMER_ID
    return application


async def _post(client: AsyncClient, session_id: str) -> int:
    response = await client.post(
        "/api/v1/agent/turn",
        json={"session_id": session_id, "message": "cho em gap tu van vien"},
    )
    return response.status_code


@pytest.mark.asyncio
async def test_the_turn_after_the_limit_is_refused(session_id: str) -> None:
    limiter = _CountingLimiter()
    transport = ASGITransport(app=_app(limiter))

    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        statuses = [await _post(client, session_id) for _ in range(TURNS_PER_WINDOW + 1)]

    assert statuses[:TURNS_PER_WINDOW] == [200] * TURNS_PER_WINDOW, "duoi han muc phai chay binh thuong"
    assert statuses[TURNS_PER_WINDOW] == 429


@pytest.mark.asyncio
async def test_a_refused_turn_names_its_reason(session_id: str) -> None:
    """429 trần trụi không nói cho client biết nên đợi hay nên sửa request."""

    limiter = _CountingLimiter(attempts=1)
    transport = ASGITransport(app=_app(limiter))

    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        await _post(client, session_id)
        response = await client.post(
            "/api/v1/agent/turn",
            json={"session_id": session_id, "message": "cho em gap tu van vien"},
        )

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_two_customers_do_not_share_a_quota(session_id: str) -> None:
    """Khoá theo khách: một người spam không được làm câm người bên cạnh."""

    limiter = _CountingLimiter(attempts=1)
    application = _app(limiter)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        assert await _post(client, session_id) == 200
        application.dependency_overrides[get_current_customer_id] = lambda: "customer-khac"
        assert await _post(client, session_id) == 200


@pytest.mark.asyncio
async def test_a_missing_limiter_never_closes_the_door(session_id: str) -> None:
    """Chưa nối limiter (AGENT_ENABLED=false, test cũ) → lượt chạy như trước.

    Fail-open có chủ ý và ĐÃ CÂN NHẮC: limiter là chống lạm dụng, không phải
    chốt an toàn. Hạ tầng đếm chết mà làm câm cả sản phẩm là đổi một phiền toái
    lấy một sự cố.
    """

    transport = ASGITransport(app=_app(None))

    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        statuses = [await _post(client, session_id) for _ in range(TURNS_PER_WINDOW + 2)]

    assert set(statuses) == {200}


def test_fixed_window_counts_only_inside_its_own_window() -> None:
    """Cửa sổ CỐ ĐỊNH, cùng khuôn `PostgresRateLimiter` của auth.

    Ghi rõ vì nó có một tính chất phải biết trước: hai cửa sổ liền kề cho phép
    một cụm gấp đôi hạn mức quanh ranh giới. Chấp nhận được ở mức 20/phút, và
    đổi lấy một phép đếm nguyên tử bằng đúng một câu lệnh INSERT.
    """

    from src.agents.adapters.rate_limiter import window_start

    now = datetime(2026, 8, 24, 10, 0, 59, tzinfo=UTC)

    assert window_start(now, 60) == datetime(2026, 8, 24, 10, 0, 0, tzinfo=UTC)
    assert window_start(now + timedelta(seconds=1), 60) == datetime(2026, 8, 24, 10, 1, 0, tzinfo=UTC)
