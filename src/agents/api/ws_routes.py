"""WebSocket endpoints for customer and advisor live chat rooms with strict authorization."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.agents.api.dependencies import get_agent
from src.agents.api.ws_auth import websocket_customer, websocket_staff
from src.agents.api.ws_manager import ws_manager
from src.auth.domain.audit import log_websocket_auth_denied
from src.auth.domain.authorization import Role

router = APIRouter(tags=["advisor-live-chat"])


@router.websocket("/ws/conversations/{conversation_id}")
async def customer_conversation_ws(websocket: WebSocket, conversation_id: UUID, token: str | None = None) -> None:
    """Customer room: enforce customer ownership before accepting WebSocket."""

    customer_id = await websocket_customer(websocket, token)
    agent = get_agent(websocket)
    if agent is None or agent.services.conversation is None:
        await websocket.close(code=1013)
        return
    try:
        await agent.services.conversation.list_messages(str(conversation_id), customer_id, 1)
    except Exception:
        log_websocket_auth_denied(
            actor_id=customer_id,
            role=Role.CUSTOMER,
            conversation_id=str(conversation_id),
            reason="CUSTOMER_NOT_OWNER",
        )
        await websocket.close(code=4003, reason="conversation access forbidden")
        return
    key = f"customer:{customer_id}"
    await ws_manager.connect(str(conversation_id), key, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(str(conversation_id), key)


@router.websocket("/ws/advisor/conversations/{conversation_id}")
async def advisor_conversation_ws(websocket: WebSocket, conversation_id: UUID, token: str | None = None) -> None:
    """Advisor/Admin room: enforce advisor assignment before accepting WebSocket."""

    identity = await websocket_staff(websocket, token)
    agent = get_agent(websocket)
    if agent is None or agent.services.conversation is None:
        await websocket.close(code=1013)
        return

    if identity.role != Role.ADMIN:
        try:
            detail = await agent.services.conversation.staff_conversation_detail(
                str(conversation_id), requester_id=identity.staff_id, role=identity.role.value
            )
            if detail is None:
                log_websocket_auth_denied(
                    actor_id=identity.staff_id,
                    role=identity.role,
                    conversation_id=str(conversation_id),
                    reason="ADVISOR_NOT_ASSIGNED",
                )
                await websocket.close(code=4003, reason="conversation access forbidden")
                return
        except Exception:
            log_websocket_auth_denied(
                actor_id=identity.staff_id,
                role=identity.role,
                conversation_id=str(conversation_id),
                reason="ADVISOR_AUTH_ERROR",
            )
            await websocket.close(code=4003, reason="conversation access forbidden")
            return

    key = f"{identity.role.value}:{identity.staff_id}"
    await ws_manager.connect(str(conversation_id), key, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(str(conversation_id), key)
