"""Focused Task 4 refresh-contract regression tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import anyio
import pytest

from src.auth.application.customer_auth import AuthSession, CustomerAuthService
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import (
    ConcurrentTokenUseError,
    RefreshTokenReplayError,
    SessionExpiredError,
    SessionRevokedError,
)
from src.auth.domain.sessions import RefreshToken, RevocationReason
from src.auth.domain.values import (
    NormalizedEmail,
    PasswordHash,
    PlaintextPassword,
    TokenHash,
    UserId,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)
PASSWORD = PlaintextPassword("Str0ng!Passw0rd")


class FakeHasher:
    def hash(self, password: PlaintextPassword) -> PasswordHash:
        return PasswordHash(f"hash:{password.reveal()}")

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        return self.hash(password) == password_hash

    def dummy_hash(self) -> PasswordHash:
        return PasswordHash("hash:dummy-password")

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        return False


class FakeTokens:
    def __init__(self) -> None:
        self._counter = 0

    def new_secret(self) -> str:
        self._counter += 1
        return f"secret-{self._counter}"

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(f"hash:{secret}")


class FakeAccessTokens:
    def __init__(self) -> None:
        self.entries: dict[str, tuple[UserId, str, datetime]] = {}

    def issue(self, *, user_id: UserId, session_id: str, expires_at: datetime) -> str:
        token = f"access-{len(self.entries) + 1}"
        self.entries[token] = (user_id, session_id, expires_at)
        return token

    def validate(self, token: str, *, now: datetime) -> tuple[UserId, str] | None:
        entry = self.entries.get(token)
        if entry is None or now >= entry[2]:
            return None
        return entry[0], entry[1]


@dataclass(slots=True)
class FakeUsers:
    by_id: dict[UserId, User]
    by_email: dict[NormalizedEmail, User]

    async def add(self, user: User, *, now: datetime) -> None:
        self.by_id[user.id] = user
        self.by_email[user.email] = user

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        return self.by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self.by_id.get(user_id)

    async def get_for_update(self, user_id: UserId) -> User | None:
        return self.by_id.get(user_id)

    async def save(self, user: User, *, now: datetime) -> None:
        self.by_id[user.id] = user
        self.by_email[user.email] = user


@dataclass(slots=True)
class FakeRefreshes:
    by_hash: dict[TokenHash, RefreshToken]
    race_hash: TokenHash | None = None
    race_arrivals: int = 0
    race_ready: anyio.Event | None = None
    race_release: anyio.Event | None = None
    reject_rotation: bool = False

    async def add(self, token: RefreshToken) -> None:
        self.by_hash[token.token_hash] = token

    async def get(self, token_hash: TokenHash) -> RefreshToken | None:
        return self.by_hash.get(token_hash)

    async def get_for_rotation(self, token_hash: TokenHash) -> RefreshToken | None:
        token = self.by_hash.get(token_hash)
        if token_hash == self.race_hash and self.race_ready is not None and self.race_release is not None:
            self.race_arrivals += 1
            if self.race_arrivals == 2:
                self.race_ready.set()
            await self.race_release.wait()
        return token

    async def rotate(self, revoked: RefreshToken, successor: RefreshToken) -> None:
        if self.reject_rotation:
            raise ConcurrentTokenUseError("conditional update rejected")
        authoritative = self.by_hash.get(revoked.token_hash)
        if authoritative is None or authoritative.is_revoked:
            raise RefreshTokenReplayError("atomic rotation lost")
        self.by_hash[revoked.token_hash] = revoked
        self.by_hash[successor.token_hash] = successor

    async def has_live_session(self, session_id: str, user_id: UserId, *, now: datetime) -> bool:
        return any(
            str(token.session_id) == session_id
            and token.user_id == user_id
            and not token.is_revoked
            and not token.is_expired_at(now)
            for token in self.by_hash.values()
        )

    async def revoke_family(self, family_id: str, *, now: datetime, reason: RevocationReason) -> int:
        changed = 0
        for key, token in tuple(self.by_hash.items()):
            if str(token.family_id) == family_id and not token.is_revoked:
                self.by_hash[key] = token.revoke(now, reason)
                changed += 1
        return changed

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime, reason: RevocationReason) -> int:
        changed = 0
        for key, token in tuple(self.by_hash.items()):
            if token.user_id == user_id and not token.is_revoked:
                self.by_hash[key] = token.revoke(now, reason)
                changed += 1
        return changed


@dataclass(slots=True)
class FakeOneTime:
    tokens: dict[TokenHash, object]


@dataclass(slots=True)
class FakeEvents:
    entries: list[str]

    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None:
        self.entries.append(event_type)


@dataclass(slots=True)
class FakeStores:
    users: FakeUsers
    refresh_tokens: FakeRefreshes
    one_time_tokens: FakeOneTime
    security_events: FakeEvents


class FakeTransaction:
    def __init__(self, stores: FakeStores) -> None:
        self._stores = stores

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeStores]:
        yield self._stores


def build_service(now: datetime = NOW) -> tuple[CustomerAuthService, FakeStores, FakeTokens, FakeAccessTokens, User]:
    user = User(
        id=UserId("customer-1"),
        email=NormalizedEmail.parse_customer("customer@gmail.com"),
        role=Role.CUSTOMER,
        state=AccountState.ACTIVE,
        password_hash=PasswordHash(f"hash:{PASSWORD.reveal()}"),
        created_at=NOW,
    )
    stores = FakeStores(
        FakeUsers({user.id: user}, {user.email: user}), FakeRefreshes({}), FakeOneTime({}), FakeEvents([])
    )
    tokens, access = FakeTokens(), FakeAccessTokens()
    return (
        CustomerAuthService(
            FakeTransaction(stores),
            FixedClock(now),
            FakeHasher(),
            tokens,
            access,
            AllowLimiter(),
            AllowLimiter(),
            TestKeys(),
        ),
        stores,
        tokens,
        access,
        user,
    )


class AllowLimiter:
    async def allow(self, key: str, *, now: datetime) -> bool:
        return True


class TestKeys:
    def build(self, scope: str, subject: str) -> str:
        return f"{scope}:{subject}"


async def login(service: CustomerAuthService) -> AuthSession:
    session = await service.login("customer@gmail.com", PASSWORD.reveal())
    assert session is not None
    return session


@pytest.mark.asyncio
async def test_refresh_concurrently_rotates_once_and_rejects_the_loser() -> None:
    service, stores, _, _, _ = build_service()
    session = await login(service)
    token_hash = TokenHash(f"hash:{session.refresh_token.reveal()}")
    stores.refresh_tokens.race_hash = token_hash
    stores.refresh_tokens.race_ready = anyio.Event()
    stores.refresh_tokens.race_release = anyio.Event()
    successes: list[AuthSession] = []
    replays: list[RefreshTokenReplayError] = []

    async def refresh_once() -> None:
        try:
            successes.append(await service.refresh(session.refresh_token.reveal()))
        except RefreshTokenReplayError as error:
            replays.append(error)

    async with anyio.create_task_group() as group:
        group.start_soon(refresh_once)
        group.start_soon(refresh_once)
        await stores.refresh_tokens.race_ready.wait()
        stores.refresh_tokens.race_release.set()

    assert len(successes) == 1
    assert len(replays) == 1
    assert sum(not token.is_revoked for token in stores.refresh_tokens.by_hash.values()) == 1


@pytest.mark.asyncio
async def test_refresh_at_exact_expiry_is_refused() -> None:
    service, stores, _, _, _ = build_service(NOW + timedelta(days=30))
    session = await login(
        CustomerAuthService(
            FakeTransaction(stores),
            FixedClock(NOW),
            FakeHasher(),
            FakeTokens(),
            FakeAccessTokens(),
            AllowLimiter(),
            AllowLimiter(),
            TestKeys(),
        )
    )
    with pytest.raises(SessionExpiredError):
        await service.refresh(session.refresh_token.reveal())


@pytest.mark.asyncio
async def test_refresh_requires_an_authoritative_live_session() -> None:
    service, stores, _, _, _ = build_service()
    session = await login(service)
    await stores.refresh_tokens.revoke_family(str(session.family_id), now=NOW, reason=RevocationReason.LOGOUT)
    with pytest.raises(SessionRevokedError):
        await service.refresh(session.refresh_token.reveal())


@pytest.mark.asyncio
async def test_conditional_rotation_conflict_is_a_stable_refresh_refusal() -> None:
    service, stores, _, _, _ = build_service()
    session = await login(service)
    stores.refresh_tokens.reject_rotation = True

    with pytest.raises(RefreshTokenReplayError):
        await service.refresh(session.refresh_token.reveal())


@pytest.mark.asyncio
async def test_logout_current_only_revokes_its_login_family() -> None:
    service, stores, _, _, _ = build_service()
    first = await login(service)
    second = await login(service)

    assert first.family_id != second.family_id
    assert await service.logout_current(first.refresh_token.reveal()) is True
    with pytest.raises(SessionRevokedError):
        await service.refresh(first.refresh_token.reveal())
    assert (await service.refresh(second.refresh_token.reveal())).user_id == second.user_id


@pytest.mark.asyncio
async def test_replay_does_not_revoke_another_users_family() -> None:
    service, stores, _, _, user = build_service()
    other = User(
        id=UserId("customer-2"),
        email=NormalizedEmail.parse_customer("other@gmail.com"),
        role=Role.CUSTOMER,
        state=AccountState.ACTIVE,
        password_hash=user.password_hash,
        created_at=NOW,
    )
    await stores.users.add(other, now=NOW)
    first = await login(service)
    second = await service.login("other@gmail.com", PASSWORD.reveal())
    assert second is not None
    await service.refresh(first.refresh_token.reveal())

    with pytest.raises(RefreshTokenReplayError):
        await service.refresh(first.refresh_token.reveal())

    assert (await service.refresh(second.refresh_token.reveal())).user_id == other.id
