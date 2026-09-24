import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.agents.api.analytics_routes import analytics_operations
from src.agents.api.booking_routes import booking_operations
from src.agents.api.bottleneck_signal_routes import bottleneck_signal_operations
from src.agents.api.customer_360_routes import (
    customer_360_operations,
    customer_360_read_operations,
    customer_ownership_operations,
    opportunity_offer_operations,
)
from src.agents.api.customer_routes import turn_event_broker
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.history_routes import history_operations
from src.agents.api.notice_routes import notice_operations
from src.agents.api.review_routes import review_operations
from src.agents.api.sales_opportunity_routes import sales_opportunity_service
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.api.turn_trace_routes import turn_trace_operations
from src.agents.api.ws_routes import router as agents_ws_router
from src.agents.composition import AgentComposition
from src.api.router import api_router
from src.auth.application.ports import AbuseLimitExceededError
from src.auth.composition import AuthComposition, AuthStartupError
from src.auth.domain.accounts import User
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.values import UserId
from src.auth.presentation.routes import _access, _resources
from src.auth.settings import get_auth_settings
from src.config import get_settings
from src.document.composition import DocumentComposition
from src.document.infrastructure.settings import get_document_settings
from src.document.presentation.dependencies import CurrentPrincipal as DocumentCurrentPrincipal
from src.document.presentation.dependencies import get_current_principal as get_document_current_principal
from src.images.composition import ImageComposition
from src.images.presentation.dependencies import get_current_principal
from src.locations.composition import LocationsComposition
from src.locations.infrastructure.settings import LocationsSettings
from src.products.composition import ProductComposition
from src.products.presentation.promotion_admin_routes import router as promotion_admin_router
from src.products.presentation.routes import router as product_router

AUTH_EMAIL_SENDER_OVERRIDE = None


async def _auth_identity(request: Request) -> tuple[UserId, str] | None:
    """Return authenticated Auth identity `(user_id, session_id)`, or None."""
    resources = _resources(request)
    access = _access(request)
    if resources is None or access is None:
        return None
    user = await resources.services.customer.me(access)
    if user is None:
        return None
    return user.id, user


async def _auth_user(request: Request) -> User | None:
    """Return the authenticated Auth user, or None when the session is unusable."""
    resources = _resources(request)
    access = _access(request)
    if resources is None or access is None:
        return None
    return await resources.services.customer.me(access)


async def _staff_identity_from_auth(request: Request) -> StaffIdentity:
    """Return staff identity through Auth session validation.

    `validate_access` chỉ trả `(user_id, session_id)`, không mang vai trò, nên
    vai phải lấy từ hồ sơ người dùng — đọc `.role` trên phần tử thứ hai sẽ vỡ.
    """
    identity = await _auth_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    user_id, _session_id = identity
    user = await _auth_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    email = str(user.email) if getattr(user, "email", None) is not None else None
    return StaffIdentity(staff_id=str(user_id), role=user.role, email=email)


async def _document_principal_from_auth(request: Request) -> DocumentCurrentPrincipal:
    """Return CurrentPrincipal for Document and Image routes through Auth session validation."""
    composition = getattr(request.app.state, "document", None)
    if (
        composition is None
        or not getattr(composition, "enabled", True)
        or getattr(composition, "resources", None) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service unavailable",
        )
    identity = await _auth_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    user_id, user = identity
    return DocumentCurrentPrincipal(actor_id=str(user_id), role=user.role)


async def _customer_id_from_auth(request: Request) -> str | None:
    """Return authenticated customer identifier, or None when no session exists.

    Trả `None` thay vì raise: seam này được giải trước khi FastAPI validate body,
    raise ở đây sẽ che mất 422 của request có body sai.
    """
    identity = await _auth_identity(request)
    if identity is None:
        return None
    user_id, _user = identity
    return str(user_id)


def _wire_agent_operations(app: FastAPI, agent: AgentComposition) -> None:
    """Override operations route seams with database-backed Agent operations."""
    # Danh tính khách không phụ thuộc database của agent: khi agent chưa có DB,
    # route khách vẫn phải trả 503 vì thiếu service, không phải 401 vì thiếu seam.
    app.dependency_overrides.setdefault(get_current_customer_id, _customer_id_from_auth)
    app.dependency_overrides.setdefault(current_staff, _staff_identity_from_auth)
    app.dependency_overrides.setdefault(get_current_principal, _document_principal_from_auth)
    app.dependency_overrides.setdefault(get_document_current_principal, _document_principal_from_auth)
    operations = agent.operations
    if operations is None:
        return
    app.dependency_overrides[review_operations] = lambda: operations.review
    app.dependency_overrides[bottleneck_signal_operations] = lambda: operations.bottleneck_signals
    if agent.broker is not None:
        app.dependency_overrides[turn_event_broker] = lambda: agent.broker
    app.dependency_overrides[booking_operations] = lambda: operations.booking
    app.dependency_overrides[history_operations] = lambda: operations.history
    app.dependency_overrides[notice_operations] = lambda: operations.notices
    app.dependency_overrides[analytics_operations] = lambda: operations.analytics
    app.dependency_overrides[turn_trace_operations] = lambda: operations.turn_traces
    app.dependency_overrides[sales_opportunity_service] = lambda: operations.sales_opportunity
    if operations.customer360 is not None and operations.customer360_read is not None:
        app.dependency_overrides[customer_360_operations] = lambda: operations.customer360
        app.dependency_overrides[customer_360_read_operations] = lambda: operations.customer360_read
    if operations.opportunity_offers is not None:
        app.dependency_overrides[opportunity_offer_operations] = lambda: operations.opportunity_offers
    if operations.customer_ownership is not None:
        app.dependency_overrides[customer_ownership_operations] = lambda: operations.customer_ownership
    app.dependency_overrides[current_staff] = _staff_identity_from_auth
    app.dependency_overrides[get_current_principal] = _document_principal_from_auth
    app.dependency_overrides[get_document_current_principal] = _document_principal_from_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")

    # Auth owns its own resources. When AUTH_ENABLED=false this is a no-op, so
    # legacy-only deployments start exactly as before.
    auth = AuthComposition(get_auth_settings(), email_sender=AUTH_EMAIL_SENDER_OVERRIDE)
    document = getattr(app.state, "document", None) or DocumentComposition(get_document_settings())
    image = getattr(app.state, "image", None) or ImageComposition(get_document_settings())
    locations = LocationsComposition(LocationsSettings.from_environment())
    product_db_url = os.environ.get(
        "PRODUCT_DATABASE_URL",
        os.environ.get("AUTH_DATABASE_URL", ""),
    )
    product = ProductComposition(product_db_url) if product_db_url else None
    agent = AgentComposition()
    app.state.auth = auth
    app.state.document = document
    app.state.image = image
    app.state.locations = locations
    app.state.product = product
    app.state.agent = agent
    try:
        await auth.start()
        await document.start()
        await image.start()
        await locations.start()
        await agent.start()
        _wire_agent_operations(app, agent)
        if product is not None:
            await product.start()
            app.state.product = product.resources
        yield
    finally:
        if product is not None:
            await product.shutdown()
        await agent.shutdown()
        await locations.shutdown()
        await image.shutdown()
        await document.shutdown()
        await auth.shutdown()
        print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

# Document and Image authentication must not depend on Agent operations being
# enabled. Their routes are registered before startup and use these stable seams.
app.dependency_overrides[get_current_principal] = _document_principal_from_auth
app.dependency_overrides[get_document_current_principal] = _document_principal_from_auth

settings = get_settings()


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_auth_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    # `Cache-Control` nằm trong danh sách vì frontend gửi `no-store` trên mọi
    # lời gọi auth; thiếu nó thì preflight trả 400 và trình duyệt chặn toàn bộ
    # luồng đăng nhập, dù chính request đó gọi bằng curl vẫn chạy.
    allow_headers=["Content-Type", "Origin", "X-CSRF-Token", "Cache-Control"],
)


AUTH_VALIDATION_REDACTED_PREFIXES = (
    "/api/v1/auth/staff/",
    "/api/v1/auth/admin/",
)


@app.exception_handler(RequestValidationError)
async def auth_validation_error(request: Request, error: RequestValidationError):
    if request.url.path.startswith(AUTH_VALIDATION_REDACTED_PREFIXES):
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request"},
            headers={"Cache-Control": "no-store"},
        )
    response = await request_validation_exception_handler(request, error)
    if request.url.path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AbuseLimitExceededError)
async def abuse_limit_error(request: Request, error: AbuseLimitExceededError) -> JSONResponse:
    return JSONResponse(
        status_code=429, content={"error": "rate_limited"}, headers={"Retry-After": "60", "Cache-Control": "no-store"}
    )


@app.exception_handler(AuthDomainError)
async def auth_domain_error(request: Request, error: AuthDomainError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": "invalid_request"}, headers={"Cache-Control": "no-store"})


_logger = logging.getLogger(__name__)


@app.exception_handler(AuthStartupError)
async def auth_startup_error(request: Request, error: AuthStartupError) -> JSONResponse:
    _logger.exception("[503] AuthStartupError on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"error": "auth_unavailable"}, headers={"Cache-Control": "no-store"})


@app.exception_handler(SQLAlchemyError)
async def auth_database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
    _logger.exception("[503] SQLAlchemyError on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"error": "auth_unavailable"}, headers={"Cache-Control": "no-store"})


app.include_router(api_router)
app.include_router(agents_ws_router)
app.include_router(product_router, prefix="/api/v1")
app.include_router(promotion_admin_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
