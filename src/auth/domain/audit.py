"""Structured security audit logging for authorization and access control events.

Complies with AGENTS.md rules:
- No passwords, credentials, JWTs, or secrets are ever logged.
- Events use structured JSON-formatted log messages.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.auth.domain.authorization import Permission, Role, Scope

_logger = logging.getLogger("auth.security.audit")


def _event_payload(
    event_type: str,
    *,
    actor_id: str | None,
    role: Role | str | None,
    permission: Permission | str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    scope: Scope | str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    """Build sanitized JSON event string without leaking secrets."""
    payload: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "actor_id": str(actor_id) if actor_id is not None else "anonymous",
        "role": getattr(role, "value", str(role)) if role is not None else None,
    }
    if permission is not None:
        payload["permission"] = getattr(permission, "value", str(permission))
    if resource_type is not None:
        payload["resource_type"] = resource_type
    if resource_id is not None:
        payload["resource_id"] = str(resource_id)
    if scope is not None:
        payload["scope"] = getattr(scope, "value", str(scope))
    if reason is not None:
        payload["reason"] = reason
    if details:
        # Exclude any potential sensitive keys
        sanitized_details = {
            k: v
            for k, v in details.items()
            if k.lower() not in {"password", "token", "secret", "key", "access", "refresh", "jwt"}
        }
        payload["details"] = sanitized_details

    return json.dumps(payload, ensure_ascii=False)


def log_authorization_denied(
    *,
    actor_id: str | None,
    role: Role | str | None,
    permission: Permission | str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    scope: Scope | str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an explicit authorization denial."""
    msg = _event_payload(
        "AUTHORIZATION_DENIED",
        actor_id=actor_id,
        role=role,
        permission=permission,
        resource_type=resource_type,
        resource_id=resource_id,
        scope=scope,
        reason=reason,
        details=details,
    )
    _logger.warning(msg)


def log_hitl_claim_conflict(
    *,
    actor_id: str,
    review_id: str,
    claimed_by: str | None,
    lease_expires_at: datetime | None,
) -> None:
    """Log a failed HITL claim attempt due to existing active lease."""
    msg = _event_payload(
        "HITL_CLAIM_CONFLICT",
        actor_id=actor_id,
        role=Role.ADVISOR,
        permission=Permission.HITL_CLAIM,
        resource_type="review_queue",
        resource_id=review_id,
        scope=Scope.CLAIMED,
        reason="ALREADY_CLAIMED",
        details={
            "currently_claimed_by": claimed_by,
            "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
        },
    )
    _logger.warning(msg)


def log_hitl_lease_expired(
    *,
    actor_id: str,
    review_id: str,
    lease_expires_at: datetime | None,
) -> None:
    """Log a failed HITL resolve attempt due to expired 15-minute lease."""
    msg = _event_payload(
        "HITL_LEASE_EXPIRED",
        actor_id=actor_id,
        role=Role.ADVISOR,
        permission=Permission.HITL_RESOLVE,
        resource_type="review_queue",
        resource_id=review_id,
        scope=Scope.CLAIMED,
        reason="LEASE_EXPIRED",
        details={
            "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
        },
    )
    _logger.warning(msg)


def log_admin_override(
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict | None = None,
) -> None:
    """Audit log an administrative override action."""
    msg = _event_payload(
        "ADMIN_OVERRIDE",
        actor_id=actor_id,
        role=Role.ADMIN,
        resource_type=resource_type,
        resource_id=resource_id,
        scope=Scope.GLOBAL,
        reason=action,
        details=details,
    )
    _logger.info(msg)


def log_websocket_auth_denied(
    *,
    actor_id: str | None,
    role: Role | str | None,
    conversation_id: str,
    reason: str,
) -> None:
    """Log a WebSocket connection rejection due to lack of ownership or assignment."""
    msg = _event_payload(
        "WEBSOCKET_AUTH_DENIED",
        actor_id=actor_id,
        role=role,
        resource_type="conversation_session",
        resource_id=conversation_id,
        reason=reason,
    )
    _logger.warning(msg)
