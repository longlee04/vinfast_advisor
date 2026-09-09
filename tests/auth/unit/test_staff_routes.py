"""Focused HTTP contract tests for staff self-service routes."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.application.ports import AbuseLimitExceededError
from src.auth.application.session_lifecycle import AuthSession
from src.auth.domain.errors import AccountStateError, TemporaryPasswordRequiredError
from src.auth.domain.values import FamilyId, PlaintextToken, SessionId, UserId
from src.auth.presentation.staff_routes import router

NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)


def session() -> AuthSession:
    return AuthSession(
        access_token="access-token",
        refresh_token=PlaintextToken("refresh-token"),
        user_id=UserId("staff"),
        session_id=SessionId("session"),
        family_id=FamilyId("family"),
        family_expires_at=NOW,
    )


class RouteStaff:
    def __init__(self) -> None:
        self.login_result: AuthSession | None = session()
        self.login_error: AbuseLimitExceededError | TemporaryPasswordRequiredError | None = None
        self.identity: UserId | None = UserId("staff")
        self.identify_error: AbuseLimitExceededError | None = None
        self.completion_error: AccountStateError | None = None
        self.login_after_setup_calls = 0

    async def login(self, email: str, password: str) -> AuthSession | None:
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    async def identify_for_password_setup(self, email: str, password: str) -> UserId | None:
        if self.identify_error is not None:
            raise self.identify_error
        return self.identity

    async def complete_temporary_password_change(self, user_id: UserId, password: str) -> None:
        if self.completion_error is not None:
            raise self.completion_error

    async def login_after_password_setup(self, user_id: UserId) -> AuthSession | None:
        self.login_after_setup_calls += 1
        return self.login_result


@pytest.fixture
def route_app() -> tuple[FastAPI, RouteStaff]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    staff = RouteStaff()
    app.state.auth = SimpleNamespace(
        enabled=True,
        resources=SimpleNamespace(services=SimpleNamespace(staff=staff)),
    )
    return app, staff


async def request(
    app: FastAPI, path: str, payload: dict[str, str]
) -> tuple[int, dict[str, str], dict[str, str], list[str]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        response = await client.post(path, json=payload)
    return (
        response.status_code,
        response.json(),
        dict(response.headers),
        response.headers.get_list("set-cookie"),
    )


@pytest.mark.asyncio
async def test_staff_login_success_sets_three_session_cookies(route_app: tuple[FastAPI, RouteStaff]) -> None:
    app, _ = route_app

    status_code, body, _headers, cookies = await request(
        app,
        "/api/v1/auth/staff/login",
        {"email": "staff@example.com", "password": "Strong-password-123"},
    )

    assert status_code == 200
    assert body == {"message": "logged_in"}
    assert len(cookies) == 3


@pytest.mark.asyncio
async def test_staff_login_temporary_password_returns_no_store_conflict_without_cookies(
    route_app: tuple[FastAPI, RouteStaff],
) -> None:
    app, staff = route_app
    staff.login_error = TemporaryPasswordRequiredError("change required")

    status_code, body, _headers, cookies = await request(
        app,
        "/api/v1/auth/staff/login",
        {"email": "staff@example.com", "password": "Strong-password-123"},
    )

    assert status_code == 409
    assert body == {"error": "temporary_password_required"}
    assert _headers["cache-control"] == "no-store"
    assert cookies == []


@pytest.mark.asyncio
async def test_staff_login_rate_limit_returns_429_without_cookies(route_app: tuple[FastAPI, RouteStaff]) -> None:
    app, staff = route_app
    staff.login_error = AbuseLimitExceededError()

    status_code, body, headers, cookies = await request(
        app,
        "/api/v1/auth/staff/login",
        {"email": "staff@example.com", "password": "Strong-password-123"},
    )

    assert status_code == 429
    assert body == {"error": "invalid_credentials"}
    assert headers["cache-control"] == "no-store"
    assert headers["retry-after"] == "60"
    assert cookies == []


@pytest.mark.asyncio
async def test_complete_password_issues_session_without_second_limiter_call(
    route_app: tuple[FastAPI, RouteStaff],
) -> None:
    app, staff = route_app

    status_code, body, _headers, cookies = await request(
        app,
        "/api/v1/auth/staff/complete-password",
        {
            "email": "staff@example.com",
            "temporary_password": "Temporary-password-123",
            "new_password": "New-strong-password-123",
        },
    )

    assert status_code == 200
    assert body == {"message": "password_set"}
    assert len(cookies) == 3
    assert staff.login_after_setup_calls == 1


@pytest.mark.asyncio
async def test_complete_password_weak_password_returns_422_no_store_without_cookies(
    route_app: tuple[FastAPI, RouteStaff],
) -> None:
    app, staff = route_app
    staff.completion_error = AccountStateError("weak")

    status_code, body, _headers, cookies = await request(
        app,
        "/api/v1/auth/staff/complete-password",
        {
            "email": "staff@example.com",
            "temporary_password": "Temporary-password-123",
            "new_password": "weak",
        },
    )

    assert status_code == 422
    assert body == {"error": "weak_password"}
    assert _headers["cache-control"] == "no-store"
    assert cookies == []


@pytest.mark.asyncio
async def test_staff_routes_reject_extra_fields_with_no_store(route_app: tuple[FastAPI, RouteStaff]) -> None:
    app, _ = route_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        response = await client.post(
            "/api/v1/auth/staff/complete-password",
            json={
                "email": "staff@example.com",
                "temporary_password": "Temporary-password-123",
                "new_password": "New-strong-password-123",
                "extra": "refused",
            },
        )

    assert response.status_code == 422
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.asyncio
async def test_disabled_auth_closes_staff_routes() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.auth = SimpleNamespace(enabled=False)

    status_code, body, _headers, cookies = await request(
        app,
        "/api/v1/auth/staff/login",
        {"email": "staff@example.com", "password": "Strong-password-123"},
    )

    assert status_code == 401
    assert body == {"error": "invalid_credentials"}
    assert cookies == []
