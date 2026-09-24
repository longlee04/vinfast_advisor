"""Phase 0 Customer 360: TVV chỉ thấy phiên/khách của mình; SĐT bị che ở danh sách.

Trước bản vá, `list_staff_sessions` bỏ qua điều kiện lọc cho role `advisor` —
mọi TVV thấy toàn bộ phiên — và `GET /advisor/customers?advisor_id=X` cho bất kỳ
TVV nào xem khách của người khác.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.assignment_repository import AssignedCustomerSummaryDto
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.api.advisor_routes import router as advisor_router
from src.agents.api.security import StaffIdentity, current_staff, require_staff
from src.agents.models import (
    AgentRunRow,
    ConversationSessionRow,
    CustomerAdvisorAssignmentRow,
    ReviewQueueRow,
)
from src.auth.domain.authorization import Role

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _session(customer_id: str, *, assigned: str | None = None, ownership: str = "AI") -> ConversationSessionRow:
    return ConversationSessionRow(
        session_id=uuid4(),
        customer_id=customer_id,
        assigned_advisor_id=assigned,
        ownership=ownership,
        status="ACTIVE",
        started_at=NOW,
        last_activity_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


async def _seed(session: AsyncSession) -> dict[str, UUID]:
    rows = {
        "mine_direct": _session("cust-x", assigned="adv-1", ownership="HUMAN"),
        "assigned_customer": _session("cust-a"),
        "assigned_by_email": _session("cust-e"),
        "handoff_waiting": _session("cust-z", ownership="PENDING_HANDOFF"),
        "pending_review": _session("cust-r"),
        "other_advisor": _session("cust-b", assigned="adv-2", ownership="HUMAN"),
        "other_customer_ai": _session("cust-b"),
    }
    session.add_all(rows.values())
    session.add_all(
        [
            CustomerAdvisorAssignmentRow(
                assignment_id=uuid4(),
                customer_id=customer_id,
                advisor_id=advisor_id,
                assigned_by="admin-1",
                status=status,
                assigned_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
            for customer_id, advisor_id, status in (
                ("cust-a", "adv-1", "ACTIVE"),
                ("cust-e", "a1@x.vn", "ACTIVE"),
                ("cust-b", "adv-2", "ACTIVE"),
                ("cust-b", "adv-1", "UNASSIGNED"),
            )
        ]
    )
    await session.flush()
    run_id = uuid4()
    session.add(
        AgentRunRow(
            run_id=run_id,
            session_id=rows["pending_review"].session_id,
            state="PENDING_REVIEW",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await session.flush()
    session.add(
        ReviewQueueRow(
            review_id=uuid4(),
            session_id=rows["pending_review"].session_id,
            run_id=run_id,
            content="nháp",
            status="PENDING",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await session.flush()
    return {name: row.session_id for name, row in rows.items()}


@pytest.mark.asyncio
async def test_tvv_chi_thay_phien_trong_pham_vi(agent_session: AsyncSession) -> None:
    ids = await _seed(agent_session)
    repository = SqlAlchemySessionRepository(agent_session, FixedClock())

    visible = {
        row.session_id
        for row in await repository.list_staff_sessions(requester_id="adv-1", role="advisor", requester_email="a1@x.vn")
    }

    assert visible == {
        ids["mine_direct"],
        ids["assigned_customer"],
        ids["assigned_by_email"],
        ids["handoff_waiting"],
        ids["pending_review"],
    }
    assert await repository.staff_can_view(ids["assigned_customer"], requester_id="adv-1")
    assert not await repository.staff_can_view(ids["other_advisor"], requester_id="adv-1")
    assert not await repository.staff_can_view(ids["other_customer_ai"], requester_id="adv-1")


@pytest.mark.asyncio
async def test_admin_thay_moi_phien(agent_session: AsyncSession) -> None:
    ids = await _seed(agent_session)
    repository = SqlAlchemySessionRepository(agent_session, FixedClock())

    rows = await repository.list_staff_sessions(requester_id="admin-1", role="admin")

    assert {row.session_id for row in rows} == set(ids.values())


def _app(role: Role, staff_id: str, assignments: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(advisor_router)
    app.state.agent = SimpleNamespace(operations=SimpleNamespace(assignments=assignments))
    identity = StaffIdentity(staff_id=staff_id, role=role, email=f"{staff_id}@x.vn")
    app.dependency_overrides[current_staff] = lambda: identity
    app.dependency_overrides[require_staff] = lambda: identity
    return app


def _assignments() -> AsyncMock:
    operations = AsyncMock()
    operations.list_assigned_customers = AsyncMock(
        return_value=[
            AssignedCustomerSummaryDto(
                customer_id="cust-1",
                advisor_id="adv-2",
                assigned_at=NOW,
                reason=None,
                status="ACTIVE",
                profile_payload={"name": "Khách A", "phone": "0912345678"},
                active_conversations_count=1,
                last_activity_at=NOW,
            )
        ]
    )
    return operations


@pytest.mark.asyncio
async def test_tvv_khong_xem_duoc_khach_cua_tvv_khac() -> None:
    operations = _assignments()
    async with AsyncClient(
        transport=ASGITransport(app=_app(Role.ADVISOR, "adv-1", operations)), base_url="http://t"
    ) as c:
        response = await c.get("/advisor/customers", params={"advisor_id": "adv-2"})

    assert response.status_code == 403
    operations.list_assigned_customers.assert_not_called()


@pytest.mark.asyncio
async def test_admin_xem_khach_cua_tvv_khac_va_sdt_bi_che() -> None:
    operations = _assignments()
    async with AsyncClient(
        transport=ASGITransport(app=_app(Role.ADMIN, "admin-1", operations)), base_url="http://t"
    ) as c:
        response = await c.get("/advisor/customers", params={"advisor_id": "adv-2"})

    assert response.status_code == 200
    assert response.json()["items"][0]["profile_payload"]["phone"] == "0912***678"
