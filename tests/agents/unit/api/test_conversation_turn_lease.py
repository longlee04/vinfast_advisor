"""T1.7/T1.8: Route contract — POST busy/replay, GET recovery matrix."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import conversation_routes as routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.domain.conversation_memory import (
    CoreTurnLease,
    LeaseAcquired,
    TurnBusy,
)
from src.agents.errors import CoreTurnLeaseStaleError, CoreTurnTimeoutError


class FakeMemory:
    """begin_core_turn trả kết quả theo lập trình; assert_core_turn_lease có thể fail."""

    def __init__(
        self,
        begin_result: object | None = None,
        lease: CoreTurnLease | None = None,
        fail_assert: bool = False,
    ) -> None:
        self.begin_result = begin_result
        self.lease = lease
        self.fail_assert = fail_assert
        self.begin_called = False

    async def begin_core_turn(self, **kwargs: object) -> object:
        self.begin_called = True
        if self.begin_result is not None:
            return self.begin_result
        return LeaseAcquired(self.lease)

    async def assert_core_turn_lease(self, lease: CoreTurnLease) -> None:
        if self.fail_assert:
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason="lease_expired",
            )


class FakeConversations:
    def __init__(self, outcome: object | None = None) -> None:
        self.outcome = outcome

    async def detail(self, conversation_id: str, customer_id: str) -> object:
        return SimpleNamespace(state="ACTIVE")

    async def turn_outcome(self, conversation_id: str, customer_id: str, client_turn_id: str) -> object | None:
        return self.outcome


class FakeOperations:
    def __init__(self, outcome: object | None = None) -> None:
        self.conversations = FakeConversations(outcome)


def _client(*, memory: FakeMemory | None = None, graph: object = None, outcome: object | None = None) -> AsyncClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.state.agent = SimpleNamespace(
        operations=FakeOperations(outcome),
        services=SimpleNamespace(memory=memory) if memory else None,
        graph=graph,
    )
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_post_turn_busy_returns_409_turn_in_progress() -> None:
    memory = FakeMemory(
        begin_result=TurnBusy(retry_after_seconds=2, recovery_url="/api/v1/conversations/.../turns/...")
    )
    async with _client(memory=memory, graph=True) as client:
        response = await client.post(
            "/api/v1/conversations/00000000-0000-0000-0000-000000000001/turns",
            json={"client_turn_id": str(uuid4()), "message": "xe nào ưu đãi"},
        )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "TURN_IN_PROGRESS"
    assert "retry_after_seconds" in body
    assert "recovery_url" in body
    assert response.headers.get("retry-after") == "2" or response.headers.get("Retry-After") == "2"


@pytest.mark.asyncio
async def test_recovery_get_in_progress_returns_202() -> None:
    session_id = uuid4()
    client_turn_id = uuid4()
    outcome = SimpleNamespace(
        status=SimpleNamespace(value="IN_PROGRESS"),
        answer=None,
        pending_question=None,
        lookup_facts=(),
        terminal_reason=None,
        error_category=None,
        review_id=None,
    )
    async with _client(outcome=outcome) as client:
        response = await client.get(f"/api/v1/conversations/{session_id}/turns/{client_turn_id}")

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_recovery_get_completed_returns_200() -> None:
    session_id = uuid4()
    client_turn_id = uuid4()
    outcome = SimpleNamespace(
        status=SimpleNamespace(value="COMPLETED"),
        answer="câu trả lời cũ",
        pending_question=None,
        lookup_facts=(),
        terminal_reason="CATALOG_LOOKUP",
        error_category=None,
        review_id=None,
    )
    async with _client(outcome=outcome) as client:
        response = await client.get(f"/api/v1/conversations/{session_id}/turns/{client_turn_id}")

    assert response.status_code == 200
    assert response.json()["answer"] == "câu trả lời cũ"


@pytest.mark.asyncio
async def test_recovery_get_missing_returns_404() -> None:
    async with _client() as client:
        response = await client.get(f"/api/v1/conversations/{uuid4()}/turns/{uuid4()}")
    assert response.status_code == 404
    assert "TURN_NOT_FOUND" in response.text


@pytest.mark.asyncio
async def test_timeout_returns_503_turn_timeout() -> None:
    """Hard budget 20s hết → 503 TURN_TIMEOUT + Retry-After: 5; outcome IN_PROGRESS (không finalize FAILED)."""
    lease = CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=__import__("datetime").datetime(2026, 9, 1, tzinfo=__import__("zoneinfo").ZoneInfo("UTC")),
        lease_expires_at=__import__("datetime").datetime(2026, 9, 1, tzinfo=__import__("zoneinfo").ZoneInfo("UTC")),
    )
    memory = FakeMemory(lease=lease)
    original_run_turn = routes.run_turn

    async def _mock_run_turn(*args: object, **kwargs: object) -> object:
        raise CoreTurnTimeoutError(session_id=str(lease.session_id), client_turn_id=str(lease.client_turn_id))

    routes.run_turn = _mock_run_turn  # type: ignore[assignment]
    async with _client(memory=memory, graph=True) as client:
        response = await client.post(
            "/api/v1/conversations/00000000-0000-0000-0000-000000000001/turns",
            json={"client_turn_id": str(lease.client_turn_id), "message": "xe nào ưu đãi"},
        )

    routes.run_turn = original_run_turn
    assert response.status_code == 503, response.text
    body = response.json()["detail"]
    assert body["code"] == "TURN_TIMEOUT"
    assert body["client_turn_id"] == str(lease.client_turn_id)
    assert body["retry_after_seconds"] == 5
    assert response.headers.get("retry-after") == "5" or response.headers.get("Retry-After") == "5"
