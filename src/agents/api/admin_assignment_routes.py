"""Admin endpoints for Customer Assignment Center and Conversation Reassignment."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from src.agents.api.dependencies import get_agent
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.composition import AgentComposition
from src.agents.models import (
    ConversationSessionRow,
    ConversationTurnOutcomeRow,
    CustomerProfileRow,
    ReviewQueueRow,
    TestDriveBookingRow,
)
from src.auth.domain.audit import log_admin_override
from src.auth.domain.authorization import Role

router = APIRouter(prefix="/admin", tags=["admin-assignments"])


class AssignCustomerRequest(BaseModel):
    """Payload to assign or transfer a customer to an advisor."""

    model_config = ConfigDict(frozen=True)

    advisor_id: str
    reason: str | None = None


class UnassignCustomerRequest(BaseModel):
    """Payload to unassign an active customer."""

    model_config = ConfigDict(frozen=True)

    reason: str | None = None


class ReassignConversationRequest(BaseModel):
    """Payload to reassign a live chat session to a different advisor."""

    model_config = ConfigDict(frozen=True)

    advisor_id: str
    reason: str | None = None


class CustomerAssignmentItem(BaseModel):
    """Assignment record item."""

    model_config = ConfigDict(frozen=True)

    assignment_id: UUID
    customer_id: str
    advisor_id: str
    assigned_by: str
    reason: str | None
    status: str
    assigned_at: datetime
    unassigned_at: datetime | None
    created_at: datetime


class CustomerAssignmentsPage(BaseModel):
    """Paginated list of customer assignments."""

    model_config = ConfigDict(frozen=True)

    items: list[CustomerAssignmentItem]
    total: int
    page: int
    page_size: int


class DashboardMetricsResponse(BaseModel):
    """Aggregated operational metrics for the Admin Dashboard."""

    model_config = ConfigDict(frozen=True)

    total_conversations: int
    completed_profiles: int
    approved_reviews: int
    total_bookings: int
    funnel: list[dict]
    quality_stats: dict


def _require_admin(identity: StaffIdentity = Depends(current_staff)) -> StaffIdentity:
    if identity.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required for assignment management",
        )
    return identity


@router.post("/customers/{customer_id}/assign")
async def assign_customer(
    customer_id: str,
    request: AssignCustomerRequest,
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> dict:
    """Admin assigns or transfers a customer to an advisor."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    assignment_id = await agent.operations.assignments.assign_customer(
        customer_id=customer_id,
        advisor_id=request.advisor_id,
        assigned_by=identity.staff_id,
        reason=request.reason,
    )
    log_admin_override(
        actor_id=identity.staff_id,
        action="ASSIGN_CUSTOMER",
        resource_type="customer",
        resource_id=customer_id,
        details={"advisor_id": request.advisor_id, "reason": request.reason},
    )
    return {
        "assignment_id": str(assignment_id),
        "customer_id": customer_id,
        "advisor_id": request.advisor_id,
        "status": "ACTIVE",
    }


@router.post("/customers/{customer_id}/unassign")
async def unassign_customer(
    customer_id: str,
    request: UnassignCustomerRequest,
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> dict:
    """Admin unassigns an active customer."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    unassigned = await agent.operations.assignments.unassign_customer(
        customer_id=customer_id,
        unassigned_by=identity.staff_id,
        reason=request.reason,
    )
    return {"customer_id": customer_id, "status": "UNASSIGNED", "unassigned": unassigned}


@router.get("/customers/assignments", response_model=CustomerAssignmentsPage)
async def list_assignments(
    advisor_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> CustomerAssignmentsPage:
    """Admin lists all customer assignments with status/advisor filters."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    offset = (page - 1) * page_size
    items, total = await agent.operations.assignments.list_assignments(
        advisor_id=advisor_id,
        status=status_filter,
        limit=page_size,
        offset=offset,
    )
    return CustomerAssignmentsPage(
        items=[
            CustomerAssignmentItem(
                assignment_id=item.assignment_id,
                customer_id=item.customer_id,
                advisor_id=item.advisor_id,
                assigned_by=item.assigned_by,
                reason=item.reason,
                status=item.status,
                assigned_at=item.assigned_at,
                unassigned_at=item.unassigned_at,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers/{customer_id}/assignment-history")
async def get_customer_assignment_history(
    customer_id: str,
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> dict:
    """Admin views the full assignment history of a customer."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    history = await agent.operations.assignments.get_customer_history(customer_id)
    return {
        "customer_id": customer_id,
        "items": [
            {
                "assignment_id": str(item.assignment_id),
                "advisor_id": item.advisor_id,
                "assigned_by": item.assigned_by,
                "reason": item.reason,
                "status": item.status,
                "assigned_at": item.assigned_at.isoformat(),
                "unassigned_at": item.unassigned_at.isoformat() if item.unassigned_at else None,
            }
            for item in history
        ],
    }


@router.get("/customers/available")
async def list_available_customers(
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> list[dict]:
    """Admin lists all registered customer profiles from database to select for assignment."""
    if not agent.operations:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    async with agent.operations.review._unit_of_work.transaction() as tx:
        session = tx.sessions.session
        stmt = select(CustomerProfileRow).order_by(CustomerProfileRow.created_at.desc())
        rows = (await session.scalars(stmt)).all()
        return [
            {
                "customer_id": row.customer_id,
                "display_name": row.display_name or row.customer_id,
                "phone": row.phone,
                "email": row.email,
            }
            for row in rows
        ]


@router.post("/conversations/{conversation_id}/reassign")
async def reassign_conversation(
    conversation_id: UUID,
    request: ReassignConversationRequest,
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> dict:
    """Admin transfers a live chat conversation to another advisor."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    try:
        prev_advisor, new_advisor = await agent.operations.assignments.reassign_conversation(
            session_id=conversation_id,
            new_advisor_id=request.advisor_id,
            reassigned_by=identity.staff_id,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    log_admin_override(
        actor_id=identity.staff_id,
        action="REASSIGN_CONVERSATION",
        resource_type="conversation_session",
        resource_id=str(conversation_id),
        details={"previous_advisor_id": prev_advisor, "new_advisor_id": new_advisor, "reason": request.reason},
    )
    return {
        "session_id": str(conversation_id),
        "previous_advisor_id": prev_advisor,
        "new_advisor_id": new_advisor,
        "reassigned": True,
    }


@router.get("/analytics/dashboard", response_model=DashboardMetricsResponse)
async def admin_dashboard_metrics(
    identity: StaffIdentity = Depends(_require_admin),
    agent: AgentComposition = Depends(get_agent),
) -> DashboardMetricsResponse:
    """Live aggregation of operational KPIs and conversion funnel for Admin Dashboard."""
    if not agent.operations:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent operations unavailable")

    async with agent.operations.review._unit_of_work.transaction() as tx:
        session = tx.sessions.session  # underlying AsyncSession

        total_conv = (await session.scalar(select(func.count(ConversationSessionRow.session_id)))) or 0
        total_profiles = (await session.scalar(select(func.count(CustomerProfileRow.customer_id)))) or 0
        approved_reviews = (
            await session.scalar(
                select(func.count(ReviewQueueRow.review_id)).where(ReviewQueueRow.status.in_(["APPROVED", "EDITED"]))
            )
        ) or 0
        total_bookings = (await session.scalar(select(func.count(TestDriveBookingRow.booking_id)))) or 0

        # Review stats
        total_reviews = (await session.scalar(select(func.count(ReviewQueueRow.review_id)))) or 0
        approved_orig = (
            await session.scalar(
                select(func.count(ReviewQueueRow.review_id)).where(ReviewQueueRow.status == "APPROVED")
            )
        ) or 0
        edited_count = (
            await session.scalar(select(func.count(ReviewQueueRow.review_id)).where(ReviewQueueRow.status == "EDITED"))
        ) or 0
        rejected_count = (
            await session.scalar(
                select(func.count(ReviewQueueRow.review_id)).where(ReviewQueueRow.status == "REJECTED")
            )
        ) or 0

        # Plan Customer 360 (Phase 4): trước đây rỗng dữ liệu thì trả số BỊA (74/83/1814…) và
        # "Có đề xuất" = 73% số hội thoại. Giờ không có dữ liệu thì là 0, và "Có đề xuất" đếm
        # thật từ các lượt có danh sách đề xuất.
        rec_count = (
            await session.scalar(
                select(func.count(func.distinct(ConversationTurnOutcomeRow.session_id))).where(
                    func.jsonb_array_length(ConversationTurnOutcomeRow.recommendations) > 0
                )
            )
        ) or 0

        def _pct(part: int, whole: int) -> int:
            return round(part / whole * 100) if whole else 0

        approved_pct = _pct(approved_orig, total_reviews)
        edited_pct = _pct(edited_count, total_reviews)
        rejected_pct = _pct(rejected_count, total_reviews)
        conv_percent = 100 if total_conv else 0
        prof_percent = _pct(total_profiles, total_conv)
        rec_percent = _pct(rec_count, total_conv)
        appr_percent = _pct(approved_reviews, total_conv)
        book_percent = _pct(total_bookings, total_conv)

        funnel_data = [
            {"label": "Bắt đầu hội thoại", "value": total_conv, "percent": conv_percent},
            {"label": "Hoàn tất hồ sơ", "value": total_profiles, "percent": prof_percent},
            {"label": "Có đề xuất", "value": rec_count, "percent": rec_percent},
            {"label": "Được duyệt", "value": approved_reviews, "percent": appr_percent},
            {"label": "Đặt lái thử", "value": total_bookings, "percent": book_percent},
        ]

        quality_stats = {
            "approved_original_pct": approved_pct,
            "edited_pct": edited_pct,
            "rejected_pct": rejected_pct,
        }

    return DashboardMetricsResponse(
        total_conversations=total_conv,
        completed_profiles=total_profiles,
        approved_reviews=approved_reviews,
        total_bookings=total_bookings,
        funnel=funnel_data,
        quality_stats=quality_stats,
    )
