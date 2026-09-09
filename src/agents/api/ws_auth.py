"""JWT query-token authentication for browser WebSocket connections."""

from __future__ import annotations

from fastapi import WebSocket, WebSocketException

from src.agents.api.security import StaffIdentity
from src.auth.domain.authorization import Role


async def websocket_staff(websocket: WebSocket, token: str | None) -> StaffIdentity:
    """Validate a query JWT through the application Auth composition."""

    if not token:
        raise WebSocketException(code=4001, reason="authentication required")
    auth = getattr(websocket.app.state, "auth", None)
    if auth is None or not auth.enabled:
        raise WebSocketException(code=4001, reason="authentication unavailable")
    identity = await auth.resources.services.customer.validate_access(token)
    if identity is None:
        raise WebSocketException(code=4001, reason="invalid token")
    user = await auth.resources.services.customer.me(token)
    if user is None or user.role not in {Role.ADVISOR, Role.ADMIN}:
        raise WebSocketException(code=4003, reason="staff role required")
    return StaffIdentity(staff_id=str(identity[0]), role=user.role)


async def websocket_customer(websocket: WebSocket, token: str | None) -> str:
    """Validate a customer query JWT and return its user ID."""

    if not token:
        raise WebSocketException(code=4001, reason="authentication required")
    auth = getattr(websocket.app.state, "auth", None)
    if auth is None or not auth.enabled:
        raise WebSocketException(code=4001, reason="authentication unavailable")
    identity = await auth.resources.services.customer.validate_access(token)
    if identity is None:
        raise WebSocketException(code=4001, reason="invalid token")
    return str(identity[0])
