"""Integration tests for Customer Assignment Center and Conversation Reassignment."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.adapters.assignment_repository import (
    AssignedCustomerSummaryDto,
    CustomerAssignmentDto,
)
from src.agents.api.admin_assignment_routes import router as admin_assignment_router
from src.agents.api.advisor_routes import router as advisor_routes_router
from src.agents.api.security import StaffIdentity, current_staff, require_staff
from src.auth.domain.authorization import Role


def _build_test_app(role: Role, staff_id: str, mock_assignments_op: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_assignment_router)
    app.include_router(advisor_routes_router)

    app.state.agent = SimpleNamespace(
        operations=SimpleNamespace(
            assignments=mock_assignments_op,
            review=SimpleNamespace(_unit_of_work=SimpleNamespace()),
        )
    )
    identity = StaffIdentity(staff_id=staff_id, role=role)
    app.dependency_overrides[current_staff] = lambda: identity
    app.dependency_overrides[require_staff] = lambda: identity
    return app


@pytest.mark.asyncio
async def test_admin_can_assign_customer() -> None:
    # Given
    mock_op = AsyncMock()
    assignment_id = uuid4()
    mock_op.assign_customer = AsyncMock(return_value=assignment_id)

    app = _build_test_app(role=Role.ADMIN, staff_id="admin-1", mock_assignments_op=mock_op)
    customer_id = "cust-123"

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/admin/customers/{customer_id}/assign",
            json={"advisor_id": "advisor-a", "reason": "VIP customer allocation"},
        )

    # Then
    assert res.status_code == 200
    data = res.json()
    assert data["assignment_id"] == str(assignment_id)
    assert data["customer_id"] == customer_id
    assert data["advisor_id"] == "advisor-a"
    assert data["status"] == "ACTIVE"
    mock_op.assign_customer.assert_awaited_once_with(
        customer_id=customer_id,
        advisor_id="advisor-a",
        assigned_by="admin-1",
        reason="VIP customer allocation",
    )


@pytest.mark.asyncio
async def test_advisor_cannot_assign_customer() -> None:
    # Given: authenticated as Advisor
    mock_op = AsyncMock()
    app = _build_test_app(role=Role.ADVISOR, staff_id="advisor-1", mock_assignments_op=mock_op)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/admin/customers/cust-123/assign",
            json={"advisor_id": "advisor-b"},
        )

    # Then: 403 Forbidden
    assert res.status_code == 403
    assert "Admin privileges required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_list_assignments() -> None:
    # Given
    mock_op = AsyncMock()
    now = datetime.now(UTC)
    mock_items = [
        CustomerAssignmentDto(
            assignment_id=uuid4(),
            customer_id="cust-1",
            advisor_id="adv-1",
            assigned_by="admin-1",
            reason="Territory",
            status="ACTIVE",
            assigned_at=now,
            unassigned_at=None,
            created_at=now,
        )
    ]
    mock_op.list_assignments = AsyncMock(return_value=(mock_items, 1))

    app = _build_test_app(role=Role.ADMIN, staff_id="admin-1", mock_assignments_op=mock_op)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/admin/customers/assignments?status=ACTIVE&page=1&page_size=20")

    # Then
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["customer_id"] == "cust-1"
    assert data["items"][0]["advisor_id"] == "adv-1"


@pytest.mark.asyncio
async def test_admin_can_reassign_conversation() -> None:
    # Given
    mock_op = AsyncMock()
    conv_id = uuid4()
    mock_op.reassign_conversation = AsyncMock(return_value=("advisor-old", "advisor-new"))

    app = _build_test_app(role=Role.ADMIN, staff_id="admin-1", mock_assignments_op=mock_op)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/admin/conversations/{conv_id}/reassign",
            json={"advisor_id": "advisor-new", "reason": "Advisor old offline"},
        )

    # Then
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == str(conv_id)
    assert data["previous_advisor_id"] == "advisor-old"
    assert data["new_advisor_id"] == "advisor-new"
    assert data["reassigned"] is True


@pytest.mark.asyncio
async def test_advisor_can_fetch_assigned_customers() -> None:
    # Given
    mock_op = AsyncMock()
    now = datetime.now(UTC)
    mock_cust = [
        AssignedCustomerSummaryDto(
            customer_id="cust-100",
            advisor_id="advisor-me",
            assigned_at=now,
            reason="Assigned by admin",
            status="ACTIVE",
            profile_payload={"name": "Nguyễn Văn A", "budget_vnd": 1000000000},
            active_conversations_count=2,
            last_activity_at=now,
        )
    ]
    mock_op.list_assigned_customers = AsyncMock(return_value=mock_cust)

    app = _build_test_app(role=Role.ADVISOR, staff_id="advisor-me", mock_assignments_op=mock_op)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/advisor/customers")

    # Then
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["customer_id"] == "cust-100"
    assert item["advisor_id"] == "advisor-me"
    assert item["profile_payload"]["name"] == "Nguyễn Văn A"
    assert item["active_conversations_count"] == 2
