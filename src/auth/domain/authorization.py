"""Action and Scope based, default-deny authorization (Role × Permission × Scope).

Permission is a lookup in an explicit `(role, permission)` table, not a comparison
of role ranks. Rank ordering (`admin > advisor > customer`) silently grants every
future action to the highest role. Here an undeclared pair is denied.

This module formalizes:
1. Role: CUSTOMER, ADVISOR, ADMIN
2. Permission / Action: Explicit operations across chat, booking, HITL, live-chat,
   observability, catalog, documents, notices, and user management.
3. Scope: PUBLIC, OWN, ASSIGNED, CLAIMED, GLOBAL
4. Centralized Authorization Decision Engine and Resource Policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, unique
from typing import Final

from src.auth.domain.errors import AuthorizationError, LastAdminProtectedError


@unique
class Role(StrEnum):
    CUSTOMER = "customer"
    ADVISOR = "advisor"
    ADMIN = "admin"


@unique
class Scope(StrEnum):
    PUBLIC = "public"
    OWN = "own"
    ASSIGNED = "assigned"
    CLAIMED = "claimed"
    GLOBAL = "global"


@unique
class Permission(StrEnum):
    # Self-service
    READ_OWN_PROFILE = "read_own_profile"
    CHANGE_OWN_PASSWORD = "change_own_password"
    LIST_OWN_SESSIONS = "list_own_sessions"
    REVOKE_OWN_SESSIONS = "revoke_own_sessions"

    # Staff administration
    CREATE_ADVISOR = "create_advisor"
    CREATE_ADMIN = "create_admin"
    DISABLE_USER = "disable_user"
    ENABLE_USER = "enable_user"
    LIST_USERS = "list_users"
    CHANGE_USER_ROLE = "change_user_role"
    REVOKE_OTHER_SESSIONS = "revoke_other_sessions"
    RESET_OTHER_PASSWORD = "reset_other_password"

    # Chat & Conversation
    CHAT_CREATE = "chat_create"
    CHAT_VIEW_OWN = "chat_view_own"
    CHAT_VIEW_ASSIGNED = "chat_view_assigned"
    CHAT_AUDIT = "chat_audit"
    CONVERSATION_VIEW_OWN = "conversation_view_own"
    CONVERSATION_VIEW_ASSIGNED = "conversation_view_assigned"
    CONVERSATION_RESTART_OWN = "conversation_restart_own"
    CONVERSATION_DELETE_GLOBAL = "conversation_delete_global"

    # AI Observability & Trace
    AI_TRACE_VIEW = "ai_trace_view"
    AI_COST_VIEW = "ai_cost_view"

    # Test-drive Booking
    BOOKING_CREATE = "booking_create"
    BOOKING_VIEW_OWN = "booking_view_own"
    BOOKING_VIEW_ASSIGNED = "booking_view_assigned"
    BOOKING_UPDATE_OWN = "booking_update_own"
    BOOKING_UPDATE_ASSIGNED = "booking_update_assigned"
    BOOKING_MANAGE_GLOBAL = "booking_manage_global"

    # HITL Review Queue
    HITL_VIEW = "hitl_view"
    HITL_CLAIM = "hitl_claim"
    HITL_RESOLVE = "hitl_resolve"
    HITL_MANAGE = "hitl_manage"

    # Live Chat
    LIVE_CHAT_JOIN_OWN = "live_chat_join_own"
    LIVE_CHAT_VIEW_ASSIGNED = "live_chat_view_assigned"
    LIVE_CHAT_TAKEOVER = "live_chat_takeover"
    LIVE_CHAT_SEND = "live_chat_send"
    LIVE_CHAT_CLOSE = "live_chat_close"

    # Customer Profiles & Leads
    CUSTOMER_VIEW_OWN = "customer_view_own"
    CUSTOMER_VIEW_ASSIGNED = "customer_view_assigned"
    CUSTOMER_VIEW_ALL = "customer_view_all"
    CUSTOMER_ASSIGN = "customer_assign"
    CONVERSATION_REASSIGN = "conversation_reassign"

    # Document & RAG Knowledge
    READ_DOCUMENT = "read_document"
    CREATE_DOCUMENT = "create_document"
    ARCHIVE_DOCUMENT = "archive_document"
    DOCUMENT_VIEW = "document_view"
    DOCUMENT_MANAGE = "document_manage"
    POLICY_NOTIFICATION_READ = "policy_notification_read"
    POLICY_NOTIFICATION_MANAGE = "policy_notification_manage"

    # Images
    UPLOAD_IMAGE = "upload_image"
    READ_IMAGE = "read_image"
    DELETE_IMAGE = "delete_image"

    # Catalog
    CATALOG_VIEW = "catalog_view"
    CATALOG_MANAGE = "catalog_manage"

    # Internal Notices & Analytics
    NOTICE_VIEW = "notice_view"
    NOTICE_MANAGE = "notice_manage"
    FUNNEL_ANALYTICS_VIEW = "funnel_analytics_view"


# Compatibility alias: Action is identical to Permission
Action = Permission


# --- Group Definitions ---

_SELF_SERVICE: Final[frozenset[Permission]] = frozenset(
    {
        Permission.READ_OWN_PROFILE,
        Permission.CHANGE_OWN_PASSWORD,
        Permission.LIST_OWN_SESSIONS,
        Permission.REVOKE_OWN_SESSIONS,
    }
)

_CUSTOMER_PERMISSIONS: Final[frozenset[Permission]] = frozenset(
    {
        *_SELF_SERVICE,
        Permission.CHAT_CREATE,
        Permission.CHAT_VIEW_OWN,
        Permission.CONVERSATION_VIEW_OWN,
        Permission.CONVERSATION_RESTART_OWN,
        Permission.BOOKING_CREATE,
        Permission.BOOKING_VIEW_OWN,
        Permission.BOOKING_UPDATE_OWN,
        Permission.LIVE_CHAT_JOIN_OWN,
        Permission.LIVE_CHAT_SEND,
        Permission.CUSTOMER_VIEW_OWN,
        Permission.READ_DOCUMENT,
        Permission.DOCUMENT_VIEW,
        Permission.POLICY_NOTIFICATION_READ,
        Permission.READ_IMAGE,
        Permission.CATALOG_VIEW,
    }
)

_ADVISOR_PERMISSIONS: Final[frozenset[Permission]] = frozenset(
    {
        *_SELF_SERVICE,
        Permission.CHAT_VIEW_ASSIGNED,
        Permission.CONVERSATION_VIEW_ASSIGNED,
        Permission.BOOKING_VIEW_ASSIGNED,
        Permission.BOOKING_UPDATE_ASSIGNED,
        Permission.HITL_VIEW,
        Permission.HITL_CLAIM,
        Permission.HITL_RESOLVE,
        Permission.LIVE_CHAT_VIEW_ASSIGNED,
        Permission.LIVE_CHAT_TAKEOVER,
        Permission.LIVE_CHAT_SEND,
        Permission.LIVE_CHAT_CLOSE,
        Permission.CUSTOMER_VIEW_ASSIGNED,
        Permission.NOTICE_VIEW,
        Permission.FUNNEL_ANALYTICS_VIEW,
        Permission.READ_DOCUMENT,
        Permission.DOCUMENT_VIEW,
        Permission.READ_IMAGE,
        Permission.UPLOAD_IMAGE,
        Permission.DELETE_IMAGE,
        Permission.CATALOG_VIEW,
    }
)

_ADMIN_PERMISSIONS: Final[frozenset[Permission]] = frozenset(
    {
        *_CUSTOMER_PERMISSIONS,
        *_ADVISOR_PERMISSIONS,
        Permission.CREATE_ADVISOR,
        Permission.CREATE_ADMIN,
        Permission.DISABLE_USER,
        Permission.ENABLE_USER,
        Permission.LIST_USERS,
        Permission.CHANGE_USER_ROLE,
        Permission.REVOKE_OTHER_SESSIONS,
        Permission.RESET_OTHER_PASSWORD,
        Permission.CHAT_AUDIT,
        Permission.AI_TRACE_VIEW,
        Permission.AI_COST_VIEW,
        Permission.CONVERSATION_DELETE_GLOBAL,
        Permission.CONVERSATION_REASSIGN,
        Permission.BOOKING_MANAGE_GLOBAL,
        Permission.CUSTOMER_ASSIGN,
        Permission.CUSTOMER_VIEW_ALL,
        Permission.HITL_MANAGE,
        Permission.CREATE_DOCUMENT,
        Permission.ARCHIVE_DOCUMENT,
        Permission.DOCUMENT_MANAGE,
        Permission.POLICY_NOTIFICATION_MANAGE,
        Permission.CATALOG_MANAGE,
        Permission.NOTICE_MANAGE,
    }
)

# The authoritative allow table. Every pair not listed here is denied.
ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = {
    Role.CUSTOMER: _CUSTOMER_PERMISSIONS,
    Role.ADVISOR: _ADVISOR_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
}

# Compatibility alias
PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = ROLE_PERMISSIONS

# Actions that only ever apply to somebody else's account.
_TARGET_MUST_DIFFER: Final[frozenset[Permission]] = frozenset(
    {
        Permission.REVOKE_OTHER_SESSIONS,
        Permission.RESET_OTHER_PASSWORD,
        Permission.DISABLE_USER,
        Permission.ENABLE_USER,
        Permission.CHANGE_USER_ROLE,
    }
)


@dataclass(frozen=True)
class AuthDecision:
    """The result of an authorization check."""

    allowed: bool
    role: Role
    permission: Permission
    scope: Scope
    reason: str | None = None
    policy: str | None = None


def is_allowed(role: Role, action: Permission | Action) -> bool:
    """Return whether `role` may perform `action`. Unknown pairs are denied."""
    try:
        permission = Permission(action)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def authorize(
    role: Role,
    action: Permission | Action,
    *,
    actor_id: str | None = None,
    target_id: str | None = None,
) -> None:
    """Raise `AuthorizationError` unless `role` may perform `action` on the target.

    The message never names the target account: an authorization failure must not
    double as an account-existence oracle.
    """
    try:
        permission = Permission(action)
    except ValueError as exc:
        raise AuthorizationError(f"unknown permission {action}") from exc

    if not is_allowed(role, permission):
        raise AuthorizationError(f"role {role.value} may not perform {permission.value}")

    if permission in _TARGET_MUST_DIFFER and actor_id is not None and target_id == actor_id:
        raise AuthorizationError(f"{permission.value} requires a target other than the actor")


def assert_not_last_active_admin(action: Permission | Action, remaining_active_admins: int) -> None:
    """Refuse an action that would leave the system with no active Admin."""
    try:
        permission = Permission(action)
    except ValueError:
        return
    if permission in {Permission.DISABLE_USER, Permission.CHANGE_USER_ROLE} and remaining_active_admins <= 0:
        raise LastAdminProtectedError("the last active admin cannot be changed")


# --- Policy Deciders ---


class CustomerOwnershipPolicy:
    """Policy ensuring a customer only accesses resources they own."""

    @staticmethod
    def evaluate(
        role: Role,
        permission: Permission,
        *,
        actor_id: str | None,
        resource_customer_id: str | None,
    ) -> AuthDecision:
        if not is_allowed(role, permission):
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.OWN,
                reason="ROLE_NOT_PERMITTED",
                policy="CustomerOwnershipPolicy",
            )
        if role == Role.ADMIN:
            return AuthDecision(
                allowed=True,
                role=role,
                permission=permission,
                scope=Scope.GLOBAL,
                policy="CustomerOwnershipPolicy",
            )
        if actor_id is None or resource_customer_id is None:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.OWN,
                reason="MISSING_IDENTITY_OR_OWNER",
                policy="CustomerOwnershipPolicy",
            )
        if actor_id != resource_customer_id and resource_customer_id != f"anon-{actor_id}":
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.OWN,
                reason="RESOURCE_OWNED_BY_ANOTHER_CUSTOMER",
                policy="CustomerOwnershipPolicy",
            )
        return AuthDecision(
            allowed=True,
            role=role,
            permission=permission,
            scope=Scope.OWN,
            policy="CustomerOwnershipPolicy",
        )


class AdvisorAssignmentPolicy:
    """Policy ensuring an advisor only accesses resources assigned to them."""

    @staticmethod
    def evaluate(
        role: Role,
        permission: Permission,
        *,
        actor_id: str | None,
        assigned_advisor_id: str | None,
    ) -> AuthDecision:
        if not is_allowed(role, permission):
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.ASSIGNED,
                reason="ROLE_NOT_PERMITTED",
                policy="AdvisorAssignmentPolicy",
            )
        if role == Role.ADMIN:
            return AuthDecision(
                allowed=True,
                role=role,
                permission=permission,
                scope=Scope.GLOBAL,
                policy="AdvisorAssignmentPolicy",
            )
        if actor_id is None:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.ASSIGNED,
                reason="MISSING_STAFF_IDENTITY",
                policy="AdvisorAssignmentPolicy",
            )
        if assigned_advisor_id is not None and assigned_advisor_id != actor_id:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.ASSIGNED,
                reason="RESOURCE_ASSIGNED_TO_ANOTHER_ADVISOR",
                policy="AdvisorAssignmentPolicy",
            )
        return AuthDecision(
            allowed=True,
            role=role,
            permission=permission,
            scope=Scope.ASSIGNED,
            policy="AdvisorAssignmentPolicy",
        )


class HITLClaimPolicy:
    """Policy ensuring an advisor only resolves tickets they hold valid lease for."""

    @staticmethod
    def evaluate(
        role: Role,
        permission: Permission,
        *,
        actor_id: str | None,
        claimed_by: str | None,
        lease_expires_at: datetime | None,
        now: datetime,
        status: str,
    ) -> AuthDecision:
        if not is_allowed(role, permission):
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.CLAIMED,
                reason="ROLE_NOT_PERMITTED",
                policy="HITLClaimPolicy",
            )
        if role == Role.ADMIN:
            return AuthDecision(
                allowed=True,
                role=role,
                permission=permission,
                scope=Scope.GLOBAL,
                policy="HITLClaimPolicy",
            )
        if actor_id is None:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.CLAIMED,
                reason="MISSING_STAFF_IDENTITY",
                policy="HITLClaimPolicy",
            )
        if status != "PENDING":
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.CLAIMED,
                reason="TICKET_NOT_IN_PENDING_STATE",
                policy="HITLClaimPolicy",
            )
        if claimed_by is not None and claimed_by != actor_id:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.CLAIMED,
                reason="TICKET_CLAIMED_BY_ANOTHER_ADVISOR",
                policy="HITLClaimPolicy",
            )
        if lease_expires_at is not None and lease_expires_at <= now:
            return AuthDecision(
                allowed=False,
                role=role,
                permission=permission,
                scope=Scope.CLAIMED,
                reason="TICKET_LEASE_EXPIRED",
                policy="HITLClaimPolicy",
            )
        return AuthDecision(
            allowed=True,
            role=role,
            permission=permission,
            scope=Scope.CLAIMED,
            policy="HITLClaimPolicy",
        )


def evaluate_authorization(
    role: Role,
    permission: Permission,
    scope: Scope = Scope.PUBLIC,
    *,
    actor_id: str | None = None,
    resource_owner_id: str | None = None,
    assigned_advisor_id: str | None = None,
    claimed_by: str | None = None,
    lease_expires_at: datetime | None = None,
    now: datetime | None = None,
    ticket_status: str | None = None,
) -> AuthDecision:
    """Central authorization decision engine."""
    if not is_allowed(role, permission):
        return AuthDecision(
            allowed=False,
            role=role,
            permission=permission,
            scope=scope,
            reason="ROLE_NOT_PERMITTED",
            policy="RolePolicy",
        )

    if scope == Scope.PUBLIC or role == Role.ADMIN:
        return AuthDecision(
            allowed=True,
            role=role,
            permission=permission,
            scope=Scope.GLOBAL if role == Role.ADMIN else Scope.PUBLIC,
            policy="AdminOrPublicPolicy",
        )

    if scope == Scope.OWN:
        return CustomerOwnershipPolicy.evaluate(
            role,
            permission,
            actor_id=actor_id,
            resource_customer_id=resource_owner_id,
        )

    if scope == Scope.ASSIGNED:
        return AdvisorAssignmentPolicy.evaluate(
            role,
            permission,
            actor_id=actor_id,
            assigned_advisor_id=assigned_advisor_id,
        )

    if scope == Scope.CLAIMED:
        current_now = now or datetime.now().astimezone()
        return HITLClaimPolicy.evaluate(
            role,
            permission,
            actor_id=actor_id,
            claimed_by=claimed_by,
            lease_expires_at=lease_expires_at,
            now=current_now,
            status=ticket_status or "PENDING",
        )

    return AuthDecision(
        allowed=True,
        role=role,
        permission=permission,
        scope=scope,
        policy="DefaultAllowPolicy",
    )
