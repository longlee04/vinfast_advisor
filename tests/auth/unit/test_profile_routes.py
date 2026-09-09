"""Focused HTTP tests for profile retrieval and update endpoints."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.accounts import AccountState, User, UserProfile
from src.auth.domain.authorization import Role
from src.auth.domain.values import NormalizedEmail, PasswordHash, UserId
from src.auth.presentation.routes import router

NOW = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)


class FakeCustomerService:
    def __init__(self) -> None:
        self.user = User(
            id=UserId("customer-123"),
            email=NormalizedEmail("test@gmail.com"),
            role=Role.CUSTOMER,
            state=AccountState.ACTIVE,
            password_hash=PasswordHash("hashed"),
            created_at=NOW,
        )
        self.profile = UserProfile(
            user_id=UserId("customer-123"),
            full_name="Nguyễn Văn A",
            phone_number="0912345678",
            address="Hà Nội",
        )

    async def get_profile(self, access_token: str):
        if access_token == "valid-token":
            return self.user, self.profile
        return None

    async def update_profile(self, access_token: str, **kwargs):
        if access_token == "valid-token":
            self.profile = UserProfile(
                user_id=self.user.id,
                full_name=kwargs.get("full_name"),
                phone_number=kwargs.get("phone_number"),
                address=kwargs.get("address"),
                showroom_name=kwargs.get("showroom_name"),
                avatar_url=kwargs.get("avatar_url"),
                vehicle_preference=kwargs.get("vehicle_preference"),
                budget_preference=kwargs.get("budget_preference"),
                seats_preference=kwargs.get("seats_preference"),
                home_charging=kwargs.get("home_charging"),
                title=kwargs.get("title"),
                bio=kwargs.get("bio"),
            )
            return self.profile
        return None

    async def me(self, access_token: str):
        if access_token == "valid-token":
            return self.user
        return None


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.state.auth = SimpleNamespace(
        enabled=True,
        resources=SimpleNamespace(
            services=SimpleNamespace(
                customer=FakeCustomerService(),
            )
        ),
    )
    application.include_router(router)
    return application


@pytest.mark.asyncio
async def test_get_profile_authenticated(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", cookies={"__Host-p150_access": "valid-token"}
    ) as client:
        response = await client.get("/auth/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@gmail.com"
        assert data["full_name"] == "Nguyễn Văn A"
        assert data["phone_number"] == "0912345678"


@pytest.mark.asyncio
async def test_get_profile_unauthenticated(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/profile")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_authenticated(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={
            "__Host-p150_access": "valid-token",
            "__Host-p150_csrf": "csrf-test-token",
        },
    ) as client:
        response = await client.put(
            "/auth/profile",
            headers={"X-CSRF-Token": "csrf-test-token"},
            json={
                "full_name": "Lê Văn Cập Nhật",
                "phone_number": "0988776655",
                "address": "TP Hồ Chí Minh",
                "vehicle_preference": "car",
                "budget_preference": "1 tỷ",
                "seats_preference": "7 chỗ",
                "home_charging": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Lê Văn Cập Nhật"
        assert data["phone_number"] == "0988776655"
        assert data["address"] == "TP Hồ Chí Minh"
        assert data["vehicle_preference"] == "car"
        assert data["budget_preference"] == "1 tỷ"
        assert data["seats_preference"] == "7 chỗ"
        assert data["home_charging"] is True
