"""FastAPI routes for staff self-service authentication."""

from secrets import token_urlsafe

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from src.auth.application.ports import AbuseLimitExceededError
from src.auth.domain.errors import AuthDomainError, TemporaryPasswordRequiredError
from src.auth.presentation.routes import (
    RATE_LIMIT_RETRY_AFTER,
    _error,
    _message,
    _resources,
    _set_session_cookies,
)
from src.auth.presentation.schemas import AuthCredentials, AuthMessage, StaffPasswordSetupRequest

router = APIRouter(prefix="/auth/staff", tags=["auth-staff"])


@router.post("/login", response_model=AuthMessage)
async def staff_login(payload: AuthCredentials, request: Request, response: Response) -> AuthMessage | JSONResponse:
    resources = _resources(request)
    if resources is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    try:
        session = await resources.services.staff.login(payload.email, payload.password)
    except AbuseLimitExceededError:
        return _error(
            "invalid_credentials",
            status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after=RATE_LIMIT_RETRY_AFTER,
        )
    except TemporaryPasswordRequiredError:
        return _error("temporary_password_required", status.HTTP_409_CONFLICT)
    if session is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    _set_session_cookies(response, session.access_token, session.refresh_token.reveal(), token_urlsafe(32))
    return _message("logged_in", response)


@router.post("/complete-password", response_model=AuthMessage)
async def complete_temporary_password(
    payload: StaffPasswordSetupRequest, request: Request, response: Response
) -> AuthMessage | JSONResponse:
    resources = _resources(request)
    if resources is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    staff = resources.services.staff
    try:
        identity = await staff.identify_for_password_setup(payload.email, payload.temporary_password)
    except AbuseLimitExceededError:
        return _error(
            "invalid_credentials",
            status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after=RATE_LIMIT_RETRY_AFTER,
        )
    if identity is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    try:
        await staff.complete_temporary_password_change(identity, payload.new_password)
    except AuthDomainError:
        return _error("weak_password", status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        issued = await staff.login_after_password_setup(identity)
    except AbuseLimitExceededError:
        return _error(
            "invalid_credentials",
            status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after=RATE_LIMIT_RETRY_AFTER,
        )
    if issued is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    _set_session_cookies(response, issued.access_token, issued.refresh_token.reveal(), token_urlsafe(32))
    return _message("password_set", response)


__all__ = ["router"]
