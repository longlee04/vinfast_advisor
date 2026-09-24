"""Customer 360 HTTP: quyền advisor/admin, cờ tắt, Tách/Gộp — với use case giả."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api.customer_360_routes import (
    admin_router,
    advisor_router,
    customer_360_operations,
    customer_360_read_operations,
    meta_router,
)
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.services.operations.customer_360_read import Customer360DisabledError, CustomerAccessDeniedError
from src.auth.domain.authorization import Role


class FakeReader:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls: list[tuple] = []

    async def overview(self, customer_id: str, *, requester_ids, is_admin: bool) -> dict:  # noqa: ANN001
        if not self.enabled:
            raise Customer360DisabledError
        if not is_admin and "adv-1" not in requester_ids:
            raise CustomerAccessDeniedError
        customer = {"customer_id": customer_id, "phone_masked": "0912***678"}
        if not is_admin:
            customer["phone"] = "0912345678"
        return {"customer": customer, "opportunities": [], "sessions": [], "test_drives": []}

    async def check_access(self, kind: str, ref: str, *, requester_ids, is_admin: bool) -> str | None:  # noqa: ANN001
        self.calls.append((kind, ref))
        if "adv-1" not in requester_ids:
            raise CustomerAccessDeniedError
        return "cust-1"

    async def meta(self) -> dict:
        return {"enabled": {"ui": self.enabled}}


class FakeOperations:
    def __init__(self) -> None:
        self.moves: list[tuple] = []

    async def move_session(self, session_id: str, target: str | None, actor: str) -> str:
        self.moves.append((session_id, target, actor))
        return "opp-new"


def _app(role: Role, staff_id: str, reader: FakeReader, operations: FakeOperations | None = None) -> FastAPI:
    app = FastAPI()
    for router in (advisor_router, admin_router, meta_router):
        app.include_router(router)
    identity = StaffIdentity(staff_id=staff_id, role=role, email=f"{staff_id}@x.vn")
    app.dependency_overrides[current_staff] = lambda: identity
    app.dependency_overrides[customer_360_read_operations] = lambda: reader
    app.dependency_overrides[customer_360_operations] = lambda: operations or FakeOperations()
    return app


async def _get(app: FastAPI, path: str):  # noqa: ANN202
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_tvv_phu_trach_thay_sdt_tvv_khac_bi_403_admin_chi_thay_ban_che() -> None:
    reader = FakeReader()
    mine = await _get(_app(Role.ADVISOR, "adv-1", reader), "/advisor/customers/cust-1/overview")
    other = await _get(_app(Role.ADVISOR, "adv-9", reader), "/advisor/customers/cust-1/overview")
    admin = await _get(_app(Role.ADMIN, "admin-1", reader), "/admin/customers/cust-1/overview")

    assert mine.status_code == 200 and mine.json()["customer"]["phone"] == "0912345678"
    assert other.status_code == 403
    assert admin.status_code == 200 and "phone" not in admin.json()["customer"]
    advisor_on_admin = await _get(_app(Role.ADVISOR, "adv-1", reader), "/admin/customers/cust-1/overview")
    assert advisor_on_admin.status_code == 403


@pytest.mark.asyncio
async def test_co_tat_tra_503_de_frontend_dung_man_du_phong() -> None:
    reader = FakeReader(enabled=False)
    response = await _get(_app(Role.ADVISOR, "adv-1", reader), "/advisor/customers/cust-1/overview")
    meta = await _get(_app(Role.ADVISOR, "adv-1", reader), "/agent/customer-360/meta")

    assert response.status_code == 503
    assert meta.json() == {"enabled": {"ui": False}}


@pytest.mark.asyncio
async def test_tach_gop_chi_tvv_phu_trach_admin_chi_doc() -> None:
    session_id = str(uuid4())
    operations = FakeOperations()
    async with AsyncClient(
        transport=ASGITransport(app=_app(Role.ADVISOR, "adv-1", FakeReader(), operations)), base_url="http://t"
    ) as client:
        split = await client.post(f"/advisor/sessions/{session_id}/opportunity", json={"action": "SPLIT"})
        missing = await client.post(f"/advisor/sessions/{session_id}/opportunity", json={"action": "MOVE"})
        bad_id = await client.post("/advisor/sessions/not-a-uuid/opportunity", json={"action": "SPLIT"})
    async with AsyncClient(
        transport=ASGITransport(app=_app(Role.ADMIN, "admin-1", FakeReader(), operations)), base_url="http://t"
    ) as client:
        admin = await client.post(f"/advisor/sessions/{session_id}/opportunity", json={"action": "SPLIT"})

    assert split.status_code == 200 and split.json() == {
        "session_id": session_id,
        "opportunity_id": "opp-new",
        "decided_by": "ADVISOR",
    }
    assert operations.moves == [(session_id, None, "adv-1")]
    assert missing.status_code == 422 and bad_id.status_code == 422
    assert admin.status_code == 403
