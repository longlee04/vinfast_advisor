"""Đăng nhập Google: đổi code lấy danh tính đã xác minh, tìm-hoặc-tạo user.

Gateway HTTP được fake toàn bộ — các bài này kiểm LOGIC tin cậy: aud phải là
client_id của mình, issuer phải là Google, email phải đã xác minh; rồi mới đến
chuyện tài khoản (tạo mới ACTIVE, đăng nhập lại, kích hoạt tài khoản đang chờ
xác minh, từ chối tài khoản bị khoá).
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from src.auth.application.google_oauth import GoogleOAuthService
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.values import (
    NormalizedEmail,
    PasswordHash,
    PlaintextPassword,
    TokenHash,
    UserId,
)

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
CLIENT_ID = "test-client.apps.googleusercontent.com"
EMAIL = "khach@gmail.com"


def google_claims(**overrides: str) -> dict[str, str]:
    base = {
        "aud": CLIENT_ID,
        "iss": "https://accounts.google.com",
        "email": EMAIL,
        "email_verified": "true",
    }
    base.update(overrides)
    return base


class FakeGateway:
    def __init__(
        self,
        token_response: dict[str, Any] | None,
        tokeninfo: dict[str, Any] | None,
    ) -> None:
        self.token_response = token_response
        self.tokeninfo = tokeninfo
        self.exchanged: list[str] = []

    async def exchange_code(self, code: str) -> dict[str, Any] | None:
        self.exchanged.append(code)
        return self.token_response

    async def fetch_tokeninfo(self, id_token: str) -> dict[str, Any] | None:
        return self.tokeninfo


class FakeHasher:
    def hash(self, password: PlaintextPassword) -> PasswordHash:
        return PasswordHash(f"hash:{password.reveal()}")

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        return self.hash(password) == password_hash

    def dummy_hash(self) -> PasswordHash:
        return PasswordHash("hash:dummy-password")

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        return False


class FakeTokenFactory:
    def __init__(self) -> None:
        self.counter = 0

    def new_secret(self) -> str:
        self.counter += 1
        return f"secret-{self.counter}"

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(f"token-hash:{secret}")


class FakeAccessTokens:
    def issue(self, *, user_id: UserId, session_id: str, expires_at: datetime) -> str:
        return f"access:{user_id}"

    def validate(self, token: str, *, now: datetime) -> tuple[UserId, str] | None:
        return None


class FakeStores:
    def __init__(self) -> None:
        self.users_by_email: dict[NormalizedEmail, User] = {}
        self.users_by_id: dict[UserId, User] = {}
        self.refresh_tokens_added: list[object] = []
        self.events: list[str] = []
        self.users = self
        self.refresh_tokens = self
        self.security_events = self

    async def add(self, value: object, *, now: datetime | None = None) -> None:
        if isinstance(value, User):
            self.users_by_email[value.email] = value
            self.users_by_id[value.id] = value
            return
        self.refresh_tokens_added.append(value)

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        return self.users_by_email.get(email)

    async def save(self, user: User, *, now: datetime) -> None:
        self.users_by_email[user.email] = user
        self.users_by_id[user.id] = user

    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None:
        self.events.append(event_type)


class FakeTransaction:
    def __init__(self, stores: FakeStores) -> None:
        self.stores = stores

    @asynccontextmanager
    async def transaction(self):
        yield self.stores


def build_service(stores: FakeStores, gateway: FakeGateway) -> GoogleOAuthService:
    return GoogleOAuthService(
        FakeTransaction(stores),
        FixedClock(NOW),
        FakeHasher(),
        FakeTokenFactory(),
        FakeAccessTokens(),
        gateway,
        client_id=CLIENT_ID,
    )


def existing_user(state: AccountState) -> User:
    return User(
        id=UserId("user-1"),
        email=NormalizedEmail(EMAIL),
        role=Role.CUSTOMER,
        state=state,
        password_hash=PasswordHash("hash:old-password"),
        created_at=NOW,
    )


def gateway_returning(claims: dict[str, str] | None) -> FakeGateway:
    return FakeGateway(token_response={"id_token": "fake-id-token"}, tokeninfo=claims)


@pytest.mark.asyncio
async def test_new_google_user_is_created_active_and_logged_in() -> None:
    stores = FakeStores()
    session = await build_service(stores, gateway_returning(google_claims())).login_with_google("code-1")

    assert session is not None
    created = stores.users_by_email[NormalizedEmail(EMAIL)]
    assert created.state is AccountState.ACTIVE
    assert created.role is Role.CUSTOMER
    assert session.user_id == created.id
    assert len(stores.refresh_tokens_added) == 1
    # Mật khẩu là hash của một bí mật ngẫu nhiên, không phải chuỗi rỗng hay hằng.
    assert created.password_hash != "hash:"


@pytest.mark.asyncio
async def test_existing_user_logs_in_without_a_new_account() -> None:
    stores = FakeStores()
    user = existing_user(AccountState.ACTIVE)
    stores.users_by_email[user.email] = user
    stores.users_by_id[user.id] = user

    session = await build_service(stores, gateway_returning(google_claims())).login_with_google("code-2")

    assert session is not None
    assert session.user_id == user.id
    assert len(stores.users_by_email) == 1
    assert stores.users_by_email[user.email].password_hash == user.password_hash


@pytest.mark.asyncio
async def test_pending_user_becomes_active_after_google_verified_email() -> None:
    """Google xác nhận hộp thư thuộc về người này — đúng điều bước verify email
    đòi hỏi — nên tài khoản đang chờ xác minh được kích hoạt và đăng nhập luôn."""
    stores = FakeStores()
    user = existing_user(AccountState.PENDING_VERIFICATION)
    stores.users_by_email[user.email] = user
    stores.users_by_id[user.id] = user

    session = await build_service(stores, gateway_returning(google_claims())).login_with_google("code-3")

    assert session is not None
    assert stores.users_by_email[user.email].state is AccountState.ACTIVE


@pytest.mark.asyncio
async def test_disabled_user_is_refused() -> None:
    stores = FakeStores()
    user = existing_user(AccountState.DISABLED)
    stores.users_by_email[user.email] = user
    stores.users_by_id[user.id] = user

    session = await build_service(stores, gateway_returning(google_claims())).login_with_google("code-4")

    assert session is None
    assert stores.refresh_tokens_added == []


@pytest.mark.asyncio
async def test_aud_for_another_client_is_refused() -> None:
    stores = FakeStores()
    gateway = gateway_returning(google_claims(aud="ke-khac.apps.googleusercontent.com"))

    assert await build_service(stores, gateway).login_with_google("code-5") is None
    assert stores.users_by_email == {}


@pytest.mark.asyncio
async def test_unverified_email_is_refused() -> None:
    stores = FakeStores()
    gateway = gateway_returning(google_claims(email_verified="false"))

    assert await build_service(stores, gateway).login_with_google("code-6") is None
    assert stores.users_by_email == {}


@pytest.mark.asyncio
async def test_foreign_issuer_is_refused() -> None:
    stores = FakeStores()
    gateway = gateway_returning(google_claims(iss="https://evil.example.com"))

    assert await build_service(stores, gateway).login_with_google("code-7") is None
    assert stores.users_by_email == {}


@pytest.mark.asyncio
async def test_failed_code_exchange_is_refused() -> None:
    stores = FakeStores()
    gateway = FakeGateway(token_response=None, tokeninfo=google_claims())

    assert await build_service(stores, gateway).login_with_google("code-8") is None


@pytest.mark.asyncio
async def test_token_response_without_id_token_is_refused() -> None:
    stores = FakeStores()
    gateway = FakeGateway(token_response={"access_token": "xx"}, tokeninfo=google_claims())

    assert await build_service(stores, gateway).login_with_google("code-9") is None


@pytest.mark.asyncio
async def test_unusable_tokeninfo_is_refused() -> None:
    stores = FakeStores()
    gateway = FakeGateway(token_response={"id_token": "fake"}, tokeninfo=None)

    assert await build_service(stores, gateway).login_with_google("code-10") is None
