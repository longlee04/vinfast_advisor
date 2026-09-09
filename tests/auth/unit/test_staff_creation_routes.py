"""DB-independent route contracts for staff account creation."""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient

import src.auth.presentation.routes as auth_routes
from src.auth.domain.authorization import Role
from src.auth.domain.errors import AuthorizationError
from src.auth.domain.values import UserId
from src.auth.presentation.schemas import AuthMessage, StaffCreateRequest


class RecordingCustomer:
    def __init__(self, identity: tuple[UserId, str] | None) -> None:
        self.identity = identity
        self.calls = 0

    async def validate_access(self, token: str) -> tuple[UserId, str] | None:
        self.calls += 1
        return self.identity


class RecordingStaff:
    def __init__(self) -> None:
        self.calls: list[tuple[UserId, str, str]] = []
        self.error: AuthorizationError | None = None

    async def create_staff(self, actor_id: UserId, email: str, role: Role) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((actor_id, email, str(role)))


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/staff",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("test", 443),
            "client": ("test", 1),
            "root_path": "",
            "app": SimpleNamespace(),
        }
    )


def install_resources(
    monkeypatch: pytest.MonkeyPatch,
    customer: RecordingCustomer,
    staff: RecordingStaff,
) -> None:
    monkeypatch.setattr(
        auth_routes,
        "_resources",
        lambda _request: SimpleNamespace(services=SimpleNamespace(customer=customer, staff=staff)),
    )
    monkeypatch.setattr(auth_routes, "_access", lambda _request: "access-token")
    monkeypatch.setattr(auth_routes, "_csrf_valid", lambda _request: True)


@pytest.mark.asyncio
async def test_staff_creation_rejects_missing_csrf_before_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = RecordingCustomer((UserId("admin"), "admin"))
    staff = RecordingStaff()
    install_resources(monkeypatch, customer, staff)
    monkeypatch.setattr(auth_routes, "_csrf_valid", lambda _request: False)

    result = await auth_routes.create_staff(
        StaffCreateRequest(email="advisor@example.com", role="advisor"), request(), Response()
    )

    assert result.status_code == 403
    assert json.loads(result.body) == {"error": "csrf_failed"}
    assert customer.calls == 0
    assert staff.calls == []


@pytest.mark.asyncio
async def test_staff_creation_rejects_invalid_session_without_calling_staff_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = RecordingCustomer(None)
    staff = RecordingStaff()
    install_resources(monkeypatch, customer, staff)

    result = await auth_routes.create_staff(
        StaffCreateRequest(email="advisor@example.com", role="advisor"), request(), Response()
    )

    assert result.status_code == 401
    assert json.loads(result.body) == {"error": "invalid_session"}
    assert staff.calls == []


@pytest.mark.asyncio
async def test_staff_creation_maps_non_admin_rejection_to_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = RecordingCustomer((UserId("advisor"), "advisor"))
    staff = RecordingStaff()
    staff.error = AuthorizationError("role advisor may not create staff")
    install_resources(monkeypatch, customer, staff)

    result = await auth_routes.create_staff(
        StaffCreateRequest(email="advisor@example.com", role="admin"), request(), Response()
    )

    assert result.status_code == 403
    assert json.loads(result.body) == {"error": "forbidden"}
    assert "role advisor" not in result.body.decode()


@pytest.mark.asyncio
async def test_staff_creation_returns_stable_message_and_delegates_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = RecordingCustomer((UserId("admin"), "admin"))
    staff = RecordingStaff()
    install_resources(monkeypatch, customer, staff)
    response = Response()

    result = await auth_routes.create_staff(
        StaffCreateRequest(email="advisor@example.com", role="advisor"), request(), response
    )

    assert isinstance(result, AuthMessage)
    assert result.message == "staff_created"
    assert response.headers["cache-control"] == "no-store"
    assert staff.calls == [(UserId("admin"), "advisor@example.com", "advisor")]


def validation_app(staff: RecordingStaff) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/v1")
    app.state.auth = SimpleNamespace(
        enabled=True,
        resources=SimpleNamespace(
            services=SimpleNamespace(
                customer=RecordingCustomer((UserId("admin"), "admin")),
                staff=staff,
            )
        ),
    )
    return app


@pytest.mark.asyncio
async def test_staff_creation_customer_role_is_rejected_before_service_call() -> None:
    staff = RecordingStaff()
    app = validation_app(staff)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test.example") as client:
        response = await client.post(
            "/api/v1/auth/staff",
            json={"email": "customer@example.com", "role": "customer"},
        )

    assert response.status_code == 422
    assert staff.calls == []


@pytest.mark.asyncio
async def test_staff_creation_password_field_is_rejected_before_service_call() -> None:
    staff = RecordingStaff()
    app = validation_app(staff)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test.example") as client:
        response = await client.post(
            "/api/v1/auth/staff",
            json={
                "email": "advisor@example.com",
                "role": "advisor",
                "password": "NeverPrint!123",
            },
        )

    assert response.status_code == 422
    assert staff.calls == []
