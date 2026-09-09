"""Customer delivery REST and turn-event SSE endpoints."""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import AsyncIterator
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from src.agents.api.dependencies import CustomerDependency
from src.agents.api.history_routes import history_operations
from src.agents.api.review_routes import review_operations
from src.agents.services.operations.history import HistoryOperations
from src.agents.services.operations.review import (
    CustomerSessionForbiddenError,
    ReviewOperations,
)
from src.agents.services.operations.turn_events import TurnEventBroker
from src.auth.domain.audit import log_authorization_denied
from src.auth.domain.authorization import Permission, Role, Scope

router = APIRouter(prefix="/agent", tags=["agent-customer"])


class CustomerDeliveryResponse(BaseModel):
    """One approved or edited review visible to its owning customer."""

    model_config = ConfigDict(frozen=True)

    review_id: UUID
    content: str
    #: `APPROVED`/`EDITED` là nội dung thật; `EXPIRED` là lời xin lỗi quá hạn.
    status: str = "APPROVED"
    comparison_image_base64: str | None = None


class CustomerDeliveriesResponse(BaseModel):
    """Customer-visible delivery collection."""

    model_config = ConfigDict(frozen=True)

    items: list[CustomerDeliveryResponse]


class CustomerActivityResponse(BaseModel):
    id: str
    kind: str
    date: str
    title: str
    description: str
    status: str
    tone: str = "neutral"
    icon: str = "message"


class CustomerAccountSummaryResponse(BaseModel):
    session_count: int
    booking_count: int
    comparison_count: int
    approved_recommendations_count: int
    activities: list[CustomerActivityResponse]


def turn_event_broker() -> TurnEventBroker:
    """Resolve broker through the application composition override seam."""
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent unavailable")


def _forbidden(error: CustomerSessionForbiddenError, session_id: UUID, customer_id: str) -> HTTPException:
    log_authorization_denied(
        actor_id=customer_id,
        role=Role.CUSTOMER,
        permission=Permission.CHAT_VIEW_OWN,
        resource_type="conversation_session",
        resource_id=str(session_id),
        scope=Scope.OWN,
        reason="CUSTOMER_NOT_SESSION_OWNER",
    )
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="session access forbidden")


@router.get("/deliveries/{session_id}", response_model=CustomerDeliveriesResponse)
async def customer_deliveries(
    session_id: UUID,
    customer_id: str | None = CustomerDependency,
    operations: ReviewOperations = Depends(review_operations),
) -> CustomerDeliveriesResponse:
    """Return approved customer content and optional comparison images."""
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    try:
        items = await operations.customer_deliverables(session_id, customer_id)
    except CustomerSessionForbiddenError as error:
        raise _forbidden(error, session_id, customer_id) from error
    deliveries = [
        CustomerDeliveryResponse(
            review_id=item.review_id,
            content=item.deliverable_content,
            status=item.status,
            # Mục quá hạn không có gì để so sánh: chỉ có lời xin lỗi, kèm ảnh
            # bảng so sánh vào là hứa một nội dung chưa ai duyệt.
            comparison_image_base64=(
                b64encode(image).decode("ascii")
                if item.status != "EXPIRED" and (image := await operations.image_for_review(item.review_id)) is not None
                else None
            ),
        )
        for item in items
    ]
    return CustomerDeliveriesResponse(items=deliveries)


@router.get("/events/{session_id}")
async def customer_turn_events(
    session_id: UUID,
    customer_id: str | None = CustomerDependency,
    operations: ReviewOperations = Depends(review_operations),
    broker: TurnEventBroker = Depends(turn_event_broker),
) -> StreamingResponse:
    """Stream review IDs for an owned session; content stays behind REST."""
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    try:
        await operations.authorize_customer_session(session_id, customer_id)
    except CustomerSessionForbiddenError as error:
        raise _forbidden(error, session_id, customer_id) from error

    async def stream() -> AsyncIterator[str]:
        async with broker.subscribe(session_id) as events:
            while True:
                with anyio.move_on_after(15) as timeout:
                    try:
                        event = await anext(events)
                    except StopAsyncIteration:
                        return
                if timeout.cancelled_caught:
                    yield ": keepalive\n\n"
                    continue
                payload = {
                    "event_id": str(event.event_id),
                    "kind": event.kind,
                    "review_id": str(event.review_id),
                    "client_turn_id": (str(event.client_turn_id) if event.client_turn_id is not None else None),
                    "message_id": str(event.message_id) if event.message_id is not None else None,
                }
                yield (f"id: {event.event_id}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n")

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.get("/customer/summary", response_model=CustomerAccountSummaryResponse)
async def customer_summary(
    customer_id: str | None = CustomerDependency,
    history_ops: HistoryOperations = Depends(history_operations),
) -> CustomerAccountSummaryResponse:
    """Trả về số liệu thống kê phiên tư vấn, lịch lái thử và hoạt động gần đây của khách hàng."""
    if customer_id is None:
        return CustomerAccountSummaryResponse(
            session_count=0,
            booking_count=0,
            comparison_count=0,
            approved_recommendations_count=0,
            activities=[],
        )
    summary = await history_ops.get_summary(customer_id, requester_id=customer_id, role=Role.CUSTOMER)
    return CustomerAccountSummaryResponse(
        session_count=summary.session_count,
        booking_count=summary.booking_count,
        comparison_count=summary.comparison_count,
        approved_recommendations_count=summary.approved_recommendations_count,
        activities=[
            CustomerActivityResponse(
                id=a.id,
                kind=a.kind,
                date=a.date,
                title=a.title,
                description=a.description,
                status=a.status,
                tone=a.tone,
                icon=a.icon,
            )
            for a in summary.activities
        ],
    )


__all__ = ["router", "turn_event_broker"]
