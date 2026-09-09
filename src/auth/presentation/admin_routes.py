"""FastAPI routes for administrative user management."""

from typing import assert_never

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse

from src.auth.application.contracts import UserPage
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.values import UserId
from src.auth.presentation.routes import (
    _access,
    _csrf_failed,
    _csrf_valid,
    _error,
    _no_store,
    _resources,
)
from src.auth.presentation.schemas import AuthMessage, RoleRequest, UserPageResponse, UserSummaryResponse

router = APIRouter(prefix="/auth/admin", tags=["auth-admin"])


async def _identity(request: Request) -> tuple[UserId, User] | None:
    """Return authenticated identity, or None when Auth/session is unavailable."""
    resources = _resources(request)
    access = _access(request)
    if resources is None or access is None:
        return None
    return await resources.services.customer.validate_access(access)


def _to_response(page: UserPage) -> UserPageResponse:
    """Map application listing data to its stable HTTP representation."""
    return UserPageResponse(
        items=[
            UserSummaryResponse(
                id=str(item.id),
                email=str(item.email),
                role=item.role.value,
                state=item.state.value,
                created_at=item.created_at,
                last_activity_at=item.last_activity_at,
            )
            for item in page.items
        ],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/users", response_model=UserPageResponse)
async def list_users(
    request: Request,
    response: Response,
    role: str | None = Query(default=None),
    state: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> UserPageResponse | JSONResponse:
    """List accounts for an administrator with bounded filters and pagination."""
    identity = await _identity(request)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    try:
        parsed_role = Role(role) if role else None
        parsed_state = AccountState(state) if state else None
    except ValueError:
        return _error("invalid_filter", status.HTTP_422_UNPROCESSABLE_CONTENT)
    try:
        result = await _resources(request).services.staff.list_users(
            identity[0],
            role=parsed_role,
            state=parsed_state,
            email_query=q,
            page=page,
            page_size=page_size,
        )
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    _no_store(response)
    return _to_response(result)


@router.patch("/users/{user_id}/role", response_model=AuthMessage)
async def change_user_role(
    user_id: str, payload: RoleRequest, request: Request, response: Response
) -> AuthMessage | JSONResponse:
    """Change one staff role after CSRF and session checks."""
    if not _csrf_valid(request):
        return _csrf_failed()
    identity = await _identity(request)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    match payload.role:
        case "advisor" | "admin":
            target_role = Role(payload.role)
        case "customer":
            return _error("invalid_role", status.HTTP_422_UNPROCESSABLE_CONTENT)
        case unreachable:
            assert_never(unreachable)
    try:
        await _resources(request).services.staff.change_role(identity[0], UserId(user_id), target_role)
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    _no_store(response)
    return AuthMessage(message="role_changed")


@router.post("/users/{user_id}/disable", response_model=AuthMessage)
async def disable_user(user_id: str, request: Request, response: Response) -> AuthMessage | JSONResponse:
    """Disable one account after CSRF and session checks."""
    if not _csrf_valid(request):
        return _csrf_failed()
    identity = await _identity(request)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    try:
        await _resources(request).services.staff.disable_user(identity[0], UserId(user_id))
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    _no_store(response)
    return AuthMessage(message="user_disabled")


@router.post("/users/{user_id}/enable", response_model=AuthMessage)
async def enable_user(user_id: str, request: Request, response: Response) -> AuthMessage | JSONResponse:
    """Enable one disabled account after CSRF and session checks."""
    if not _csrf_valid(request):
        return _csrf_failed()
    identity = await _identity(request)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    try:
        await _resources(request).services.staff.enable_user(identity[0], UserId(user_id))
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    _no_store(response)
    return AuthMessage(message="user_enabled")


@router.post("/users/{user_id}/activate", response_model=AuthMessage)
async def activate_user(user_id: str, request: Request, response: Response) -> AuthMessage | JSONResponse:
    """Activate or confirm a pending account after CSRF and session checks."""
    if not _csrf_valid(request):
        return _csrf_failed()
    identity = await _identity(request)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    try:
        await _resources(request).services.staff.activate_user(identity[0], UserId(user_id))
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    _no_store(response)
    return AuthMessage(message="user_activated")


__all__ = ["router"]
