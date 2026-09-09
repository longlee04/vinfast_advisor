"""Advisor/Admin conversation history and live-chat control API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.agents.api.dependencies import AgentDependency
from src.agents.api.security import StaffIdentity, require_staff
from src.agents.api.ws_manager import ws_manager
from src.auth.domain.audit import log_authorization_denied
from src.auth.domain.authorization import Permission, Role, Scope

router = APIRouter(prefix="/advisor", tags=["advisor-conversations"])


class AdvisorConversationListItem(BaseModel):
    conversation_id: UUID
    customer_id: str
    customer_display: str | None = None
    status: str
    hitl_priority: str | None = None
    hitl_reasons: list[str] = Field(default_factory=list)
    last_message_preview: str = ""
    last_activity_at: datetime
    assigned_advisor_id: str | None = None
    # Đợt 9: slot lõi v2 đã hiểu (ngân sách, loại xe, mục đích…) — có ngay ở
    # danh sách để TVV lọc phiên đáng gọi mà không phải mở từng cái.
    slots: dict = Field(default_factory=dict)


class AdvisorConversationListResponse(BaseModel):
    items: list[AdvisorConversationListItem]


class AdvisorConversationDetailResponse(AdvisorConversationListItem):
    messages: list[dict]
    current_summary: str | None = None
    ai_summary: dict | None = None


class JoinResponse(BaseModel):
    joined: bool
    conversation_id: UUID
    customer_id: str | None = None


class ReplyRequest(BaseModel):
    content: str = Field(min_length=1)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=128)


class ReplyResponse(BaseModel):
    message_id: UUID
    created_at: datetime


class CloseResponse(BaseModel):
    closed: bool
    conversation_id: UUID


class HitlQueueItem(BaseModel):
    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime


def _service(agent):
    if agent is None or agent.services.conversation is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="conversation unavailable")
    return agent.services.conversation


def _role(identity: StaffIdentity) -> str:
    return identity.role.value


def _staff_status(item: object) -> str:
    """Trạng thái cho màn TVV: `WAITING_ADVISOR` khi bot đã bàn giao mà chưa ai nhận.

    Cột `status` DB chỉ có ACTIVE/COMPLETED/ABANDONED, còn màn danh sách TVV lọc
    theo `WAITING_ADVISOR` — trước đây không nguồn nào phát ra giá trị đó nên
    phiên khách xin gặp người nằm lẫn trong "đang hoạt động" (kiểm tra prod
    2026-08-30). Ownership `PENDING_HANDOFF` chính là "đang chờ tư vấn viên".
    """

    status = str(getattr(item, "status", "") or "")
    if status == "ACTIVE" and getattr(item, "ownership", "AI") == "PENDING_HANDOFF":
        return "WAITING_ADVISOR"
    return status


def _hitl_reasons(item: object) -> list[str]:
    ownership = getattr(item, "ownership", "AI")
    if ownership == "PENDING_HANDOFF":
        return ["Bot đã bàn giao — khách đang chờ tư vấn viên"]
    if ownership == "HUMAN":
        return ["Tư vấn viên đang cầm phiên"]
    return []


@router.get("/queue", response_model=list[HitlQueueItem])
async def advisor_queue(
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> list[HitlQueueItem]:
    """Compatibility queue endpoint for live-chat and draft leads."""

    if agent is None or agent.operations is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="advisor queue unavailable")
    entries = await agent.operations.review.pending_queue()
    return [HitlQueueItem(**vars(entry)) for entry in entries]


@router.get("/queue/stats")
async def advisor_queue_stats(
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> dict[str, int]:
    """Thống kê hàng đợi duyệt thực tế cho Advisor Workspace."""
    if agent is None or agent.operations is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="advisor queue unavailable")
    return await agent.operations.review.queue_stats()


@router.get("/conversations", response_model=AdvisorConversationListResponse)
async def list_advisor_conversations(
    customer_id: str | None = None,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> AdvisorConversationListResponse:
    """Admin sees all; advisor sees assigned conversations only."""

    service = _service(agent)
    items = await service.list_staff_conversations(
        requester_id=identity.staff_id, role=_role(identity), customer_id=customer_id
    )
    return AdvisorConversationListResponse(
        items=[
            AdvisorConversationListItem(
                conversation_id=item.session_id,
                customer_id=item.customer_id,
                status=_staff_status(item),
                hitl_reasons=_hitl_reasons(item),
                assigned_advisor_id=item.assigned_advisor_id,
                last_activity_at=item.last_activity_at,
                last_message_preview=item.last_message_preview,
                slots=dict(item.slots),
            )
            for item in items
        ]
    )


@router.get("/conversations/{conversation_id}", response_model=AdvisorConversationDetailResponse)
async def advisor_conversation_detail(
    conversation_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> AdvisorConversationDetailResponse:
    """Return assigned staff context and the complete durable transcript."""

    service = _service(agent)
    result = await service.staff_conversation_detail(
        str(conversation_id), requester_id=identity.staff_id, role=_role(identity)
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    summary, messages = result
    return AdvisorConversationDetailResponse(
        conversation_id=summary.session_id,
        customer_id=summary.customer_id,
        status=_staff_status(summary),
        hitl_reasons=_hitl_reasons(summary),
        assigned_advisor_id=summary.assigned_advisor_id,
        last_activity_at=summary.last_activity_at,
        last_message_preview=summary.last_message_preview,
        slots=dict(summary.slots),
        messages=[
            {
                "message_id": message.message_id,
                "role": message.role,
                "sender_type": "CUSTOMER"
                if message.role == "USER"
                else ("ADVISOR" if message.role == "ADVISOR" else "AGENT"),
                "content": message.content,
                "client_turn_id": message.client_turn_id,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    )


@router.post("/conversations/{conversation_id}/join", response_model=JoinResponse)
async def join_conversation(
    conversation_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> JoinResponse:
    """Claim a conversation and move it to ADVISOR_JOINED."""

    service = _service(agent)
    joined = await service.join_advisor(str(conversation_id), identity.staff_id)
    if not joined:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conversation already assigned or closed")
    detail = await service.staff_conversation_detail(
        str(conversation_id), requester_id=identity.staff_id, role=_role(identity)
    )
    customer_id = detail[0].customer_id if detail else None
    await ws_manager.broadcast(
        str(conversation_id),
        {"type": "ADVISOR_JOINED", "advisor_name": identity.staff_id, "role": _role(identity)},
    )
    return JoinResponse(joined=True, conversation_id=conversation_id, customer_id=customer_id)


@router.post("/conversations/{conversation_id}/reply", response_model=ReplyResponse)
@router.post("/conversations/{conversation_id}/messages", response_model=ReplyResponse)
async def reply_to_conversation(
    conversation_id: UUID,
    request: ReplyRequest,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> ReplyResponse:
    """Persist an advisor message and broadcast it to the room."""

    service = _service(agent)
    try:
        message_id = await service.advisor_reply(
            str(conversation_id), identity.staff_id, request.content, request.client_message_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation not assigned") from error
    created_at = datetime.now().astimezone()
    await ws_manager.broadcast(
        str(conversation_id),
        {
            "type": "ADVISOR_MESSAGE",
            "content": request.content,
            "message_id": str(message_id),
            "advisor_name": identity.staff_id,
            "created_at": created_at.isoformat(),
        },
    )
    return ReplyResponse(message_id=message_id, created_at=created_at)


@router.post("/conversations/{conversation_id}/close", response_model=CloseResponse)
async def close_conversation(
    conversation_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> CloseResponse:
    """Close the assigned live chat and notify all room participants."""

    service = _service(agent)
    closed = await service.close_advisor_chat(str(conversation_id), identity.staff_id)
    if not closed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation not assigned or already closed")

    # Xoá các mục chờ duyệt của phiên này khỏi hàng đợi nếu có
    try:
        if hasattr(agent, "operations") and hasattr(agent.operations, "review"):
            pending_items = await agent.operations.review.pending_queue()
            for item in pending_items:
                if str(item.session_id) == str(conversation_id):
                    try:
                        await agent.operations.review.reject(item.review_id, advisor_id=identity.staff_id)
                    except Exception:
                        pass
    except Exception:
        pass

    await ws_manager.broadcast(str(conversation_id), {"type": "ADVISOR_CLOSED"})
    return CloseResponse(closed=True, conversation_id=conversation_id)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_by_staff(
    conversation_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> dict[str, bool]:
    """Delete a conversation and all its messages (Admin only)."""
    if identity.role != Role.ADMIN:
        log_authorization_denied(
            actor_id=identity.staff_id,
            role=identity.role,
            permission=Permission.CONVERSATION_DELETE_GLOBAL,
            resource_type="conversation_session",
            resource_id=str(conversation_id),
            scope=Scope.GLOBAL,
            reason="ADMIN_ROLE_REQUIRED",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to delete conversations",
        )

    service = _service(agent)
    deleted = await service.staff_delete_conversation(str(conversation_id))
    return {"deleted": deleted}


@router.post("/conversations/{conversation_id}/handoff")
@router.post("/conversations/{conversation_id}/release")
async def handoff_to_agent(
    conversation_id: UUID,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> dict[str, bool]:
    """Release an assigned conversation back to AI Agent."""

    service = _service(agent)
    released = await service.release_to_agent(str(conversation_id))
    await ws_manager.broadcast(
        str(conversation_id),
        {
            "type": "ADVISOR_HANDOFF",
            "advisor_name": identity.staff_id,
            "message": "Tư vấn viên đã chuyển lại cuộc trò chuyện cho trợ lý ảo VinFast.",
        },
    )
    return {"released": released}


class AdvisorCustomerItem(BaseModel):
    customer_id: str
    advisor_id: str
    assigned_at: datetime
    reason: str | None = None
    status: str = "ACTIVE"
    profile_payload: dict = Field(default_factory=dict)
    active_conversations_count: int = 0
    last_activity_at: datetime | None = None


class AdvisorCustomerListResponse(BaseModel):
    items: list[AdvisorCustomerItem]


@router.get("/customers", response_model=AdvisorCustomerListResponse)
async def list_assigned_customers(
    advisor_id: str | None = None,
    identity: StaffIdentity = Depends(require_staff),
    agent=AgentDependency,
) -> AdvisorCustomerListResponse:
    """Return the real active assigned customers for the authenticated advisor."""
    if not agent.operations or not agent.operations.assignments:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assignment operations unavailable",
        )

    target_id = identity.staff_id
    target_email = identity.email
    if advisor_id:
        target_id = advisor_id
        target_email = advisor_id

    customers = await agent.operations.assignments.list_assigned_customers(
        advisor_id=target_id, advisor_email=target_email
    )
    return AdvisorCustomerListResponse(
        items=[
            AdvisorCustomerItem(
                customer_id=c.customer_id,
                advisor_id=c.advisor_id,
                assigned_at=c.assigned_at,
                reason=c.reason,
                status=c.status,
                profile_payload=c.profile_payload,
                active_conversations_count=c.active_conversations_count,
                last_activity_at=c.last_activity_at,
            )
            for c in customers
        ]
    )
