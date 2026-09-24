"""HTTP cho hồ sơ khách 360 (plan Customer 360, Phase 4 mục 5).

Ba router, một nguồn dữ liệu:
- `/advisor/...`: TVV (chỉ khách được giao) và Admin (xem tất cả, chỉ đọc).
- `/admin/...`: hồ sơ chỉ đọc, số liệu dashboard, picker khách cho màn phân công.
- `/agent/customer-360/meta`: cờ + enum để frontend biết dùng màn mới hay màn dự phòng.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.security import StaffIdentity, require_admin, require_staff
from src.agents.domain.offer_lifecycle import SELF_APPROVAL, OfferStatus, OfferTransitionError
from src.agents.domain.staff_access import is_admin, staff_identifiers
from src.agents.services.operations.customer_360 import Customer360Operations
from src.agents.services.operations.customer_360_read import (
    Customer360DisabledError,
    Customer360ReadOperations,
    CustomerAccessDeniedError,
)
from src.agents.services.operations.customer_ownership import CustomerOwnershipOperations
from src.agents.services.operations.opportunity_offers import (
    OfferBlockedError,
    OffersDisabledError,
    OpportunityOfferOperations,
)

advisor_router = APIRouter(prefix="/advisor", tags=["customer-360"])
admin_router = APIRouter(prefix="/admin", tags=["customer-360-admin"])
meta_router = APIRouter(prefix="/agent/customer-360", tags=["customer-360"])

_DISABLED = "Customer 360 chưa được bật"
_FORBIDDEN = "Khách hàng không thuộc phạm vi phụ trách"


def customer_360_read_operations() -> Customer360ReadOperations:
    """Điểm nối use case — `main._wire_agent_operations` ghi đè bằng bản có DB."""
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa nối Customer 360")


def customer_360_operations() -> Customer360Operations:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa nối Customer 360")


def customer_ownership_operations() -> CustomerOwnershipOperations | None:
    """Nhận/trả khách — `main` ghi đè. `None` (chưa nối) thì tiếp quản vẫn chạy, chỉ không gán khách."""
    return None


def opportunity_offer_operations() -> OpportunityOfferOperations:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa nối ưu đãi theo cơ hội")


class CreateOfferRequest(BaseModel):
    promotion_code: str = Field(min_length=1, max_length=100)
    #: Điều chỉnh của TVV (amount_vnd/percent/months/gift_code) — cùng hình `OfferAdjustment`.
    proposed_value: dict[str, Any] = Field(default_factory=dict)


class OfferResponse(BaseModel):
    offer_id: str
    opportunity_id: str
    promotion_code: str
    status: str
    discount_vnd: int | None = None
    needs_manager_approval: bool = False


class MoveSessionRequest(BaseModel):
    action: Literal["MOVE", "SPLIT"]
    opportunity_id: UUID | None = None


class MoveSessionResponse(BaseModel):
    session_id: str
    opportunity_id: str
    decided_by: Literal["ADVISOR"] = "ADVISOR"


class InsightFeedbackRequest(BaseModel):
    verdict: Literal["WRONG", "OK"]
    note: str | None = Field(default=None, max_length=500)


class OpportunityListItem(BaseModel):
    opportunity_id: str
    customer_id: str
    display_name: str | None = None
    assigned_advisor_id: str | None = None
    vehicle_type: str | None = None
    buyer_for: str
    status: str
    stage: str
    heat_score: int
    heat_band: str
    slots: dict[str, Any] = Field(default_factory=dict)
    barriers: list[str] = Field(default_factory=list)
    needs_review: bool = False
    last_seen_at: datetime
    # Màn "Khách cần xử lý" (mockup 01) — chỉ THÊM trường, trường cũ giữ nguyên.
    sessions_count: int = 0
    has_phone: bool = False
    #: Khách đang chờ người thật (phiên ACTIVE, ownership PENDING_HANDOFF).
    waiting: bool = False
    has_test_drive: bool = False
    booking_requested: bool = False
    #: Xe đứng đầu thẻ đề xuất gần nhất — tên chép từ thẻ đã gửi khách.
    top_vehicle_name: str | None = None
    #: Việc đầu tiên trong "Việc cần làm" của hồ sơ (cùng hàm domain).
    next_action: dict[str, str] | None = None


class PoolItem(BaseModel):
    customer_id: str
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    sessions_count: int
    last_seen_at: datetime | None = None
    waiting: bool = False
    heat_band: str | None = None
    heat_score: int | None = None
    stage: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)


class ClaimResponse(BaseModel):
    outcome: Literal["CLAIMED", "ALREADY_MINE"]
    customer_id: str


class MyCustomerItem(BaseModel):
    """Một khách đang phụ trách (tab "Đã nhận"). Trường cơ hội rỗng khi khách chưa có nhu cầu."""

    customer_id: str
    display_name: str | None = None
    email: str | None = None
    assigned_advisor_id: str | None = None
    assigned_at: datetime | None = None
    opportunity_id: str | None = None
    vehicle_type: str | None = None
    buyer_for: str | None = None
    status: str | None = None
    stage: str | None = None
    heat_score: int | None = None
    heat_band: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)
    barriers: list[str] = Field(default_factory=list)
    needs_review: bool = False
    last_seen_at: datetime | None = None
    sessions_count: int = 0
    has_phone: bool = False
    waiting: bool = False
    has_test_drive: bool = False
    booking_requested: bool = False
    top_vehicle_name: str | None = None
    next_action: dict[str, str] | None = None


class OpportunitySummary(BaseModel):
    hot: int
    waiting: int
    test_drives_48h: int
    #: Câu AI không trả lời được (MISSING_DATA/OUT_OF_SCOPE) trong 7 ngày gần nhất.
    unanswered: int


class CustomerPickerItem(BaseModel):
    customer_id: str
    display_name: str | None = None
    phone: str | None = None
    advisor_id: str | None = None
    last_seen_at: datetime | None = None
    sessions_count: int = 0
    heat_band: str | None = None
    heat_score: int | None = None


def _ids(identity: StaffIdentity) -> tuple[str, ...]:
    return staff_identifiers(identity.staff_id, identity.email)


def _admin(identity: StaffIdentity) -> bool:
    return is_admin(identity.role.value)


async def _overview(customer_id: str, identity: StaffIdentity, operations: Customer360ReadOperations) -> dict:
    try:
        return await operations.overview(customer_id, requester_ids=_ids(identity), is_admin=_admin(identity))
    except Customer360DisabledError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED) from error
    except CustomerAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from error


@advisor_router.get("/customers/{customer_id}/overview")
async def advisor_customer_overview(
    customer_id: str,
    identity: StaffIdentity = Depends(require_staff),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> dict:
    """Hồ sơ khách 360 — ≤ 3 câu SQL. TVV phụ trách thấy SĐT đầy đủ."""
    return await _overview(customer_id, identity, operations)


@admin_router.get("/customers/{customer_id}/overview")
async def admin_customer_overview(
    customer_id: str,
    identity: StaffIdentity = Depends(require_admin),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> dict:
    """Hồ sơ chỉ đọc cho Admin — SĐT luôn bị che."""
    return await _overview(customer_id, identity, operations)


def _ownership(operations: CustomerOwnershipOperations | None) -> CustomerOwnershipOperations:
    if operations is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa nối nhận khách")
    return operations


def _advisor_only(identity: StaffIdentity) -> None:
    # Admin lo kỹ thuật, chỉ xem — người phụ trách khách luôn là tư vấn viên.
    if _admin(identity):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin chỉ xem, không nhận khách")


@advisor_router.get("/customers/mine", response_model=list[MyCustomerItem])
async def my_customers(
    band: Literal["HOT", "WARM", "COLD"] | None = None,
    waiting: bool = False,
    has_test_drive: bool = False,
    limit: int = Query(200, ge=1, le=500),
    identity: StaffIdentity = Depends(require_staff),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> list[MyCustomerItem]:
    """Tab "Đã nhận": mọi khách đang phụ trách (có cơ hội hay chưa), khách đang chờ người lên trước."""
    try:
        rows = await operations.list_my_customers(
            requester_ids=_ids(identity),
            is_admin=_admin(identity),
            band=band,
            limit=limit,
            only_waiting=waiting,
            only_test_drive=has_test_drive,
        )
    except Customer360DisabledError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED) from error
    return [MyCustomerItem(**row) for row in rows]


@advisor_router.get("/customers/pool", response_model=list[PoolItem])
async def customer_pool(
    limit: int = Query(50, ge=1, le=200),
    identity: StaffIdentity = Depends(require_staff),
    operations: CustomerOwnershipOperations | None = Depends(customer_ownership_operations),
) -> list[PoolItem]:
    """Hàng chờ khách chưa ai phụ trách: khách đang chờ người trước, rồi nóng nhất."""
    return [PoolItem(**row) for row in await _ownership(operations).pool(limit)]


@advisor_router.post("/customers/{customer_id}/claim", response_model=ClaimResponse)
async def claim_customer(
    customer_id: str,
    identity: StaffIdentity = Depends(require_staff),
    operations: CustomerOwnershipOperations | None = Depends(customer_ownership_operations),
) -> ClaimResponse:
    """Nhận khách từ hàng chờ. Người khác đã nhận trước → 409."""
    _advisor_only(identity)
    result = await _ownership(operations).claim(customer_id, advisor_id=identity.staff_id, requester_ids=_ids(identity))
    if result.outcome.value == "TAKEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Khách đã có tư vấn viên khác phụ trách")
    return ClaimResponse(outcome=result.outcome.value, customer_id=customer_id)


@advisor_router.post("/customers/{customer_id}/release")
async def release_customer(
    customer_id: str,
    identity: StaffIdentity = Depends(require_staff),
    operations: CustomerOwnershipOperations | None = Depends(customer_ownership_operations),
) -> dict[str, bool]:
    """Người đang phụ trách trả khách về hàng chờ. Không phải người phụ trách → 403."""
    _advisor_only(identity)
    if not await _ownership(operations).release(customer_id, requester_ids=_ids(identity)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)
    return {"released": True}


@advisor_router.get("/opportunities/summary", response_model=OpportunitySummary)
async def opportunity_summary(
    identity: StaffIdentity = Depends(require_staff),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> OpportunitySummary:
    """Bốn thẻ số màn "Khách cần xử lý". TVV: chỉ khách được giao."""
    try:
        counts = await operations.opportunity_summary(requester_ids=_ids(identity), is_admin=_admin(identity))
    except Customer360DisabledError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED) from error
    return OpportunitySummary(**counts)


@advisor_router.get("/opportunities", response_model=list[OpportunityListItem])
async def list_opportunities(
    band: Literal["HOT", "WARM", "COLD"] | None = None,
    waiting: bool = False,
    has_test_drive: bool = False,
    limit: int = Query(50, ge=1, le=200),
    identity: StaffIdentity = Depends(require_staff),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> list[OpportunityListItem]:
    """Cơ hội bán hàng theo đơn vị CƠ HỘI, nóng nhất trước. TVV: chỉ khách được giao."""
    try:
        rows = await operations.list_opportunities(
            requester_ids=_ids(identity),
            is_admin=_admin(identity),
            band=band,
            limit=limit,
            only_waiting=waiting,
            only_test_drive=has_test_drive,
        )
    except Customer360DisabledError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED) from error
    return [OpportunityListItem(**row) for row in rows]


@advisor_router.post("/sessions/{session_id}/opportunity", response_model=MoveSessionResponse)
async def move_session(
    session_id: UUID,
    request: MoveSessionRequest,
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    operations: Customer360Operations = Depends(customer_360_operations),
) -> MoveSessionResponse:
    """TVV Tách phiên thành cơ hội mới hoặc Gộp vào cơ hội khác. Admin chỉ xem → 403."""
    if _admin(identity):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin xem hồ sơ ở chế độ chỉ đọc")
    if request.action == "MOVE" and not request.opportunity_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="MOVE cần opportunity_id")
    try:
        customer_id = await reader.check_access(
            "session", str(session_id), requester_ids=_ids(identity), is_admin=False
        )
        if customer_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên")
        if request.action == "MOVE":
            target_owner = await reader.check_access(
                "opportunity", str(request.opportunity_id), requester_ids=_ids(identity), is_admin=False
            )
            if target_owner != customer_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Cơ hội không thuộc khách này"
                )
    except CustomerAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from error
    target = await operations.move_session(
        str(session_id),
        str(request.opportunity_id) if request.action == "MOVE" else None,
        identity.staff_id,
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên hoặc cơ hội")
    return MoveSessionResponse(session_id=str(session_id), opportunity_id=target)


@advisor_router.post("/insights/{insight_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def insight_feedback(
    insight_id: UUID,
    request: InsightFeedbackRequest,
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    operations: Customer360Operations = Depends(customer_360_operations),
) -> None:
    """TVV báo một insight sai/đúng — nguồn của tab "Chất lượng trích xuất"."""
    if _admin(identity):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin xem hồ sơ ở chế độ chỉ đọc")
    try:
        owner = await reader.check_access("insight", str(insight_id), requester_ids=_ids(identity), is_admin=False)
    except CustomerAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from error
    if owner is None or not await operations.insight_feedback(
        insight_id, request.verdict, identity.staff_id, request.note
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thông tin này")


@admin_router.get("/customer-360/metrics")
async def customer_360_metrics(
    window: int = Query(30, ge=1, le=365),
    identity: StaffIdentity = Depends(require_admin),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> dict:
    """Số THẬT cho Admin Dashboard: phễu 5 giai đoạn, độ nóng, rào cản, tải việc TVV."""
    return await operations.metrics(window)


@admin_router.get("/customer-360/extraction-quality")
async def extraction_quality(
    window: int = Query(30, ge=1, le=365),
    identity: StaffIdentity = Depends(require_admin),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> dict:
    """Tab "Chất lượng trích xuất" của turn-traces (Phase 6)."""
    return await operations.extraction_quality(window)


@admin_router.get("/customers/picker", response_model=list[CustomerPickerItem])
async def customer_picker(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    identity: StaffIdentity = Depends(require_admin),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> list[CustomerPickerItem]:
    """Chọn khách để phân công — kèm độ nóng, SĐT đã che."""
    return [CustomerPickerItem(**row) for row in await operations.picker(q, limit)]


def _offer_response(offer) -> OfferResponse:  # noqa: ANN001
    return OfferResponse(
        offer_id=offer.offer_id,
        opportunity_id=offer.opportunity_id,
        promotion_code=offer.promotion_code,
        status=offer.status.value,
        discount_vnd=offer.discount_vnd,
        needs_manager_approval=offer.needs_manager_approval,
    )


def _offer_error(error: Exception) -> HTTPException:
    if isinstance(error, OffersDisabledError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ưu đãi theo cơ hội chưa được bật")
    if isinstance(error, OfferTransitionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    reason = str(getattr(error, "reason", "BLOCKED"))
    code = status.HTTP_404_NOT_FOUND if reason.endswith("NOT_FOUND") else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=reason)


async def _check(
    reader: Customer360ReadOperations, kind: str, ref: UUID, identity: StaffIdentity, *, allow_admin: bool
) -> str:
    if _admin(identity) and not allow_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin xem hồ sơ ở chế độ chỉ đọc")
    try:
        owner = await reader.check_access(kind, str(ref), requester_ids=_ids(identity), is_admin=_admin(identity))
    except CustomerAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from error
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy")
    return owner


@advisor_router.get("/opportunities/{opportunity_id}/eligible-offers")
async def eligible_offers(
    opportunity_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> dict:
    """Ưu đãi phù hợp (kèm lý do) và cần hỏi thêm (kèm câu hỏi) — đánh giá luật tất định."""
    await _check(reader, "opportunity", opportunity_id, identity, allow_admin=True)
    try:
        result = await offers.eligible(str(opportunity_id))
    except OffersDisabledError as error:
        raise _offer_error(error) from error
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cơ hội")
    return result


@advisor_router.post("/opportunities/{opportunity_id}/offers", response_model=OfferResponse)
async def create_offer(
    opportunity_id: UUID,
    request: CreateOfferRequest,
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> OfferResponse:
    """TVV đề xuất ưu đãi. Vượt `advisor_max_discount_vnd` → SUGGESTED, chờ quản lý duyệt."""
    await _check(reader, "opportunity", opportunity_id, identity, allow_admin=False)
    try:
        offer = await offers.create(
            str(opportunity_id), request.promotion_code, request.proposed_value, identity.staff_id
        )
    except (OfferBlockedError, OffersDisabledError) as error:
        raise _offer_error(error) from error
    return _offer_response(offer)


_ACTION_TARGETS = {
    "engage": OfferStatus.ENGAGED,
    "convert": OfferStatus.CONVERTED,
    "dismiss": OfferStatus.DISMISSED,
}


@advisor_router.get("/opportunity-offers/pending")
async def pending_offers(
    identity: StaffIdentity = Depends(require_staff),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> list[dict]:
    """Ưu đãi vượt hạn mức chờ duyệt — mọi tư vấn viên thấy, người đề xuất không tự duyệt được."""
    _advisor_only(identity)
    try:
        return await offers.list_pending()
    except OffersDisabledError as error:
        raise _offer_error(error) from error


@advisor_router.post("/opportunity-offers/{offer_id}/approve", response_model=OfferResponse)
async def approve_offer(
    offer_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> OfferResponse:
    """Tư vấn viên KHÁC người đề xuất duyệt ưu đãi vượt hạn mức. Tự duyệt → 403."""
    _advisor_only(identity)
    try:
        return _offer_response(await offers.approve(str(offer_id), identity.staff_id, _ids(identity)))
    except OfferBlockedError as error:
        if error.reason == SELF_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Không tự duyệt ưu đãi do chính mình đề xuất"
            ) from error
        raise _offer_error(error) from error
    except (OffersDisabledError, OfferTransitionError) as error:
        raise _offer_error(error) from error


@advisor_router.post("/opportunity-offers/{offer_id}/{action}", response_model=OfferResponse)
async def offer_action(
    offer_id: UUID,
    action: Literal["send", "engage", "convert", "dismiss"],
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> OfferResponse:
    """Gửi (hàng rào kiểm ngay lúc gửi) / khách phản hồi / chốt / bỏ."""
    await _check(reader, "offer", offer_id, identity, allow_admin=False)
    try:
        if action == "send":
            offer = await offers.send(str(offer_id), identity.staff_id)
        else:
            offer = await offers.mark(str(offer_id), _ACTION_TARGETS[action], identity.staff_id)
    except (OfferBlockedError, OffersDisabledError, OfferTransitionError) as error:
        raise _offer_error(error) from error
    return _offer_response(offer)


@advisor_router.get("/customers/{customer_id}/offers")
async def customer_offers(
    customer_id: str,
    identity: StaffIdentity = Depends(require_staff),
    reader: Customer360ReadOperations = Depends(customer_360_read_operations),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> list[dict]:
    """Tab "Ưu đãi đã cấp" của hồ sơ khách."""
    await _overview(customer_id, identity, reader)
    return await offers.list_for_customer(customer_id)


@advisor_router.get("/promotion-stats")
async def promotion_stats(
    promotion_code: str | None = Query(None, max_length=100),
    identity: StaffIdentity = Depends(require_staff),
    offers: OpportunityOfferOperations = Depends(opportunity_offer_operations),
) -> list[dict]:
    """Hiệu quả ưu đãi: số đề xuất/duyệt/gửi/phản hồi/chốt và tỉ lệ chốt (màn Ưu đãi của TVV)."""
    _advisor_only(identity)
    return await offers.stats(promotion_code)


@meta_router.post("/identity/refresh")
async def refresh_my_identity(
    customer_id: str | None = Depends(get_current_customer_id),
    operations: Customer360Operations = Depends(customer_360_operations),
) -> dict[str, bool]:
    """Khách vừa lưu tên/SĐT/địa chỉ: chép ngay sang phía tư vấn viên (plan §19).

    Chỉ chính khách gọi cho chính mình — `customer_id` lấy từ phiên đăng nhập, không nhận từ body.
    """
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return {"refreshed": await operations.refresh_identity(customer_id)}


@meta_router.get("/meta")
async def customer_360_meta(
    identity: StaffIdentity = Depends(require_staff),
    operations: Customer360ReadOperations = Depends(customer_360_read_operations),
) -> dict:
    """Cờ đang bật + enum giai đoạn/ngưỡng độ nóng — nguồn duy nhất ở backend (plan §2.7)."""
    return await operations.meta()


__all__ = [
    "admin_router",
    "advisor_router",
    "customer_360_operations",
    "customer_360_read_operations",
    "opportunity_offer_operations",
    "meta_router",
]
