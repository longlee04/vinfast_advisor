from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import routes as legacy_routes
from src.agents.api.conversation_routes import router
from src.agents.api.dependencies import get_current_customer_id
from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationPage,
    ConversationState,
    MessagePage,
    TurnOutcome,
    TurnOutcomeStatus,
)
from src.agents.errors import ConversationArchivedError
from src.agents.services.registry import AgentServices

NOW = datetime(2026, 8, 15, tzinfo=UTC)


class Lifecycle:
    def __init__(self) -> None:
        self.conversation = Conversation(
            conversation_id=uuid4(),
            customer_id="customer-1",
            state=ConversationState.ACTIVE,
            created_at=NOW,
            last_activity_at=NOW,
        )

    async def create(self, customer_id: str) -> Conversation:
        assert customer_id == "customer-1"
        return self.conversation

    async def list_owned(self, customer_id: str, **kwargs: object) -> ConversationPage:
        assert customer_id == "customer-1"
        return ConversationPage((self.conversation,), int(kwargs["limit"]))

    async def detail(self, conversation_id: UUID, customer_id: str) -> Conversation:
        assert conversation_id == self.conversation.conversation_id
        assert customer_id == "customer-1"
        return self.conversation

    async def messages(self, conversation_id: UUID, customer_id: str, **kwargs: object) -> MessagePage:
        del conversation_id, customer_id
        return MessagePage((), int(kwargs["limit"]))

    async def archive(self, conversation_id: UUID, customer_id: str) -> Conversation:
        del conversation_id, customer_id
        return Conversation(
            conversation_id=self.conversation.conversation_id,
            customer_id="customer-1",
            state=ConversationState.ARCHIVED,
            created_at=NOW,
            last_activity_at=NOW,
            archived_at=NOW,
        )

    async def delete(self, conversation_id: UUID, customer_id: str) -> None:
        del conversation_id, customer_id

    async def turn_outcome(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome:
        assert conversation_id == self.conversation.conversation_id
        assert customer_id == "customer-1"
        return TurnOutcome(
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=1,
            status=TurnOutcomeStatus.COMPLETED,
            answer="Kết quả đã lưu.",
        )


class Graph:
    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        return {**state, "answer": "Câu trả lời bền vững."}


@pytest.fixture
def app() -> tuple[FastAPI, Lifecycle]:
    lifecycle = Lifecycle()
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(
        operations=SimpleNamespace(conversations=lifecycle),
        graph=Graph(),
        services=AgentServices(),
    )
    application.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    return application, lifecycle


@pytest.mark.asyncio
async def test_create_list_detail_and_turn_contract(
    app: tuple[FastAPI, Lifecycle],
) -> None:
    application, lifecycle = app
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/conversations")
        listed = await client.get("/api/v1/conversations?limit=20")
        detail = await client.get(f"/api/v1/conversations/{lifecycle.conversation.conversation_id}")
        client_turn_id = uuid4()
        turn = await client.post(
            f"/api/v1/conversations/{lifecycle.conversation.conversation_id}/turns",
            json={"client_turn_id": str(client_turn_id), "message": "Xin tư vấn VF 7"},
        )

    assert created.status_code == 201
    assert created.json()["conversation_id"] == str(lifecycle.conversation.conversation_id)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["state"] == "ACTIVE"
    assert detail.status_code == 200
    assert turn.status_code == 200
    assert turn.json() == {
        "conversation_id": str(lifecycle.conversation.conversation_id),
        "client_turn_id": str(client_turn_id),
        "status": "COMPLETED",
        "answer": "Câu trả lời bền vững.",
        "pending_question": None,
        "lookup_facts": [],
        "terminal_reason": None,
        "review_id": None,
    }


@pytest.mark.asyncio
async def test_conversation_api_requires_authentication() -> None:
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(
        operations=SimpleNamespace(conversations=Lifecycle()),
        graph=Graph(),
        services=AgentServices(),
    )
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/conversations")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "AUTHENTICATION_REQUIRED"}}


@pytest.mark.asyncio
async def test_recover_turn_returns_durable_result(
    app: tuple[FastAPI, Lifecycle],
) -> None:
    application, lifecycle = app
    client_turn_id = uuid4()
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/conversations/{lifecycle.conversation.conversation_id}/turns/{client_turn_id}"
        )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": str(lifecycle.conversation.conversation_id),
        "client_turn_id": str(client_turn_id),
        "status": "COMPLETED",
        "answer": "Kết quả đã lưu.",
        "pending_question": None,
        "lookup_facts": [],
        "terminal_reason": None,
        "review_id": None,
    }


@pytest.mark.asyncio
async def test_legacy_turn_returns_conflict_for_archived_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def archived_turn(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ConversationArchivedError("archived")

    monkeypatch.setattr(legacy_routes, "run_turn", archived_turn)
    application = FastAPI()
    application.include_router(legacy_routes.router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(graph=Graph(), services=AgentServices())
    application.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/turn",
            json={"session_id": str(uuid4()), "message": "Tiếp tục"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "CONVERSATION_ARCHIVED"}}
