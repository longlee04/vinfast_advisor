"""FastAPI routes for the Auth HTTP boundary."""

from hmac import compare_digest
from secrets import token_urlsafe
from typing import Final
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.auth.application.ports import AbuseLimitExceededError
from src.auth.contracts import (
    ACCESS_COOKIE_NAME,
    ACCESS_COOKIE_PATH,
    COOKIE_SAMESITE,
    CSRF_COOKIE_NAME,
    CSRF_COOKIE_PATH,
    CSRF_HEADER_NAME,
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_TTL_SECONDS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
)
from src.auth.domain.authorization import Role
from src.auth.domain.errors import (
    AuthDomainError,
    InvalidEmailError,
    PasswordPolicyError,
)
from src.auth.presentation.schemas import (
    AuthCredentials,
    AuthError,
    AuthMessage,
    EmailRequest,
    PasswordRequest,
    ProfileResponse,
    ResetPasswordRequest,
    StaffCreateRequest,
    UpdateProfileRequest,
    VerificationRequest,
)

RATE_LIMIT_RETRY_AFTER: Final[str] = "60"
router = APIRouter(prefix="/auth", tags=["auth"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _error(code: str, http_status: int, *, retry_after: str | None = None) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return JSONResponse(
        status_code=http_status,
        content=AuthError(error=code).model_dump(),
        headers=headers,
    )


def _csrf_failed() -> JSONResponse:
    return _error("csrf_failed", status.HTTP_403_FORBIDDEN)


def _invalid_session(response: Response) -> JSONResponse:
    result = _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    _clear_session_cookies(result)
    return result


def _origin_matches(request: Request) -> bool:
    origin = request.headers.get("Origin")
    return origin == request.app.state.auth.frontend_origin


def _origin_failed(request: Request) -> JSONResponse | None:
    auth = getattr(request.app.state, "auth", None)
    if auth is not None and auth.enabled and not _origin_matches(request):
        return _error("origin_forbidden", status.HTTP_403_FORBIDDEN)
    return None


def _csrf_valid(request: Request) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    header = request.headers.get(CSRF_HEADER_NAME)
    return bool(cookie and header and compare_digest(cookie, header))


def _resources(request: Request):
    auth = getattr(request.app.state, "auth", None)
    if auth is None or not auth.enabled:
        return None
    return auth.resources


def _access(request: Request) -> str | None:
    cookie_val = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_val:
        return cookie_val
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def _refresh(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE_NAME)


def _set_session_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME, access_token, secure=True, httponly=True, samesite=COOKIE_SAMESITE, path=ACCESS_COOKIE_PATH
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        secure=True,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token, secure=True, httponly=False, samesite=COOKIE_SAMESITE, path=CSRF_COOKIE_PATH
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(
        ACCESS_COOKIE_NAME,
        path=ACCESS_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=CSRF_COOKIE_PATH,
        secure=True,
        httponly=False,
        samesite=COOKIE_SAMESITE,
    )


def _message(message: str, response: Response) -> AuthMessage:
    _no_store(response)
    return AuthMessage(message=message)


@router.post("/register", response_model=AuthMessage, status_code=status.HTTP_202_ACCEPTED)
async def register(payload: AuthCredentials, request: Request, response: Response) -> AuthMessage | JSONResponse:
    origin_error = _origin_failed(request)
    if origin_error is not None:
        return origin_error
    resources = _resources(request)
    if resources is None:
        return _message("registration_received", response)
    try:
        await resources.services.customer.register(payload.email, payload.password)
    except (InvalidEmailError, PasswordPolicyError) as rejection:
        # Miền email và chính sách mật khẩu là LUẬT CÔNG KHAI: khách biết được
        # chúng trước khi gõ, nên nói ra không lộ gì. Gộp chúng vào
        # `registration_unavailable` chỉ khiến người dùng @yahoo hoặc người đặt
        # mật khẩu ngắn nhận một màn "đã gửi yêu cầu" rồi chờ mãi một lá thư
        # không bao giờ tới — hỏng mà trông như xong là kiểu hỏng tệ nhất.
        return _error(rejection.code, status.HTTP_400_BAD_REQUEST)
    except AuthDomainError:
        # Còn lại là "email đã đăng ký". Ca này PHẢI trông y hệt lần đăng ký đầu:
        # phân biệt được nó là dựng sẵn một máy dò tài khoản. Đây là chỗ duy nhất
        # trong ba nhánh mà sự mơ hồ là tính năng, không phải thiếu sót.
        return _message("registration_received", response)
    return _message("registration_received", response)


@router.post("/login", response_model=AuthMessage)
async def login(payload: AuthCredentials, request: Request, response: Response) -> AuthMessage | JSONResponse:
    resources = _resources(request)
    if resources is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    services = resources.services
    try:
        session = await services.customer.login(payload.email, payload.password)
    except AbuseLimitExceededError:
        return _error("invalid_credentials", status.HTTP_429_TOO_MANY_REQUESTS, retry_after=RATE_LIMIT_RETRY_AFTER)
    if session is None:
        return _error("invalid_credentials", status.HTTP_401_UNAUTHORIZED)
    _set_session_cookies(response, session.access_token, session.refresh_token.reveal(), token_urlsafe(32))
    return _message("logged_in", response)


@router.post("/verify", response_model=AuthMessage)
async def verify(payload: VerificationRequest, request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not await _resources(request).services.customer.verify_post(payload.token):
        return _error("invalid_verification", status.HTTP_400_BAD_REQUEST)
    return _message("verified", response)


@router.post("/resend-verification", response_model=AuthMessage)
async def resend_verification(
    payload: EmailRequest, request: Request, response: Response
) -> AuthMessage | JSONResponse:
    if not _origin_matches(request):
        return _error("origin_forbidden", status.HTTP_403_FORBIDDEN)
    resources = _resources(request)
    if resources is None:
        return _message("verification_resend_received", response)
    try:
        await resources.services.customer.resend_verification(payload.email)
    except AbuseLimitExceededError:
        return _error(
            "verification_resend_received", status.HTTP_429_TOO_MANY_REQUESTS, retry_after=RATE_LIMIT_RETRY_AFTER
        )
    return _message("verification_resend_received", response)


@router.post("/refresh", response_model=AuthMessage)
async def refresh(request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    raw = _refresh(request)
    if raw is None:
        return _invalid_session(response)
    try:
        session = await _resources(request).services.customer.refresh(raw)
    except AuthDomainError:
        return _invalid_session(response)
    _set_session_cookies(response, session.access_token, session.refresh_token.reveal(), token_urlsafe(32))
    return _message("refreshed", response)


@router.post("/logout", response_model=AuthMessage)
async def logout(request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    raw = _refresh(request)
    if raw is not None:
        await _resources(request).services.customer.logout_current(raw)
    _clear_session_cookies(response)
    return _message("logged_out", response)


@router.post("/logout-all", response_model=AuthMessage)
async def logout_all(request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    access = _access(request)
    if access is None or not await _resources(request).services.customer.logout_all(access):
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    _clear_session_cookies(response)
    return _message("logged_out", response)


@router.get("/me", response_model=None)
async def me(request: Request, response: Response) -> dict[str, str] | JSONResponse:
    access = _access(request)
    user = None if access is None else await _resources(request).services.customer.me(access)
    if user is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    _no_store(response)
    return {"id": str(user.id), "email": str(user.email), "role": user.role.value, "state": user.state.value}


@router.get("/profile", response_model=None)
async def get_profile(request: Request, response: Response) -> ProfileResponse | JSONResponse:
    """Retrieve personal profile for customer or advisor."""
    access = _access(request)
    if access is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    result = await _resources(request).services.customer.get_profile(access)
    if result is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    user, profile = result
    _no_store(response)
    return ProfileResponse(
        id=str(user.id),
        email=str(user.email),
        role=user.role.value,
        full_name=profile.full_name if profile else None,
        phone_number=profile.phone_number if profile else None,
        address=profile.address if profile else None,
        showroom_name=profile.showroom_name if profile else None,
        avatar_url=profile.avatar_url if profile else None,
        vehicle_preference=profile.vehicle_preference if profile else None,
        budget_preference=profile.budget_preference if profile else None,
        seats_preference=profile.seats_preference if profile else None,
        home_charging=profile.home_charging if profile else None,
        title=profile.title if profile else None,
        bio=profile.bio if profile else None,
    )


@router.put("/profile", response_model=None)
async def update_profile(
    payload: UpdateProfileRequest, request: Request, response: Response
) -> ProfileResponse | JSONResponse:
    """Update personal profile for customer or advisor."""
    if not _csrf_valid(request):
        return _csrf_failed()
    access = _access(request)
    if access is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    profile = await _resources(request).services.customer.update_profile(
        access,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        address=payload.address,
        showroom_name=payload.showroom_name,
        avatar_url=payload.avatar_url,
        vehicle_preference=payload.vehicle_preference,
        budget_preference=payload.budget_preference,
        seats_preference=payload.seats_preference,
        home_charging=payload.home_charging,
        title=payload.title,
        bio=payload.bio,
    )
    if profile is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    user = await _resources(request).services.customer.me(access)
    _no_store(response)
    return ProfileResponse(
        id=str(user.id),
        email=str(user.email),
        role=user.role.value,
        full_name=profile.full_name,
        phone_number=profile.phone_number,
        address=profile.address,
        showroom_name=profile.showroom_name,
        avatar_url=profile.avatar_url,
        vehicle_preference=profile.vehicle_preference,
        budget_preference=profile.budget_preference,
        seats_preference=profile.seats_preference,
        home_charging=profile.home_charging,
        title=profile.title,
        bio=profile.bio,
    )


@router.post("/change-password", response_model=AuthMessage)
async def change_password(payload: PasswordRequest, request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    access = _access(request)
    identity = None if access is None else await _resources(request).services.customer.validate_access(access)
    if identity is None or not await _resources(request).services.recovery.change_password(
        identity[0], payload.password
    ):
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    _clear_session_cookies(response)
    return _message("password_changed", response)


@router.post("/forgot-password", response_model=AuthMessage)
async def forgot_password(payload: EmailRequest, request: Request, response: Response) -> AuthMessage | JSONResponse:
    origin_error = _origin_failed(request)
    if origin_error is not None:
        return origin_error
    await _resources(request).services.recovery.forgot_password(payload.email)
    return _message("password_recovery_received", response)


@router.post("/reset-password", response_model=AuthMessage)
async def reset_password(
    payload: ResetPasswordRequest, request: Request, response: Response
) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    if not await _resources(request).services.recovery.reset_password(payload.token, payload.password):
        return _error("invalid_reset", status.HTTP_400_BAD_REQUEST)
    _clear_session_cookies(response)
    return _message("password_reset", response)


@router.post("/staff", response_model=AuthMessage)
async def create_staff(payload: StaffCreateRequest, request: Request, response: Response) -> AuthMessage | JSONResponse:
    if not _csrf_valid(request):
        return _csrf_failed()
    access = _access(request)
    identity = None if access is None else await _resources(request).services.customer.validate_access(access)
    if identity is None:
        return _error("invalid_session", status.HTTP_401_UNAUTHORIZED)
    try:
        await _resources(request).services.staff.create_staff(identity[0], payload.email, Role(payload.role))
    except AuthDomainError:
        return _error("forbidden", status.HTTP_403_FORBIDDEN)
    return _message("staff_created", response)


# ---- Đăng nhập Google (OAuth 2.0 Authorization Code) ----

GOOGLE_AUTHORIZATION_URL: Final[str] = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_LOGIN_FAILED_LOCATION: Final[str] = "/login?error=google"


def _google_oauth_composition(request: Request):
    """Auth composition khi đăng nhập Google dùng được, ngược lại `None`.

    Thiếu cấu hình → 404 thay vì 500: một triển khai không khai đủ ba biến
    `GOOGLE_OAUTH_*` đơn giản là không có tính năng này.
    """
    auth = getattr(request.app.state, "auth", None)
    if auth is None or not auth.enabled or not getattr(auth, "google_oauth_enabled", False):
        return None
    return auth


def _delete_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/", secure=True, httponly=True, samesite=COOKIE_SAMESITE)


@router.get("/google/start", response_model=None)
async def google_start(request: Request) -> RedirectResponse | JSONResponse:
    auth = _google_oauth_composition(request)
    if auth is None:
        return _error("google_oauth_unavailable", status.HTTP_404_NOT_FOUND)
    state = token_urlsafe(32)
    query = urlencode(
        {
            "client_id": auth.google_oauth_client_id,
            "redirect_uri": auth.google_oauth_redirect_url,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{GOOGLE_AUTHORIZATION_URL}?{query}", status_code=status.HTTP_302_FOUND)
    _no_store(response)
    # HttpOnly vì chỉ server cần đọc lại state ở callback; TTL ngắn vì state
    # chỉ sống một vòng chuyển hướng.
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        max_age=OAUTH_STATE_TTL_SECONDS,
        secure=True,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return response


@router.get("/google/callback", response_model=None)
async def google_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse | JSONResponse:
    auth = _google_oauth_composition(request)
    if auth is None:
        return _error("google_oauth_unavailable", status.HTTP_404_NOT_FOUND)
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    # State lệch là dấu hiệu CSRF/replay, không phải "đăng nhập trượt": trả 400
    # tường minh thay vì lặng lẽ đưa về màn đăng nhập.
    if not expected_state or not state or not compare_digest(expected_state, state):
        failure = _error("oauth_state_mismatch", status.HTTP_400_BAD_REQUEST)
        _delete_oauth_state_cookie(failure)
        return failure
    session = None
    if code:
        session = await auth.resources.services.google.login_with_google(code)
    if session is None:
        # Gồm cả ca khách bấm Huỷ ở màn Google (Google gọi về không có `code`).
        response = RedirectResponse(GOOGLE_LOGIN_FAILED_LOCATION, status_code=status.HTTP_302_FOUND)
    else:
        # Phát phiên y hệt /auth/login thành công: access + refresh + CSRF.
        response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
        _set_session_cookies(response, session.access_token, session.refresh_token.reveal(), token_urlsafe(32))
    _no_store(response)
    _delete_oauth_state_cookie(response)
    return response


__all__ = ["router"]
