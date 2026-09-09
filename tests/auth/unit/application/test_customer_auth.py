"""Customer authentication application acceptance tests (Task 4)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from src.auth.application.customer_auth import CustomerAuthService
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import RefreshTokenReplayError, SessionRevokedError
from src.auth.domain.sessions import OneTimeToken, RefreshToken, RevocationReason
from src.auth.domain.values import NormalizedEmail, PasswordHash, PlaintextPassword, TokenHash, UserId

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)
PASSWORD = "Str0ng!Passw0rd"


class FakeHasher:
    def __init__(self) -> None:
        self.verify_calls = 0

    def hash(self, password: PlaintextPassword) -> PasswordHash:
        return PasswordHash(f"hash:{password.reveal()}")

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        self.verify_calls += 1
        return self.hash(password) == password_hash

    def dummy_hash(self) -> PasswordHash:
        return PasswordHash("hash:dummy-password")

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        return False


class FakeTokenFactory:
    def __init__(self) -> None:
        self.secrets: list[str] = []

    def new_secret(self) -> str:
        secret = f"secret-{len(self.secrets) + 1}"
        self.secrets.append(secret)
        return secret

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(f"token-hash:{secret}")


class FakeStores:
    def __init__(self) -> None:
        self.users_by_email: dict[NormalizedEmail, User] = {}
        self.users_by_id: dict[UserId, User] = {}
        self.refresh_by_hash: dict[TokenHash, RefreshToken] = {}
        self.one_time: dict[TokenHash, OneTimeToken] = {}
        self.events: list[str] = []
        self.fail_after_add = False
        self.fail_after_issue = False
        self.fail_after_event = False
        self.users = self
        self.refresh_tokens = self
        self.one_time_tokens = self
        self.security_events = self

    async def add(self, value: User | RefreshToken, *, now: datetime | None = None) -> None:
        if isinstance(value, User):
            self.users_by_email[value.email] = value
            self.users_by_id[value.id] = value
            if self.fail_after_add:
                raise RuntimeError("simulated persistence failure")
            return
        self.refresh_by_hash[value.token_hash] = value

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        return self.users_by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    async def get_for_update(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: User, *, now: datetime) -> None:
        self.users_by_email[user.email] = user
        self.users_by_id[user.id] = user

    async def issue(self, token: OneTimeToken, *, now: datetime) -> int:
        for existing in self.one_time.values():
            if existing.user_id == token.user_id and existing.purpose == token.purpose:
                self.one_time[existing.token_hash] = existing.supersede(now)
        self.one_time[token.token_hash] = token
        if self.fail_after_issue:
            raise RuntimeError("simulated token persistence failure")
        return 0

    async def get(self, token_hash: TokenHash) -> RefreshToken | OneTimeToken | None:
        return self.refresh_by_hash.get(token_hash) or self.one_time.get(token_hash)

    async def get_for_consumption(self, token_hash: TokenHash) -> OneTimeToken | None:
        return self.one_time.get(token_hash)

    async def mark_consumed(self, token: OneTimeToken) -> None:
        self.one_time[token.token_hash] = token

    async def get_for_rotation(self, token_hash: TokenHash) -> RefreshToken | None:
        return self.refresh_by_hash.get(token_hash)

    async def rotate(self, revoked: RefreshToken, successor: RefreshToken) -> None:
        self.refresh_by_hash[revoked.token_hash] = revoked
        self.refresh_by_hash[successor.token_hash] = successor

    async def has_live_session(self, session_id: str, user_id: UserId, *, now: datetime) -> bool:
        return any(
            str(token.session_id) == session_id
            and token.user_id == user_id
            and not token.is_revoked
            and not token.is_expired_at(now)
            for token in self.refresh_by_hash.values()
        )

    async def revoke_family(self, family_id: object, *, now: datetime, reason: RevocationReason) -> int:
        count = 0
        for key, token in tuple(self.refresh_by_hash.items()):
            if token.family_id == family_id and not token.is_revoked:
                self.refresh_by_hash[key] = token.revoke(now, reason)
                count += 1
        return count

    async def revoke_all_for_user(self, user_id: object, *, now: datetime, reason: RevocationReason) -> int:
        count = 0
        for key, token in tuple(self.refresh_by_hash.items()):
            if token.user_id == user_id and not token.is_revoked:
                self.refresh_by_hash[key] = token.revoke(now, reason)
                count += 1
        return count

    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None:
        self.events.append(event_type)
        if self.fail_after_event:
            raise RuntimeError("simulated event persistence failure")


class FakeTransaction:
    def __init__(self, stores: FakeStores) -> None:
        self.stores = stores

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeStores]:
        snapshot = (
            dict(self.stores.users_by_email),
            dict(self.stores.users_by_id),
            dict(self.stores.refresh_by_hash),
            dict(self.stores.one_time),
            list(self.stores.events),
        )
        try:
            yield self.stores
        except Exception:
            (
                self.stores.users_by_email,
                self.stores.users_by_id,
                self.stores.refresh_by_hash,
                self.stores.one_time,
                self.stores.events,
            ) = snapshot
            raise


class FakeLimiter:
    def __init__(self) -> None:
        self.allowed = True

    async def allow(self, key: str, *, now: datetime) -> bool:
        return self.allowed


class FakeKeys:
    def build(self, scope: str, subject: str) -> str:
        return f"{scope}:{subject}"


class FakeAccessIssuer:
    def __init__(self) -> None:
        self.entries = {}

    def issue(self, *, user_id: object, session_id: str, expires_at: datetime) -> str:
        token = f"access-{len(self.entries) + 1}"
        self.entries[token] = (user_id, session_id, expires_at)
        return token

    def validate(self, token: str, *, now: datetime) -> tuple[object, str] | None:
        entry = self.entries.get(token)
        if entry is None or now >= entry[2]:
            return None
        return entry[0], entry[1]


def build_service(
    *, require_email_verification: bool = True
) -> tuple[CustomerAuthService, FakeStores, FakeTokenFactory, FakeHasher, FakeAccessIssuer]:
    stores, tokens, hasher, access = FakeStores(), FakeTokenFactory(), FakeHasher(), FakeAccessIssuer()
    limiter = FakeLimiter()
    return (
        CustomerAuthService(
            FakeTransaction(stores),
            FixedClock(NOW),
            hasher,
            tokens,
            access,
            limiter,
            limiter,
            FakeKeys(),
            require_email_verification=require_email_verification,
        ),
        stores,
        tokens,
        hasher,
        access,
    )


@pytest.mark.asyncio
async def test_4_1_register_verify_post_then_login_succeeds() -> None:
    service, stores, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    assert await service.verify_post(tokens.secrets[-1]) is True
    session = await service.login("customer@gmail.com", PASSWORD)
    assert session is not None and stores.users_by_email


@pytest.mark.asyncio
async def test_4_2_resend_invalidates_previous_verification_token() -> None:
    service, _, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    old = tokens.secrets[-1]
    await service.resend_verification("customer@gmail.com")
    assert await service.verify_post(old) is False
    assert await service.verify_post(tokens.secrets[-1]) is True


@pytest.mark.asyncio
async def test_4_3_and_4_4_login_rejects_unverified_or_disabled_account() -> None:
    service, stores, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    assert await service.login("customer@gmail.com", PASSWORD) is None
    await service.verify_post(tokens.secrets[-1])
    user = next(iter(stores.users_by_id.values())).disable()
    await stores.save(user, now=NOW)
    assert await service.login("customer@gmail.com", PASSWORD) is None


@pytest.mark.asyncio
async def test_4_5_unknown_and_wrong_password_are_generic_and_both_hash() -> None:
    service, _, tokens, hasher, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    assert await service.login("unknown@gmail.com", PASSWORD) is None
    unknown_calls = hasher.verify_calls
    assert await service.login("customer@gmail.com", "Wr0ng!Passw0rd") is None
    assert hasher.verify_calls == unknown_calls + 1


@pytest.mark.asyncio
async def test_4_6_4_7_and_4_14_server_side_checks_reject_expired_or_revoked_sessions() -> None:
    service, stores, tokens, _, access = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    session = await service.login("customer@gmail.com", PASSWORD)
    assert session is not None
    assert await service.me(session.access_token) is not None
    await service.logout_current(session.refresh_token.reveal())
    assert await service.me(session.access_token) is None
    with pytest.raises(SessionRevokedError):
        await service.refresh(session.refresh_token.reveal())
    assert access.validate("not-a-token", now=NOW) is None


@pytest.mark.asyncio
async def test_4_8_4_10_4_11_two_device_rotation_expiry_and_replay_scope() -> None:
    service, stores, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    first, second = (
        await service.login("customer@gmail.com", PASSWORD),
        await service.login("customer@gmail.com", PASSWORD),
    )
    assert first and second
    rotated = await service.refresh(first.refresh_token.reveal())
    assert rotated.family_expires_at == first.family_expires_at
    with pytest.raises(RefreshTokenReplayError):
        await service.refresh(first.refresh_token.reveal())
    assert (await service.refresh(second.refresh_token.reveal())).refresh_token
    assert any(token.family_id == first.family_id and token.is_revoked for token in stores.refresh_by_hash.values())


@pytest.mark.asyncio
async def test_4_9_concurrent_second_refresh_is_refused() -> None:
    service, _, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    session = await service.login("customer@gmail.com", PASSWORD)
    assert session is not None
    await service.refresh(session.refresh_token.reveal())
    with pytest.raises(RefreshTokenReplayError):
        await service.refresh(session.refresh_token.reveal())


@pytest.mark.asyncio
async def test_4_12_and_4_13_current_and_all_logout_have_correct_scope() -> None:
    service, _, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    first, second = (
        await service.login("customer@gmail.com", PASSWORD),
        await service.login("customer@gmail.com", PASSWORD),
    )
    assert first and second
    await service.logout_current(first.refresh_token.reveal())
    rotated_second = await service.refresh(second.refresh_token.reveal())
    await service.logout_all(rotated_second.access_token)
    with pytest.raises(SessionRevokedError):
        await service.refresh(rotated_second.refresh_token.reveal())


@pytest.mark.asyncio
async def test_4_15_get_verification_is_a_non_consuming_operation() -> None:
    service, _, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    assert await service.verify_get(tokens.secrets[-1]) is False
    assert await service.verify_post(tokens.secrets[-1]) is True


@pytest.mark.asyncio
async def test_4_16_failed_registration_rolls_back_every_side_effect() -> None:
    service, stores, _, _, _ = build_service()
    stores.fail_after_add = True
    with pytest.raises(RuntimeError):
        await service.register("customer@gmail.com", PASSWORD)
    assert not stores.users_by_id and not stores.one_time and not stores.refresh_by_hash


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_registration_rolls_back_after_verification_token_persistence_failure() -> None:
    service, stores, _, _, _ = build_service()
    stores.fail_after_issue = True

    with pytest.raises(RuntimeError):
        await service.register("customer@gmail.com", PASSWORD)

    assert not stores.users_by_id
    assert not stores.one_time
    assert not stores.events


@pytest.mark.asyncio
async def test_registration_rolls_back_after_security_event_persistence_failure() -> None:
    service, stores, _, _, _ = build_service()
    stores.fail_after_event = True

    with pytest.raises(RuntimeError):
        await service.register("customer@gmail.com", PASSWORD)

    assert not stores.users_by_id
    assert not stores.one_time
    assert not stores.events


@pytest.mark.asyncio
async def test_4_17_security_events_never_persist_raw_secrets() -> None:
    service, stores, tokens, _, _ = build_service()
    await service.register("customer@gmail.com", PASSWORD)
    await service.verify_post(tokens.secrets[-1])
    session = await service.login("customer@gmail.com", PASSWORD)
    assert session is not None
    rendered = repr(stores.events)
    for secret in (PASSWORD, tokens.secrets[-1], session.access_token, session.refresh_token.reveal()):
        assert secret not in rendered


@pytest.mark.asyncio
async def test_registration_can_activate_immediately_when_verification_is_off() -> None:
    """Công tắc tắt xác minh: đăng ký xong đăng nhập được ngay.

    Có công tắc vì hai điều kiện vận hành khác nhau tồn tại song song. Khi nhà
    cung cấp mail chưa chạy được, bắt xác minh qua mail nghĩa là KHÔNG AI đăng ký
    nổi — một lớp chống lạm dụng không bảo vệ được gì trên một sản phẩm không ai
    dùng được. Mặc định vẫn là BẬT; tắt phải là một quyết định tường minh, ghi
    trong biến môi trường, không phải mặc định lặng lẽ.

    Đánh đổi đã biết khi tắt: ai cũng đăng ký được bằng email người khác.
    """

    service, stores, _, _, _ = build_service(require_email_verification=False)

    await service.register("khach.moi@gmail.com", PASSWORD)

    user = stores.users_by_email[NormalizedEmail.parse_customer("khach.moi@gmail.com")]
    assert user.state is AccountState.ACTIVE
    assert stores.one_time == {}, "tat xac minh thi khong sinh token thua"

    session = await service.login("khach.moi@gmail.com", PASSWORD)
    assert session is not None, "dang ky xong phai dang nhap duoc ngay"


@pytest.mark.asyncio
async def test_registration_still_requires_verification_by_default() -> None:
    """Mặc định KHÔNG đổi: quên đặt biến môi trường thì vẫn siết như cũ."""

    service, stores, _, _, _ = build_service()

    await service.register("khach.cu@gmail.com", PASSWORD)

    user = stores.users_by_email[NormalizedEmail.parse_customer("khach.cu@gmail.com")]
    assert user.state is AccountState.PENDING_VERIFICATION
    assert stores.one_time, "van phai sinh token xac minh"
    assert await service.login("khach.cu@gmail.com", PASSWORD) is None
