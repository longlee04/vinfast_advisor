"""Integration tests for Conversation Delete Authorization (Admin only)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api.advisor_routes import router
from src.agents.api.security import StaffIdentity, current_staff
from src.auth.domain.authorization import Role


def _build_app(role: Role, staff_id: str, delete_result: bool = True) -> FastAPI:
    mock_service = AsyncMock()
    mock_service.staff_delete_conversation = AsyncMock(return_value=delete_result)

    app = FastAPI()
    app.include_router(router)
    app.state.agent = SimpleNamespace(services=SimpleNamespace(conversation=mock_service))
    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id=staff_id, role=role)
    return app


@pytest.mark.asyncio
async def test_advisor_cannot_delete_conversation() -> None:
    # Given: App authenticated as Advisor
    app = _build_app(role=Role.ADVISOR, staff_id="advisor-1")
    conv_id = uuid4()

    # When: Advisor requests DELETE /advisor/conversations/{id}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(f"/advisor/conversations/{conv_id}")

    # Then: HTTP 403 Forbidden
    assert res.status_code == 403
    assert "Admin privileges required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_delete_conversation() -> None:
    # Given: App authenticated as Admin
    app = _build_app(role=Role.ADMIN, staff_id="admin-1", delete_result=True)
    conv_id = uuid4()

    # When: Admin requests DELETE /advisor/conversations/{id}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(f"/advisor/conversations/{conv_id}")

    # Then: HTTP 200 OK with {"deleted": True}
    assert res.status_code == 200
    assert res.json() == {"deleted": True}
