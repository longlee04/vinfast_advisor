"""[A7-2/A7-3] HTTP cho hàng đợi duyệt — nhận mục, duyệt/sửa/từ chối, và cửa gửi khách.

Cửa gửi khách chặn theo trạng thái ở **service**, nên thêm route mới cũng không
mở ra đường vòng: mọi đường đều gọi cùng một hàm kiểm tra.
"""

from __future__ import annotations

from base64 import b64encode
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.agents.api.schemas import (
    ApproveReviewRequest,
    ClaimReviewResponse,
    DeliverContentResponse,
    PendingReviewResponse,
    QueueEntryResponse,
    ResolveReviewRequest,
    ResolveReviewResponse,
    ReviewDetailResponse,
)
from src.agents.api.security import StaffIdentity, require_staff
from src.agents.services.operations.review import (
    EditedNumbersChangedError,
    OfferAdjustmentOutOfBoundsError,
    OfferPromotionExpiredError,
    QueueEntry,
    ReviewClaimForbiddenError,
    ReviewLeaseExpiredError,
    ReviewNotApprovedError,
    ReviewNotFoundError,
    ReviewOperations,
    UntracedNumberError,
)
from src.auth.domain.audit import (
    log_admin_override,
    log_authorization_denied,
    log_hitl_claim_conflict,
    log_hitl_lease_expired,
)
from src.auth.domain.authorization import Permission, Role, Scope

router = APIRouter(prefix="/agent/review", tags=["agent-review"])

#: Màn hàng đợi dùng path số nhiều, tách hẳn khỏi `/agent/review/{id}` số ít —
#: hai router riêng nên không có chuyện `reviews` bị đọc nhầm thành `review_id`.
reviews_router = APIRouter(prefix="/agent/reviews", tags=["agent-review"])

MAX_QUEUE_LIMIT = 100


def review_operations() -> ReviewOperations:
    """Điểm nối use case — composition của app thật ghi đè bằng bản có DB."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Chưa nối use case hàng đợi duyệt",
    )


def _not_found(error: ReviewNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy mục duyệt")


@router.get("", response_model=list[PendingReviewResponse])
async def pending_queue(
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> list[PendingReviewResponse]:
    """Hàng đợi mục chờ duyệt — cửa duy nhất để tư vấn viên biết `review_id`."""
    entries = await operations.pending_queue()
    return [
        PendingReviewResponse(
            review_id=entry.review_id,
            session_id=entry.session_id,
            run_id=entry.run_id,
            status=entry.status,
            content=entry.content,
            claimed_by=entry.claimed_by,
            lease_expires_at=entry.lease_expires_at,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.get("/stats")
async def review_stats(
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> dict[str, int]:
    """Thống kê số lượng hàng đợi duyệt thực tế từ database."""
    return await operations.queue_stats()


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def review_detail(
    review_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> ReviewDetailResponse:
    """Bản nháp kèm ảnh so sánh — ảnh dựng muộn đúng lúc mở mục duyệt."""
    try:
        item = await operations.review_detail(review_id)
    except ReviewNotFoundError as error:
        raise _not_found(error) from error
    image = await operations.image_for_review(review_id)
    return ReviewDetailResponse(
        review_id=item.review_id,
        session_id=item.session_id,
        run_id=item.run_id,
        status=item.status,
        content=item.content,
        edited_content=item.edited_content,
        comparison_image_base64=b64encode(image).decode("ascii") if image else None,
        profile_snapshot=item.profile_snapshot,
        offer_state=item.offer_state,
        matched_promotions=item.matched_promotions,
        adjustment_policies=await operations.adjustment_policies(),
    )


def _queue_entry_response(entry: QueueEntry) -> QueueEntryResponse:
    return QueueEntryResponse(
        review_id=entry.review_id,
        session_id=entry.session_id,
        run_id=entry.run_id,
        status=entry.status,
        content=entry.content,
        claimed_by=entry.claimed_by,
        lease_expires_at=entry.lease_expires_at,
        created_at=entry.created_at,
        profile_snapshot=entry.profile_snapshot,
        offer_state=entry.offer_state,
        age_minutes=entry.age_minutes,
        handoff_requested=entry.handoff_requested,
        offer_suggestion_ignored=entry.offer_suggestion_ignored,
    )


@reviews_router.get("", response_model=list[QueueEntryResponse])
async def list_reviews(
    status_filter: Literal["pending", "approved", "rejected"] = Query("pending", alias="status"),
    limit: int = Query(50),
    offset: int = Query(0),
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> list[QueueEntryResponse]:
    """Hàng đợi có lọc trạng thái + phân trang — nguồn cho màn duyệt và polling."""
    if limit < 1 or limit > MAX_QUEUE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"limit phải trong khoảng 1..{MAX_QUEUE_LIMIT}",
        )
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset không được âm")
    entries = await operations.queue_entries(status_filter=status_filter, limit=limit, offset=offset)
    return [_queue_entry_response(entry) for entry in entries]


@router.post("/{review_id}/claim", response_model=ClaimReviewResponse)
async def claim_review(
    review_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> ClaimReviewResponse:
    """Nhận một mục; thua thì nói rõ đã có người nhận."""
    outcome = await operations.claim(review_id, advisor_id=identity.staff_id)
    if not outcome.granted:
        log_hitl_claim_conflict(
            actor_id=identity.staff_id,
            review_id=str(review_id),
            claimed_by=None,
            lease_expires_at=None,
        )
    return ClaimReviewResponse(
        granted=outcome.granted,
        rejection=outcome.rejection.value if outcome.rejection else None,
    )


@router.post("/{review_id}/approve", response_model=ResolveReviewResponse)
async def approve_review(
    review_id: UUID,
    payload: ApproveReviewRequest,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> ResolveReviewResponse:
    """Duyệt nguyên trạng, hoặc sửa văn bản rồi duyệt."""
    is_admin = identity.role == Role.ADMIN
    if is_admin:
        log_admin_override(
            actor_id=identity.staff_id,
            action="APPROVE_REVIEW",
            resource_type="review_queue",
            resource_id=str(review_id),
        )
    try:
        await operations.approve(
            review_id,
            advisor_id=identity.staff_id,
            edited_content=payload.edited_content,
            is_admin=is_admin,
        )
    except ReviewNotFoundError as error:
        raise _not_found(error) from error
    except ReviewClaimForbiddenError as error:
        log_authorization_denied(
            actor_id=identity.staff_id,
            role=identity.role,
            permission=Permission.HITL_RESOLVE,
            resource_type="review_queue",
            resource_id=str(review_id),
            scope=Scope.CLAIMED,
            reason="TICKET_CLAIMED_BY_ANOTHER_ADVISOR",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mục duyệt này thuộc tư vấn viên khác",
        ) from error
    except ReviewLeaseExpiredError as error:
        log_hitl_lease_expired(
            actor_id=identity.staff_id,
            review_id=str(review_id),
            lease_expires_at=None,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Thời hạn 15 phút duyệt của mục này đã hết hạn",
        ) from error
    except EditedNumbersChangedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Bản sửa làm đổi số liệu — đổi số phải qua catalog Admin",
        ) from error
    except UntracedNumberError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="untraced_number",
        ) from error
    return ResolveReviewResponse(review_id=review_id)


@router.post("/{review_id}/reject", response_model=ResolveReviewResponse)
async def reject_review(
    review_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> ResolveReviewResponse:
    """Từ chối bản nháp."""
    is_admin = identity.role == Role.ADMIN
    if is_admin:
        log_admin_override(
            actor_id=identity.staff_id,
            action="REJECT_REVIEW",
            resource_type="review_queue",
            resource_id=str(review_id),
        )
    try:
        await operations.reject(
            review_id,
            advisor_id=identity.staff_id,
            is_admin=is_admin,
        )
    except ReviewNotFoundError as error:
        raise _not_found(error) from error
    except ReviewClaimForbiddenError as error:
        log_authorization_denied(
            actor_id=identity.staff_id,
            role=identity.role,
            permission=Permission.HITL_RESOLVE,
            resource_type="review_queue",
            resource_id=str(review_id),
            scope=Scope.CLAIMED,
            reason="TICKET_CLAIMED_BY_ANOTHER_ADVISOR",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mục duyệt này thuộc tư vấn viên khác",
        ) from error
    except ReviewLeaseExpiredError as error:
        log_hitl_lease_expired(
            actor_id=identity.staff_id,
            review_id=str(review_id),
            lease_expires_at=None,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Thời hạn 15 phút duyệt của mục này đã hết hạn",
        ) from error
    return ResolveReviewResponse(review_id=review_id)


@router.post("/{review_id}/resolve", response_model=ResolveReviewResponse)
async def resolve_review(
    review_id: UUID,
    payload: ResolveReviewRequest,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> ResolveReviewResponse:
    """Duyệt/từ chối kèm tuỳ chọn cấp ưu đãi và cờ chuyển người thật.

    Cửa này thêm vào chứ không thay `/approve` + `/reject`: hai đường cũ vẫn là
    hợp đồng đang chạy, đường này dành cho luồng có ưu đãi hoặc handoff.
    """
    try:
        await operations.resolve_with_offer(
            review_id,
            advisor_id=identity.staff_id,
            status=payload.status,
            edited_content=payload.edited_content,
            offer_adjustment=(payload.offer_adjustment.model_dump() if payload.offer_adjustment else None),
            handoff_requested=payload.handoff_requested,
        )
    except ReviewNotFoundError as error:
        raise _not_found(error) from error
    except OfferAdjustmentOutOfBoundsError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="adjustment_out_of_bounds",
        ) from error
    except OfferPromotionExpiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="promotion_expired") from error
    except EditedNumbersChangedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Bản sửa làm đổi số liệu — đổi số phải qua catalog Admin",
        ) from error
    except UntracedNumberError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="untraced_number",
        ) from error
    return ResolveReviewResponse(review_id=review_id)


@router.post("/{review_id}/deliver", response_model=DeliverContentResponse)
async def deliver_to_customer(
    review_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    operations: ReviewOperations = Depends(review_operations),
) -> DeliverContentResponse:
    """Cửa duy nhất đưa nội dung ra cho khách — chưa duyệt thì 409.

    Ảnh so sánh đi kèm ngay trong cửa này, nên nó chịu đúng chốt chặn của phần
    văn bản: chưa duyệt thì không có đường nào lấy được ảnh ra.
    """
    try:
        item = await operations.deliverable_for_customer(review_id)
    except ReviewNotFoundError as error:
        raise _not_found(error) from error
    except ReviewNotApprovedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nội dung chưa được duyệt, không gửi khách được",
        ) from error
    image = await operations.image_for_review(review_id)
    return DeliverContentResponse(
        review_id=review_id,
        content=item.deliverable_content,
        comparison_image_base64=b64encode(image).decode("ascii") if image else None,
    )
