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

    async def list_opportunities(self, **kwargs) -> list[dict]:  # noqa: ANN003
        self.calls.append(("list", kwargs))
        return []

    async def opportunity_summary(self, *, requester_ids, is_admin: bool) -> dict:  # noqa: ANN001
        if not self.enabled:
            raise Customer360DisabledError
        self.calls.append(("summary", tuple(requester_ids), is_admin))
        return {"hot": 2, "waiting": 1, "test_drives_48h": 1, "unanswered": 0}


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


@pytest.mark.asyncio
async def test_bo_loc_danh_sach_va_the_so_di_qua_pham_vi_tvv() -> None:
    reader = FakeReader()
    app = _app(Role.ADVISOR, "adv-1", reader)
    response = await _get(app, "/advisor/opportunities?waiting=true&has_test_drive=true&band=HOT")
    assert response.status_code == 200
    [(_, kwargs)] = [call for call in reader.calls if call[0] == "list"]
    assert kwargs["only_waiting"] and kwargs["only_test_drive"] and kwargs["band"] == "HOT"
    assert kwargs["is_admin"] is False and "adv-1" in kwargs["requester_ids"]

    summary = await _get(app, "/advisor/opportunities/summary")
    assert summary.json() == {"hot": 2, "waiting": 1, "test_drives_48h": 1, "unanswered": 0}
    assert ("summary", ("adv-1", "adv-1@x.vn"), False) in reader.calls
    assert (
        await _get(_app(Role.ADVISOR, "adv-1", FakeReader(enabled=False)), "/advisor/opportunities/summary")
    ).status_code == 503


class FakeOwnership:
    def __init__(self, outcome: str = "CLAIMED") -> None:
        self.outcome = outcome
        self.calls: list[tuple] = []

    async def claim(self, customer_id: str, *, advisor_id: str, requester_ids) -> object:  # noqa: ANN001
        from src.agents.domain.customer_ownership import ClaimOutcome
        from src.agents.services.operations.customer_ownership import ClaimResult

        self.calls.append(("claim", customer_id, advisor_id))
        return ClaimResult(ClaimOutcome(self.outcome), "adv-9" if self.outcome == "TAKEN" else advisor_id)

    async def release(self, customer_id: str, *, requester_ids) -> bool:  # noqa: ANN001
        self.calls.append(("release", customer_id))
        return "adv-1" in requester_ids

    async def pool(self, limit: int = 50) -> list[dict]:
        return [{"customer_id": "cust-9", "sessions_count": 2, "waiting": True}]


async def _post(app: FastAPI, path: str):  # noqa: ANN202
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.post(path)


def _ownership_app(role: Role, staff_id: str, ownership: FakeOwnership) -> FastAPI:
    from src.agents.api.customer_360_routes import customer_ownership_operations

    app = _app(role, staff_id, FakeReader())
    app.dependency_overrides[customer_ownership_operations] = lambda: ownership
    return app


@pytest.mark.asyncio
async def test_tu_van_vien_nhan_tra_khach_admin_chi_xem() -> None:
    ownership = FakeOwnership()
    advisor = _ownership_app(Role.ADVISOR, "adv-1", ownership)
    assert (await _get(advisor, "/advisor/customers/pool")).json()[0]["customer_id"] == "cust-9"
    claimed = await _post(advisor, "/advisor/customers/cust-9/claim")
    assert claimed.status_code == 200 and claimed.json()["outcome"] == "CLAIMED"
    assert (await _post(advisor, "/advisor/customers/cust-9/release")).status_code == 200

    other = _ownership_app(Role.ADVISOR, "adv-2", FakeOwnership("TAKEN"))
    assert (await _post(other, "/advisor/customers/cust-9/claim")).status_code == 409
    assert (await _post(other, "/advisor/customers/cust-9/release")).status_code == 403

    admin = _ownership_app(Role.ADMIN, "admin-1", ownership)
    assert (await _post(admin, "/advisor/customers/cust-9/claim")).status_code == 403
    assert (await _post(admin, "/advisor/customers/cust-9/release")).status_code == 403


class FakeOffers:
    def __init__(self) -> None:
        self.approved: list[tuple] = []

    async def list_pending(self) -> list[dict]:
        return [{"offer_id": "o1", "suggested_by": "adv-1"}]

    async def approve(self, offer_id: str, approver: str, approver_ids=()) -> object:  # noqa: ANN001
        from src.agents.domain.offer_lifecycle import SELF_APPROVAL, OfferStatus
        from src.agents.services.operations.opportunity_offers import OfferBlockedError, OfferView

        if "adv-1" in approver_ids:
            raise OfferBlockedError(SELF_APPROVAL)
        self.approved.append((offer_id, approver))
        return OfferView(offer_id, "O1", "cust-1", "T-HN", OfferStatus.APPROVED, 30_000_000, True)

    async def stats(self, promotion_code: str | None = None) -> list[dict]:
        return []


def _offer_app(role: Role, staff_id: str, offers: FakeOffers) -> FastAPI:
    from src.agents.api.customer_360_routes import opportunity_offer_operations

    app = _app(role, staff_id, FakeReader())
    app.dependency_overrides[opportunity_offer_operations] = lambda: offers
    return app


@pytest.mark.asyncio
async def test_duyet_cheo_uu_dai_giua_tu_van_vien_admin_khong_duyet() -> None:
    offer_id = "11111111-2222-3333-4444-555555555555"
    offers = FakeOffers()
    other = _offer_app(Role.ADVISOR, "adv-2", offers)
    assert (await _get(other, "/advisor/opportunity-offers/pending")).json()[0]["suggested_by"] == "adv-1"
    assert (await _post(other, f"/advisor/opportunity-offers/{offer_id}/approve")).status_code == 200
    assert offers.approved == [(offer_id, "adv-2")]
    assert (await _get(other, "/advisor/promotion-stats")).status_code == 200

    proposer = _offer_app(Role.ADVISOR, "adv-1", offers)
    assert (await _post(proposer, f"/advisor/opportunity-offers/{offer_id}/approve")).status_code == 403

    admin = _offer_app(Role.ADMIN, "admin-1", offers)
    assert (await _post(admin, f"/advisor/opportunity-offers/{offer_id}/approve")).status_code == 403
    assert (await _get(admin, "/advisor/opportunity-offers/pending")).status_code == 403
    assert (await _get(admin, "/advisor/promotion-stats")).status_code == 403
