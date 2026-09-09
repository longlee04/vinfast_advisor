"""Integration tests for Customer and Advisor WebSocket authorization."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.agents.api.security import StaffIdentity
from src.agents.api.ws_routes import router
from src.agents.errors import SessionOwnershipError
from src.agents.services.conversation import ConversationSummary
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


class FakeConversationService:
    def __init__(self, owner_id: str, assigned_advisor_id: str | None = None) -> None:
        self.owner_id = owner_id
        self.assigned_advisor_id = assigned_advisor_id

    async def list_messages(self, session_id: str, customer_id: str, limit: int = 100) -> list:
        if customer_id != self.owner_id:
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)
        return []

    async def staff_conversation_detail(
        self, session_id: str, *, requester_id: str, role: str
    ) -> tuple[ConversationSummary, list] | None:
        if role.lower() != "admin" and self.assigned_advisor_id != requester_id:
            return None
        summary = ConversationSummary(
            session_id=UUID(session_id),
            customer_id=self.owner_id,
            status="ACTIVE",
            assigned_advisor_id=self.assigned_advisor_id,
            last_activity_at=NOW,
        )
        return summary, []


def _build_ws_app(service: FakeConversationService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.agent = SimpleNamespace(services=SimpleNamespace(conversation=service))
    return app


def test_customer_ws_rejected_when_unauthenticated() -> None:
    """Không token/khong xác thực được: đóng ngay ở bước auth, không đụng ownership."""

    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1")
    app = _build_ws_app(service)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/conversations/{session_id}"):
                pass
        assert exc.value.code == 4001


def test_advisor_ws_rejected_when_unauthenticated() -> None:
    """Cùng mã lỗi 4001 cho phòng tư vấn viên khi thiếu/token không hợp lệ."""

    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1", assigned_advisor_id="advisor-a")
    app = _build_ws_app(service)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/advisor/conversations/{session_id}"):
                pass
        assert exc.value.code == 4001


def test_customer_ws_rejected_when_not_owner() -> None:
    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1")
    app = _build_ws_app(service)

    # When customer-2 tries to connect to customer-1's conversation
    with patch("src.agents.api.ws_routes.websocket_customer", new=AsyncMock(return_value="customer-2")):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(f"/ws/conversations/{session_id}"):
                    pass
            assert exc.value.code == 4003


def test_customer_ws_allowed_when_owner() -> None:
    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1")
    app = _build_ws_app(service)

    with patch("src.agents.api.ws_routes.websocket_customer", new=AsyncMock(return_value="customer-1")):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/conversations/{session_id}") as ws:
                ws.send_json({"type": "ping"})
                res = ws.receive_json()
                assert res == {"type": "pong"}


def test_advisor_ws_rejected_when_not_assigned() -> None:
    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1", assigned_advisor_id="advisor-a")
    app = _build_ws_app(service)

    # Advisor B tries to connect to Advisor A's assigned conversation
    with patch(
        "src.agents.api.ws_routes.websocket_staff",
        new=AsyncMock(return_value=StaffIdentity(staff_id="advisor-b", role=Role.ADVISOR)),
    ):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(f"/ws/advisor/conversations/{session_id}"):
                    pass
            assert exc.value.code == 4003


def test_advisor_ws_allowed_when_assigned() -> None:
    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1", assigned_advisor_id="advisor-a")
    app = _build_ws_app(service)

    with patch(
        "src.agents.api.ws_routes.websocket_staff",
        new=AsyncMock(return_value=StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/advisor/conversations/{session_id}") as ws:
                ws.send_json({"type": "ping"})
                res = ws.receive_json()
                assert res == {"type": "pong"}


def test_admin_ws_allowed_for_any_conversation() -> None:
    session_id = uuid4()
    service = FakeConversationService(owner_id="customer-1", assigned_advisor_id="advisor-a")
    app = _build_ws_app(service)

    # Admin connects to advisor-a's assigned conversation
    with patch(
        "src.agents.api.ws_routes.websocket_staff",
        new=AsyncMock(return_value=StaffIdentity(staff_id="admin-1", role=Role.ADMIN)),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/advisor/conversations/{session_id}") as ws:
                ws.send_json({"type": "ping"})
                res = ws.receive_json()
                assert res == {"type": "pong"}
