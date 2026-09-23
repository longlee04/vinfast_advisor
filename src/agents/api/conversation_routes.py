"""Authenticated lifecycle and turn routes for server-backed conversations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from src.agents.api.conversation_schemas import (
    ConversationListResponse,
    ConversationMessageListResponse,
    ConversationMessageResponse,
    ConversationResponse,
    ConversationTurnRequest,
    ConversationTurnResponse,
)
from src.agents.api.dependencies import AgentDependency, CustomerDependency
from src.agents.chain import facts_as_dict, run_turn
from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationMessage,
    ConversationState,
    LeaseAcquired,
    TerminalReplay,
    TurnBusy,
    encode_conversation_cursor,
    encode_message_cursor,
)
from src.agents.domain.turn_result_payload import deserialize_turn_result
from src.agents.errors import (
    ConversationArchivedError,
    ConversationNotFoundError,
    CoreTurnLeaseStaleError,
    CoreTurnTimeoutError,
    TurnFailedError,
    TurnInProgressError,
    TurnPersistenceError,
)
from src.agents.services.output_guard import public_terminal_reason

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _require_customer(customer_id: str | None) -> str:
    if customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED"},
        )
    return customer_id


def _lifecycle(agent: object):
    operations = getattr(agent, "operations", None)
    lifecycle = getattr(operations, "conversations", None)
    if lifecycle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AGENT_UNAVAILABLE"},
        )
    return lifecycle


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationResponse:
    """Create one server-owned conversation for the authenticated customer."""

    customer = _require_customer(customer_id)
    conversation = await _lifecycle(agent).create(customer)
    return _conversation_response(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    include_archived: bool = False,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationListResponse:
    """List a stable page of the authenticated customer's conversations."""

    customer = _require_customer(customer_id)
    try:
        page = await _lifecycle(agent).list_owned(
            customer,
            limit=limit,
            cursor=cursor,
            include_archived=include_archived,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_CURSOR"},
        ) from error
    return ConversationListResponse(
        items=[_conversation_response(item) for item in page.items],
        next_cursor=(encode_conversation_cursor(page.next_cursor) if page.next_cursor else None),
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def conversation_detail(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationResponse:
    """Read one owned active or archived conversation."""

    customer = _require_customer(customer_id)
    try:
        conversation = await _lifecycle(agent).detail(conversation_id, customer)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    return _conversation_response(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessageListResponse,
)
async def conversation_messages(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationMessageListResponse:
    """Read customer-visible transcript messages in chronological order."""

    customer = _require_customer(customer_id)
    try:
        page = await _lifecycle(agent).messages(conversation_id, customer, limit=limit, cursor=cursor)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_CURSOR"},
        ) from error
    return ConversationMessageListResponse(
        items=[_message_response(item) for item in page.items],
        next_cursor=encode_message_cursor(page.next_cursor) if page.next_cursor else None,
    )


@router.post("/{conversation_id}/archive", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationResponse:
    """Archive one owned conversation."""

    customer = _require_customer(customer_id)
    try:
        conversation = await _lifecycle(agent).archive(conversation_id, customer)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    return _conversation_response(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> Response:
    """Delete one owned conversation and its Agent memory."""

    customer = _require_customer(customer_id)
    try:
        await _lifecycle(agent).delete(conversation_id, customer)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/turns", response_model=ConversationTurnResponse)
async def conversation_turn(
    conversation_id: UUID,
    request: ConversationTurnRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationTurnResponse:
    """Submit or replay one idempotent turn for an owned active conversation."""

    customer = _require_customer(customer_id)
    lifecycle = _lifecycle(agent)
    try:
        conversation = await lifecycle.detail(conversation_id, customer)
        if conversation.state is ConversationState.ARCHIVED:
            raise ConversationArchivedError(str(conversation_id))
    except ConversationNotFoundError as error:
        raise _not_found() from error
    except ConversationArchivedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONVERSATION_ARCHIVED"},
        ) from error

    memory = getattr(agent, "services", None)
    begin = getattr(getattr(memory, "memory", None), "begin_core_turn", None)
    try:
        if begin is not None:
            start = await begin(
                session_id=str(conversation_id),
                customer_id=customer,
                client_turn_id=request.client_turn_id,
            )
            if isinstance(start, TurnBusy):
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    headers={"Retry-After": str(start.retry_after_seconds)},
                    content={
                        "code": "TURN_IN_PROGRESS",
                        "client_turn_id": str(request.client_turn_id),
                        "recovery_url": start.recovery_url,
                        "retry_after_seconds": start.retry_after_seconds,
                    },
                )
            if isinstance(start, TerminalReplay):
                return _turn_response(conversation_id, request.client_turn_id, start.result, lookup_facts_only=False)
            if isinstance(start, LeaseAcquired):
                try:
                    result = await run_turn(
                        agent.graph,
                        agent.services,
                        session_id=str(conversation_id),
                        customer_id=customer,
                        user_message=request.message,
                        client_turn_id=request.client_turn_id,
                        lease=start.lease,
                    )
                except CoreTurnLeaseStaleError as error:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"code": "TURN_LEASE_EXPIRED"},
                    ) from error
                except CoreTurnTimeoutError as error:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        headers={"Retry-After": "5"},
                        detail={
                            "code": "TURN_TIMEOUT",
                            "client_turn_id": str(request.client_turn_id),
                            "retry_after_seconds": 5,
                        },
                    ) from error
                return _turn_response(conversation_id, request.client_turn_id, result, lookup_facts_only=False)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    except TurnFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TURN_PREVIOUSLY_FAILED", "category": error.category},
        ) from error
    except TurnPersistenceError as error:
        # Lượt chạy xong nhưng không ghi được: KHÔNG trả kết quả như đã hoàn tất.
        # Khách gửi lại đúng `client_turn_id` là đi tiếp bình thường.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "2"},
            detail={
                "code": "TURN_NOT_PERSISTED",
                "client_turn_id": error.client_turn_id,
                "retry_after_seconds": 2,
            },
        ) from error

    # Fallback path khi services chưa cài begin_core_turn (lõi cũ tự claim).
    try:
        result = await run_turn(
            agent.graph,
            agent.services,
            session_id=str(conversation_id),
            customer_id=customer,
            user_message=request.message,
            client_turn_id=request.client_turn_id,
        )
    except ConversationNotFoundError as error:
        raise _not_found() from error
    except TurnInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TURN_IN_PROGRESS"},
        ) from error
    except TurnFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TURN_PREVIOUSLY_FAILED", "category": error.category},
        ) from error
    except TurnPersistenceError as error:
        # Lượt chạy xong nhưng không ghi được: KHÔNG trả kết quả như đã hoàn tất.
        # Khách gửi lại đúng `client_turn_id` là đi tiếp bình thường.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "2"},
            detail={
                "code": "TURN_NOT_PERSISTED",
                "client_turn_id": error.client_turn_id,
                "retry_after_seconds": 2,
            },
        ) from error
    return _turn_response(conversation_id, request.client_turn_id, result, lookup_facts_only=False)


@router.get(
    "/{conversation_id}/turns/{client_turn_id}",
    response_model=ConversationTurnResponse,
)
async def recover_conversation_turn(
    conversation_id: UUID,
    client_turn_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationTurnResponse:
    """Recover an exact durable turn state after a missed HTTP/SSE response.

    Recovery matrix (PR1):
    - IN_PROGRESS → 202 (đang chạy, chờ lease expiry mới retry)
    - COMPLETED/WAITING_REVIEW/REJECTED/EXPIRED → 200 ConversationTurnResponse
    - FAILED → 409 TURN_PREVIOUSLY_FAILED
    - missing → 404 TURN_NOT_FOUND
    - stale lease → 409 TURN_LEASE_EXPIRED
    """

    customer = _require_customer(customer_id)
    try:
        outcome = await _lifecycle(agent).turn_outcome(conversation_id, customer, client_turn_id)
    except ConversationNotFoundError as error:
        raise _not_found() from error
    except CoreTurnLeaseStaleError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TURN_LEASE_EXPIRED"},
        ) from error
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TURN_NOT_FOUND"},
        )
    status_value = outcome.status.value
    if status_value == "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"code": "TURN_IN_PROGRESS"},
        )
    if status_value == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TURN_PREVIOUSLY_FAILED", "category": outcome.error_category},
        )
    if hasattr(outcome, "result_payload"):
        result = deserialize_turn_result(outcome.result_payload, outcome)
        return _turn_response(conversation_id, client_turn_id, result)
    # Compatibility for lifecycle adapters predating canonical payloads.
    return ConversationTurnResponse(
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        status=status_value,
        answer=outcome.answer,
        pending_question=outcome.pending_question,
        lookup_facts=[dict(item) for item in outcome.lookup_facts],
        terminal_reason=public_terminal_reason(outcome.terminal_reason),
        review_id=outcome.review_id,
    )


def _conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=conversation.conversation_id,
        state=conversation.state.value,
        created_at=conversation.created_at,
        last_activity_at=conversation.last_activity_at,
        archived_at=conversation.archived_at,
    )


def _message_response(message: ConversationMessage) -> ConversationMessageResponse:
    if message.message_id is None or message.created_at is None:
        raise RuntimeError("durable message metadata is missing")
    return ConversationMessageResponse(
        message_id=message.message_id,
        role=str(message.role),
        content=message.content,
        order=message.turn_index,
        created_at=message.created_at,
        client_turn_id=message.client_turn_id,
        review_id=message.review_id,
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "CONVERSATION_NOT_FOUND"},
    )


def _turn_response(
    conversation_id: UUID,
    client_turn_id: UUID,
    result: object,
    *,
    lookup_facts_only: bool = False,
) -> ConversationTurnResponse:
    """Dựng response từ TurnResult hoặc outcome — lookup_facts chuẩn hoá."""

    if lookup_facts_only:
        raise RuntimeError("lookup_facts_only chưa dùng; xem _recovery_response")
    return ConversationTurnResponse(
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        status=getattr(result, "turn_status", "COMPLETED"),
        answer=getattr(result, "answer", None),
        pending_question=getattr(result, "pending_question", None),
        lookup_facts=[facts_as_dict(fact) for fact in getattr(result, "lookup_facts", [])],
        terminal_reason=public_terminal_reason(getattr(result, "terminal_reason", None)),
        review_id=getattr(result, "review_id", None),
    )
