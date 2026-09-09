"""Customer conversation history and transcript management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.agents.api.dependencies import AgentDependency, CustomerDependency
from src.agents.api.routes import TurnResponse, _turn_response
from src.agents.chain import run_turn
from src.agents.errors import SessionOwnershipError

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    """Optional title/session seed for a customer conversation."""

    title: str | None = Field(default=None, max_length=200)
    session_id: UUID | None = None


class TurnRequest(BaseModel):
    """Idempotent customer turn payload."""

    message: str = Field(min_length=1)
    client_turn_id: str = Field(min_length=1, max_length=128)
    vehicle_type: str | None = None


class DeleteAllRequest(BaseModel):
    """Explicit destructive-action confirmation."""

    confirm: str


class MessageResponse(BaseModel):
    message_id: UUID
    role: str
    content: str
    client_turn_id: str | None
    created_at: datetime


class ConversationResponse(BaseModel):
    conversation_id: UUID
    session_id: UUID
    title: str | None = None
    status: str
    assigned_advisor_id: str | None = None
    last_activity_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class DeleteAllResponse(BaseModel):
    deleted_count: int


def _service(agent, customer_id: str | None):
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    if agent is None or agent.services.conversation is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="conversation unavailable")
    return agent.services.conversation


def _summary(item) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=item.session_id,
        session_id=item.session_id,
        status=item.status,
        assigned_advisor_id=item.assigned_advisor_id,
        last_activity_at=item.last_activity_at,
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationResponse:
    """Create an empty owned conversation."""

    service = _service(agent, customer_id)
    session_id = request.session_id or uuid4()
    try:
        await service.open_session(str(session_id), customer_id)
    except SessionOwnershipError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation access forbidden") from error
    items = await service.list_conversations(customer_id)
    return _summary(next(item for item in items if item.session_id == session_id))


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationListResponse:
    """List the authenticated customer's conversations."""

    service = _service(agent, customer_id)
    return ConversationListResponse(items=[_summary(item) for item in await service.list_conversations(customer_id)])


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationDetailResponse:
    """Return one conversation and its durable transcript."""

    service = _service(agent, customer_id)
    items = await service.list_conversations(customer_id)
    item = next((candidate for candidate in items if str(candidate.session_id) == str(conversation_id)), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    messages = await service.list_messages(str(conversation_id), customer_id, 200)
    return ConversationDetailResponse(
        **_summary(item).model_dump(),
        messages=[
            MessageResponse(
                message_id=message.message_id,
                role=message.role,
                content=message.content,
                client_turn_id=message.client_turn_id,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_conversation_messages(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> MessageListResponse:
    """Return transcript messages for one conversation."""

    service = _service(agent, customer_id)
    messages = await service.list_messages(str(conversation_id), customer_id, 200)
    return MessageListResponse(
        items=[
            MessageResponse(
                message_id=message.message_id,
                role=message.role,
                content=message.content,
                client_turn_id=message.client_turn_id,
                created_at=message.created_at,
            )
            for message in messages
        ]
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> None:
    """Delete one conversation and cascaded state."""

    service = _service(agent, customer_id)
    if not await service.delete_conversation(str(conversation_id), customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")


@router.delete("", response_model=DeleteAllResponse)
async def delete_all_conversations(
    request: DeleteAllRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> DeleteAllResponse:
    """Delete all customer conversations only after explicit confirmation."""

    if request.confirm != "DELETE_ALL":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="confirm must be DELETE_ALL")
    service = _service(agent, customer_id)
    return DeleteAllResponse(deleted_count=await service.delete_all_conversations(customer_id))


@router.delete("/{conversation_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def delete_messages(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> None:
    """Clear transcript messages while preserving the conversation shell."""

    service = _service(agent, customer_id)
    try:
        await service.delete_conversation_messages(str(conversation_id), customer_id)
    except SessionOwnershipError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation access forbidden") from error


@router.post("/{conversation_id}/archive", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: UUID,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> ConversationResponse:
    """Archive one customer conversation."""

    service = _service(agent, customer_id)
    if not await service.archive_conversation(str(conversation_id), customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    items = await service.list_conversations(customer_id)
    return _summary(next(item for item in items if item.session_id == conversation_id))


@router.post("/{conversation_id}/turns", response_model=TurnResponse)
async def conversation_turn(
    conversation_id: UUID,
    request: TurnRequest,
    agent=AgentDependency,
    customer_id: str | None = CustomerDependency,
) -> TurnResponse:
    """Run the agent once; retries with the same client turn are replayed."""

    _service(agent, customer_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent unavailable")
    result = await run_turn(
        agent.graph,
        agent.services,
        session_id=str(conversation_id),
        customer_id=customer_id,
        user_message=request.message,
        client_turn_id=request.client_turn_id,
        explicit_vehicle_type=request.vehicle_type,
    )
    return _turn_response(result)


__all__ = ["router"]
