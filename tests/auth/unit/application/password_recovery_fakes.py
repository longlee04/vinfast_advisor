"""Deterministic fakes shared by password recovery acceptance tests."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio

from src.auth.application.password_recovery import PasswordRecoveryService
from src.auth.application.ports import EmailDeliveryError
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import ConcurrentTokenUseError
from src.auth.domain.sessions import OneTimeToken, RefreshToken, RevocationReason
from src.auth.domain.values import (
    NormalizedEmail,
    PasswordHash,
    PlaintextPassword,
    PlaintextToken,
    TokenHash,
    UserId,
)

NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)
PASSWORD = "Str0ng!Passw0rd"
NEW_PASSWORD = "N3w!StrongPassw0rd"


class FakeHasher:
    def __init__(self) -> None:
        self.verify_calls = 0

    def hash(self, password: PlaintextPassword) -> PasswordHash:
        return PasswordHash(f"hash:{password.reveal()}")

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        self.verify_calls += 1
        return self.hash(password) == password_hash

    def dummy_hash(self) -> PasswordHash:
        return PasswordHash("hash:dummy")

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        return False


class FakeTokenFactory:
    def __init__(self) -> None:
        self.secrets: list[str] = []

    def new_secret(self) -> str:
        secret = f"reset-token-{len(self.secrets) + 1}"
        self.secrets.append(secret)
        return secret

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(f"hash:{secret}")


class FakeRateLimitKeys:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def build(self, scope: str, subject: str) -> str:
        digest = hashlib.sha256(subject.encode()).hexdigest()
        key = f"{scope}:{digest}"
        self.calls.append((scope, key))
        return key


class FakeRateLimiter:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.allowed = True

    async def allow(self, key: str, *, now: datetime) -> bool:
        self.keys.append(key)
        return self.allowed


class FakeEmailSender:
    def __init__(self) -> None:
        self.fail_delivery = False
        self.deliveries: list[tuple[NormalizedEmail, PlaintextToken]] = []

    async def send_password_reset(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        if self.fail_delivery:
            raise EmailDeliveryError("email delivery failed")
        self.deliveries.append((recipient, token))


class FakeStores:
    def __init__(self) -> None:
        self.users_by_email: dict[NormalizedEmail, User] = {}
        self.synchronize_consumption = False
        self.concurrent_reads = 0
        self.concurrent_read_gate = anyio.Event()
        self.users_by_id: dict[UserId, User] = {}
        self.one_time: dict[TokenHash, OneTimeToken] = {}
        self.refresh_by_hash: dict[TokenHash, RefreshToken] = {}
        self.events: list[str] = []
        self.event_values: list[str] = []
        self.users = self
        self.one_time_tokens = self
        self.refresh_tokens = self
        self.security_events = self

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        return self.users_by_email.get(email)

    async def get_for_update(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: User, *, now: datetime) -> None:
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user

    async def issue(self, token: OneTimeToken, *, now: datetime) -> int:
        for key, existing in tuple(self.one_time.items()):
            if existing.user_id == token.user_id and existing.purpose is token.purpose:
                self.one_time[key] = existing.supersede(now)
        self.one_time[token.token_hash] = token
        return 1

    async def get_for_consumption(self, token_hash: TokenHash) -> OneTimeToken | None:
        if not self.synchronize_consumption:
            return self.one_time.get(token_hash)
        self.concurrent_reads += 1
        if self.concurrent_reads == 2:
            self.concurrent_read_gate.set()
        await self.concurrent_read_gate.wait()
        return self.one_time.get(token_hash)

    async def mark_consumed(self, token: OneTimeToken) -> None:
        current = self.one_time[token.token_hash]
        if current.is_consumed:
            raise ConcurrentTokenUseError("token was already used")
        self.one_time[token.token_hash] = token

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime, reason: RevocationReason) -> int:
        count = 0
        for key, refresh in tuple(self.refresh_by_hash.items()):
            if refresh.user_id == user_id and not refresh.is_revoked:
                self.refresh_by_hash[key] = refresh.revoke(now, reason)
                count += 1
        return count

    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None:
        self.events.append(event_type)
        self.event_values.append(str(actor_user_id or ""))


class FakeTransaction:
    def __init__(self, stores: FakeStores) -> None:
        self._stores = stores

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeStores]:
        snapshot = (
            dict(self._stores.users_by_email),
            dict(self._stores.users_by_id),
            dict(self._stores.one_time),
            dict(self._stores.refresh_by_hash),
            list(self._stores.events),
            list(self._stores.event_values),
        )
        try:
            yield self._stores
        except EmailDeliveryError:
            (
                self._stores.users_by_email,
                self._stores.users_by_id,
                self._stores.one_time,
                self._stores.refresh_by_hash,
                self._stores.events,
                self._stores.event_values,
            ) = snapshot
            raise


def make_user(identifier: str = "customer") -> User:
    return User(
        id=UserId(identifier),
        email=NormalizedEmail.parse(f"{identifier}@gmail.com"),
        role=Role.CUSTOMER,
        state=AccountState.ACTIVE,
        password_hash=PasswordHash(f"hash:{PASSWORD}"),
        created_at=NOW,
    )


def build_service() -> tuple[
    PasswordRecoveryService,
    FakeStores,
    FakeTokenFactory,
    FakeHasher,
    FakeEmailSender,
    FakeRateLimitKeys,
    FakeRateLimiter,
]:
    stores = FakeStores()
    tokens = FakeTokenFactory()
    hasher = FakeHasher()
    email = FakeEmailSender()
    keys = FakeRateLimitKeys()
    limiter = FakeRateLimiter()
    service = PasswordRecoveryService(FakeTransaction(stores), FixedClock(NOW), hasher, tokens, email, limiter, keys)
    return service, stores, tokens, hasher, email, keys, limiter
