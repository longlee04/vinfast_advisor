"""Task 8 SSE contract for customer turn events."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api.customer_routes import customer_turn_events, turn_event_broker
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.review_routes import review_operations
from src.agents.services.operations.review import CustomerSessionForbiddenError
from src.agents.services.operations.turn_events import InMemoryTurnEventBroker, TurnEvent
from src.api.router import api_router

CUSTOMER_ID = "customer-1"


class FakeCustomerOperations:
    async def authorize_customer_session(self, session_id: UUID, customer_id: str) -> None:
        if customer_id != CUSTOMER_ID:
            raise CustomerSessionForbiddenError(str(session_id))


class OneShotBroker:
    @asynccontextmanager
    async def subscribe(self, session_id: UUID) -> AsyncIterator[AsyncIterator[TurnEvent]]:
        async def events() -> AsyncIterator[TurnEvent]:
            yield TurnEvent(session_id=session_id, review_id=uuid4(), kind="approved")

        yield events()


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[get_current_customer_id] = lambda: CUSTOMER_ID
    application.dependency_overrides[review_operations] = FakeCustomerOperations
    application.dependency_overrides[turn_event_broker] = lambda: InMemoryTurnEventBroker()
    return application


@pytest.mark.asyncio
async def test_customer_turn_events_authorize_before_opening_sse(app: FastAPI) -> None:
    # Given
    session_id = uuid4()
    app.dependency_overrides[get_current_customer_id] = lambda: None

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/events/{session_id}")

    # Then
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_http_customer_events_uses_broker_dependency_override(app: FastAPI) -> None:
    # Given
    session_id = uuid4()
    app.dependency_overrides[turn_event_broker] = lambda: OneShotBroker()

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/events/{session_id}")

    # Then
    assert response.status_code == 200
    # Hợp đồng T12: content-type + no-store phải ổn định, client dựa vào đó để
    # không cache một luồng sự kiện review đang chờ duyệt.
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    lines = response.text.splitlines()
    assert lines[0].startswith("id: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload["event_id"] == lines[0].removeprefix("id: ")
    assert payload["kind"] == "approved"
    assert payload["review_id"]
    # Hình dạng payload ổn định: đúng 5 khoá, không thừa không thiếu.
    assert set(payload.keys()) == {"event_id", "kind", "review_id", "client_turn_id", "message_id"}


@pytest.mark.asyncio
async def test_customer_turn_events_emit_durable_correlation_ids() -> None:
    # Given
    session_id = uuid4()
    review_id = uuid4()
    broker = InMemoryTurnEventBroker()

    # When
    response = await customer_turn_events(
        session_id=session_id,
        customer_id=CUSTOMER_ID,
        operations=FakeCustomerOperations(),
        broker=broker,
    )

    async def publish() -> None:
        await anyio.sleep(0)
        await broker.publish(TurnEvent(session_id=session_id, review_id=review_id, kind="approved"))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(publish)
        with anyio.fail_after(1):
            event_block = await anext(response.body_iterator)
        task_group.cancel_scope.cancel()
    await response.body_iterator.aclose()

    # Then
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    lines = event_block.splitlines()
    payload = json.loads(lines[1].removeprefix("data: ").strip())
    assert payload["event_id"] == lines[0].removeprefix("id: ")
    assert payload["review_id"] == str(review_id)
    assert payload["kind"] == "approved"
    assert payload["client_turn_id"] is None
    assert payload["message_id"] is None


@pytest.mark.asyncio
async def test_customer_turn_events_reject_other_customer_before_subscription(app: FastAPI) -> None:
    # Given
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-2"
    session_id = uuid4()

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/events/{session_id}")

    # Then
    assert response.status_code == 403
