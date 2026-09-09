"""Route-level contract tests for administrative user management."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

import src.auth.presentation.admin_routes as admin_routes
from src.auth.application.contracts import UserPage, UserSummary
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.errors import AuthorizationError
from src.auth.domain.values import NormalizedEmail, PasswordHash, UserId
from src.auth.presentation.schemas import AuthMessage, RoleRequest, UserPageResponse

NOW = datetime(2026, 8, 8, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RecordingStaff:
    """Fake staff service that records route delegation."""

    calls: list[
        tuple[
            str,
            tuple[UserId | Role, ...],
            dict[str, UserId | Role | AccountState | str | int | None],
        ]
    ] = field(default_factory=list)
    actor_roles: Mapping[UserId, Role] = field(
        default_factory=lambda: {
            UserId("admin"): Role.ADMIN,
            UserId("actor-from-identity"): Role.ADMIN,
            UserId("advisor-from-identity"): Role.ADVISOR,
            UserId("customer-from-identity"): Role.CUSTOMER,
        }
    )
    page: UserPage = field(
        default_factory=lambda: UserPage(
            items=(
                UserSummary(
                    id=UserId("target"),
                    email=NormalizedEmail.parse("target@example.com"),
                    role=Role.ADVISOR,
                    state=AccountState.ACTIVE,
                    created_at=NOW,
                    last_activity_at=None,
                ),
            ),
            total=1,
            page=2,
            page_size=10,
        )
    )

    async def list_users(
        self,
        actor_id: UserId,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> UserPage:
        self.calls.append(("list_users", (actor_id,), kwargs))
        if self.actor_roles.get(actor_id) is not Role.ADMIN:
            raise AuthorizationError("non-admin actor may not list users")
        return self.page

    async def change_role(
        self,
        *args: UserId | Role,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> User:
        self.calls.append(("change_role", args, kwargs))
        return make_user(role=Role.ADMIN)

    async def disable_user(
        self,
        *args: UserId | Role,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> User:
        self.calls.append(("disable_user", args, kwargs))
        return make_user(state=AccountState.DISABLED)

    async def enable_user(
        self,
        *args: UserId | Role,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> User:
        self.calls.append(("enable_user", args, kwargs))
        return make_user(state=AccountState.ACTIVE)

    async def activate_user(
        self,
        *args: UserId | Role,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> User:
        self.calls.append(("activate_user", args, kwargs))
        return make_user(state=AccountState.ACTIVE)


def make_user(*, role: Role = Role.ADMIN, state: AccountState = AccountState.ACTIVE) -> User:
    """Build an authenticated actor for route-level tests."""
    return User(
        id=UserId("admin"),
        email=NormalizedEmail.parse("admin@example.com"),
        role=role,
        state=state,
        password_hash=PasswordHash("hash:admin"),
        created_at=NOW,
    )


def make_request(*, csrf: bool = True) -> Request:
    """Build a minimal request with the route's CSRF inputs."""
    headers = [(b"x-csrf-token", b"csrf"), (b"cookie", b"__Host-p150_csrf=csrf")] if csrf else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/admin/users/target",
            "headers": headers,
            "query_string": b"",
            "scheme": "https",
            "server": ("test", 443),
            "client": ("test", 1),
            "root_path": "",
            "app": FastAPI(),
        }
    )


def install_fake_resources(monkeypatch: pytest.MonkeyPatch, staff: RecordingStaff) -> None:
    """Wire route helpers to deterministic application fakes."""
    resources = SimpleNamespace(services=SimpleNamespace(staff=staff))
    monkeypatch.setattr(admin_routes, "_resources", lambda request: resources)

    async def identity(request: Request) -> tuple[UserId, User]:
        return _identity()

    monkeypatch.setattr(admin_routes, "_identity", identity)
    monkeypatch.setattr(admin_routes, "_csrf_valid", lambda request: True)


def _identity() -> tuple[UserId, User]:
    return UserId("admin"), make_user()


@pytest.mark.asyncio
async def test_admin_listing_delegates_filters_and_maps_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given an admin identity, when listing users, then filters and page map exactly."""
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    actor_id = UserId("actor-from-identity")

    async def identity(request: Request) -> tuple[UserId, User]:
        return actor_id, make_user()

    monkeypatch.setattr(admin_routes, "_identity", identity)
    response = await admin_routes.list_users(
        make_request(),
        Response(),
        role="advisor",
        state="active",
        q="target",
        page=2,
        page_size=10,
    )

    assert isinstance(response, UserPageResponse)
    assert response.items[0].email == "target@example.com"
    assert staff.calls == [
        (
            "list_users",
            (actor_id,),
            {
                "role": Role.ADVISOR,
                "state": AccountState.ACTIVE,
                "email_query": "target",
                "page": 2,
                "page_size": 10,
            },
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "payload", "message"),
    [
        ("change_user_role", RoleRequest(role="admin"), "role_changed"),
        ("disable_user", None, "user_disabled"),
        ("enable_user", None, "user_enabled"),
    ],
)
async def test_admin_mutations_delegate_and_return_no_store_message(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    payload: RoleRequest | None,
    message: str,
) -> None:
    """Given valid CSRF and admin session, when mutating, then service is called once."""
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    endpoint: Callable[..., AuthMessage | JSONResponse] = getattr(admin_routes, method)
    http_response = Response()
    response = (
        await endpoint("target", payload, make_request(), http_response)
        if payload is not None
        else await endpoint("target", make_request(), http_response)
    )

    assert isinstance(response, AuthMessage)
    assert http_response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in http_response.headers
    assert response.message == message
    assert len(staff.calls) == 1
    expected_call = "change_role" if method == "change_user_role" else method
    assert staff.calls[0][0] == expected_call


@pytest.mark.asyncio
async def test_admin_mutation_rejects_csrf_before_session_or_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    monkeypatch.setattr(admin_routes, "_csrf_valid", lambda request: False)
    response = await admin_routes.disable_user("target", make_request(csrf=False), Response())

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "csrf_failed"}
    assert response.headers["cache-control"] == "no-store"
    assert staff.calls == []


@pytest.mark.asyncio
async def test_admin_listing_rejects_unknown_filters_without_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given an invalid filter, when listing, then response is bounded and not cacheable."""
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    response = await admin_routes.list_users(make_request(), Response(), role="unknown")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert json.loads(response.body) == {"error": "invalid_filter"}
    assert response.headers["cache-control"] == "no-store"
    assert staff.calls == []


@pytest.mark.asyncio
async def test_admin_listing_maps_non_admin_application_rejection_to_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    actor_id = UserId("advisor-from-identity")

    async def identity(request: Request) -> tuple[UserId, User]:
        return actor_id, make_user(role=Role.ADVISOR)

    monkeypatch.setattr(admin_routes, "_identity", identity)
    response = await admin_routes.list_users(
        make_request(), Response(), role=None, state=None, q=None, page=1, page_size=20
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "forbidden"}
    assert response.headers["cache-control"] == "no-store"
    assert staff.calls[0][1] == (actor_id,)


@pytest.mark.asyncio
async def test_admin_mutation_maps_authorization_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given a denied service action, when disabling, then HTTP exposes only forbidden."""
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)

    async def denied(
        self: RecordingStaff,
        *args: UserId | Role,
        **kwargs: UserId | Role | AccountState | str | int | None,
    ) -> User:
        raise AuthorizationError("internal target detail")

    monkeypatch.setattr(RecordingStaff, "disable_user", denied)
    response = await admin_routes.disable_user("target", make_request(), Response())

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "internal target detail" not in response.body.decode()


@pytest.mark.asyncio
async def test_admin_activate_user_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin can activate a user successfully."""
    staff = RecordingStaff()
    install_fake_resources(monkeypatch, staff)
    actor_id = UserId("admin")

    async def identity(request: Request) -> tuple[UserId, User]:
        return actor_id, make_user(role=Role.ADMIN)

    monkeypatch.setattr(admin_routes, "_identity", identity)
    response = await admin_routes.activate_user("target-user-123", make_request(), Response())

    assert isinstance(response, AuthMessage)
    assert response.message == "user_activated"
    assert staff.calls[0] == ("activate_user", (actor_id, UserId("target-user-123")), {})
