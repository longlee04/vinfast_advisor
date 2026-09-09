"""Task 5 staff lifecycle application acceptance tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.auth.application.contracts import UserPage, UserSummary
from src.auth.application.ports import AbuseLimitExceededError
from src.auth.application.staff_auth import StaffAuthService
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import (
    AuthorizationError,
    TemporaryPasswordExpiredError,
    TemporaryPasswordRequiredError,
)
from src.auth.domain.sessions import RefreshToken, RevocationReason
from src.auth.domain.values import (
    FamilyId,
    NormalizedEmail,
    PasswordHash,
    PlaintextPassword,
    SessionId,
    TokenHash,
    UserId,
)

NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)
ADMIN_PASSWORD = "Str0ng!AdminPass"


class FakeHasher:
    def __init__(self) -> None:
        self._hashes: dict[str, PasswordHash] = {}

    def hash(self, password: PlaintextPassword) -> PasswordHash:
        value = password.reveal()
        if value not in self._hashes:
            self._hashes[value] = PasswordHash(f"hash-{len(self._hashes) + 1}")
        return self._hashes[value]

    def verify(self, password: PlaintextPassword, password_hash: PasswordHash) -> bool:
        return self.hash(password) == password_hash

    def dummy_hash(self) -> PasswordHash:
        return PasswordHash("hash:dummy")

    def needs_rehash(self, password_hash: PasswordHash) -> bool:
        return False


class FakeTokenFactory:
    def __init__(self) -> None:
        self._next = 0

    def new_secret(self) -> str:
        self._next += 1
        return f"Temp!Pass{self._next}word"

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(f"token-hash:{secret}")


class FakeEmailSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[NormalizedEmail, PlaintextPassword]] = []
        self.should_fail = False

    async def send_temporary_password(self, *, recipient: NormalizedEmail, password: PlaintextPassword) -> None:
        if self.should_fail:
            raise DeliveryError()
        self.deliveries.append((recipient, password))


class DeliveryError(RuntimeError):
    """The deterministic fake provider refused a delivery."""


class FakeStores:
    def __init__(self) -> None:
        self.users_by_id: dict[UserId, User] = {}
        self.users_by_email: dict[NormalizedEmail, User] = {}
        self.refresh_by_hash: dict[TokenHash, RefreshToken] = {}
        self.events: list[str] = []
        self.users = self
        self.refresh_tokens = self
        self.security_events = self

    async def add(self, entity: User | RefreshToken, *, now: datetime | None = None) -> None:
        if isinstance(entity, RefreshToken):
            self.refresh_by_hash[entity.token_hash] = entity
            return
        if entity.email in self.users_by_email:
            raise DuplicateEmailError()
        self.users_by_id[entity.id] = entity
        self.users_by_email[entity.email] = entity

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        return self.users_by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    async def get_for_update(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: User, *, now: datetime) -> None:
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user

    async def claim_first_admin(self, user: User, *, now: datetime) -> bool:
        if any(existing.role is Role.ADMIN for existing in self.users_by_id.values()):
            return False
        await self.add(user, now=now)
        return True

    async def lock_active_admin_count(self) -> int:
        return sum(user.role is Role.ADMIN and user.state is AccountState.ACTIVE for user in self.users_by_id.values())

    async def list_page(
        self,
        *,
        role: Role | None,
        state: AccountState | None,
        email_query: str | None,
        page: int,
        page_size: int,
    ) -> UserPage:
        matched = [
            user
            for user in self.users_by_id.values()
            if (role is None or user.role is role)
            and (state is None or user.state is state)
            and (email_query is None or email_query in str(user.email))
        ]
        matched.sort(key=lambda user: str(user.id))
        start = (page - 1) * page_size
        window = matched[start : start + page_size]
        return UserPage(
            items=tuple(
                UserSummary(
                    id=user.id,
                    email=user.email,
                    role=user.role,
                    state=user.state,
                    created_at=user.created_at,
                    last_activity_at=None,
                )
                for user in window
            ),
            total=len(matched),
            page=page,
            page_size=page_size,
        )

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime, reason: RevocationReason) -> int:
        revoked = 0
        for token_hash, token in tuple(self.refresh_by_hash.items()):
            if token.user_id == user_id and not token.is_revoked:
                self.refresh_by_hash[token_hash] = token.revoke(now, reason)
                revoked += 1
        return revoked

    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None:
        self.events.append(event_type)


class DuplicateEmailError(RuntimeError):
    """The in-memory user identity was already claimed."""


class FakeTransaction:
    def __init__(self, stores: FakeStores) -> None:
        self._stores = stores

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeStores]:
        snapshot = (
            dict(self._stores.users_by_id),
            dict(self._stores.users_by_email),
            dict(self._stores.refresh_by_hash),
            list(self._stores.events),
        )
        try:
            yield self._stores
        except DeliveryError:
            (
                self._stores.users_by_id,
                self._stores.users_by_email,
                self._stores.refresh_by_hash,
                self._stores.events,
            ) = snapshot
            raise


def make_user(*, identifier: str, role: Role, state: AccountState = AccountState.ACTIVE) -> User:
    return User(
        id=UserId(identifier),
        email=NormalizedEmail.parse(f"{identifier}@example.com"),
        role=role,
        state=state,
        password_hash=PasswordHash(f"hash:{identifier}"),
        created_at=NOW,
    )


class FakeAccessTokenIssuer:
    def issue(self, *, user_id: UserId, session_id: str, expires_at: datetime) -> str:
        return f"access:{user_id}:{session_id}"

    def validate(self, token: str, *, now: datetime) -> tuple[UserId, str] | None:
        if not token.startswith("access:"):
            return None
        _, user_id, session_id = token.split(":", 2)
        return (UserId(user_id), session_id)


class FakeLimiter:
    def __init__(self) -> None:
        self.allowed = True
        self.calls: list[str] = []

    async def allow(self, key: str, *, now: datetime) -> bool:
        self.calls.append(key)
        return self.allowed


class FakeKeyBuilder:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def build(self, scope: str, subject: str) -> str:
        self.scopes.append(scope)
        return f"{scope}:{subject}"


def build_service() -> tuple[StaffAuthService, FakeStores, FakeEmailSender]:
    stores = FakeStores()
    email = FakeEmailSender()
    return (
        StaffAuthService(
            FakeTransaction(stores),
            FixedClock(NOW),
            FakeHasher(),
            FakeTokenFactory(),
            email,
            access_tokens=FakeAccessTokenIssuer(),
            login_limiter=FakeLimiter(),
            rate_limit_keys=FakeKeyBuilder(),
        ),
        stores,
        email,
    )


def seed_password(service: StaffAuthService, user: User, password: str) -> User:
    """Rewrite fixture user so service hasher accepts password."""
    return User(
        id=user.id,
        email=user.email,
        role=user.role,
        state=user.state,
        password_hash=service._password_hasher.hash(PlaintextPassword(password)),
        created_at=user.created_at,
        temporary_password_expires_at=user.temporary_password_expires_at,
    )


@pytest.mark.asyncio
async def test_admin_lists_users_with_role_filter() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    advisor = make_user(identifier="advisor", role=Role.ADVISOR)
    await stores.add(admin, now=NOW)
    await stores.add(advisor, now=NOW)

    page = await service.list_users(admin.id, role=Role.ADVISOR)

    assert page.total == 1
    assert page.items[0].email == advisor.email


@pytest.mark.asyncio
async def test_advisor_may_not_list_users() -> None:
    service, stores, _ = build_service()
    advisor = make_user(identifier="advisor", role=Role.ADVISOR)
    await stores.add(advisor, now=NOW)

    with pytest.raises(AuthorizationError):
        await service.list_users(advisor.id)


@pytest.mark.asyncio
async def test_page_size_is_capped_at_one_hundred() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)

    page = await service.list_users(admin.id, page_size=5000)

    assert page.page_size == 100


@pytest.mark.asyncio
async def test_admin_listing_defaults_to_page_size_twenty() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)

    page = await service.list_users(admin.id)

    assert page.page_size == 20


@pytest.mark.asyncio
async def test_admin_listing_bounds_page_and_page_size_at_one() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    target = make_user(identifier="target", role=Role.ADVISOR)
    await stores.add(admin, now=NOW)
    await stores.add(target, now=NOW)

    page = await service.list_users(admin.id, page=0, page_size=0)

    assert page.page == 1
    assert page.page_size == 1
    assert len(page.items) == 1


@pytest.mark.asyncio
async def test_admin_listing_forwards_filters_and_page_window() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    targets = [
        make_user(identifier=f"filter-{suffix}", role=Role.ADVISOR, state=AccountState.DISABLED)
        for suffix in ("a", "b", "c")
    ]
    await stores.add(admin, now=NOW)
    for target in targets:
        await stores.add(target, now=NOW)

    page = await service.list_users(
        admin.id,
        role=Role.ADVISOR,
        state=AccountState.DISABLED,
        email_query="filter-",
        page=2,
        page_size=1,
    )

    assert page.total == 3
    assert page.page == 2
    assert page.page_size == 1
    assert page.items[0].id == targets[1].id


@pytest.mark.asyncio
async def test_5_1_concurrent_admin_bootstrap_allows_exactly_one_active_admin() -> None:
    service, stores, _ = build_service()

    first = await service.bootstrap_first_admin("first@example.com", ADMIN_PASSWORD)
    second = await service.bootstrap_first_admin("second@example.com", ADMIN_PASSWORD)

    assert first is True
    assert second is False
    assert [user.role for user in stores.users_by_id.values()] == [Role.ADMIN]


@pytest.mark.asyncio
async def test_5_3_5_4_and_5_6_admin_creates_only_staff_with_hash_only_temporary_password() -> None:
    service, stores, email = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)

    advisor = await service.create_staff(admin.id, "advisor@example.com", Role.ADVISOR)

    delivered = email.deliveries[0][1].reveal()
    assert advisor.state is AccountState.TEMPORARY_PASSWORD
    assert advisor.password_hash != PasswordHash(delivered)
    with pytest.raises(AuthorizationError):
        await service.create_staff(admin.id, "customer@example.com", Role.CUSTOMER)


@pytest.mark.asyncio
async def test_5_6_temporary_password_requires_change_before_normal_session() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)
    staff = await service.create_staff(admin.id, "advisor@example.com", Role.ADVISOR)

    activated = await service.complete_temporary_password_change(staff.id, "New!StrongPass1")

    assert activated.state is AccountState.ACTIVE


@pytest.mark.asyncio
async def test_5_10_and_5_12_disable_revokes_sessions_but_protects_last_active_admin() -> None:
    service, stores, _ = build_service()
    first = make_user(identifier="first", role=Role.ADMIN)
    second = make_user(identifier="second", role=Role.ADMIN)
    await stores.add(first, now=NOW)
    await stores.add(second, now=NOW)
    token = RefreshToken(
        token_hash=TokenHash("token"),
        session_id=SessionId("session"),
        family_id=FamilyId("family"),
        user_id=second.id,
        issued_at=NOW,
        family_expires_at=NOW.replace(year=2027),
    )
    stores.refresh_by_hash[token.token_hash] = token

    disabled = await service.disable_user(first.id, second.id)
    assert disabled.is_disabled
    assert stores.refresh_by_hash[token.token_hash].revocation_reason is RevocationReason.ACCOUNT_DISABLED


@pytest.mark.asyncio
async def test_5_13_provider_failure_rolls_back_staff_creation_for_retry() -> None:
    service, stores, email = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)
    email.should_fail = True

    with pytest.raises(DeliveryError):
        await service.create_staff(admin.id, "advisor@example.com", Role.ADVISOR)

    assert NormalizedEmail.parse("advisor@example.com") not in stores.users_by_email


@pytest.mark.asyncio
async def test_5_6_expired_temporary_password_cannot_be_replaced() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    await stores.add(admin, now=NOW)
    staff = await service.create_staff(admin.id, "advisor@example.com", Role.ADVISOR)
    expired = User(
        id=staff.id,
        email=staff.email,
        role=staff.role,
        state=staff.state,
        password_hash=staff.password_hash,
        created_at=staff.created_at,
        temporary_password_expires_at=NOW - timedelta(seconds=1),
    )
    await stores.save(expired, now=NOW)

    with pytest.raises(TemporaryPasswordExpiredError):
        await service.complete_temporary_password_change(staff.id, "New!StrongPass1")


@pytest.mark.asyncio
async def test_admin_reenables_a_disabled_account() -> None:
    service, stores, _ = build_service()
    admin = make_user(identifier="admin", role=Role.ADMIN)
    target = make_user(identifier="target", role=Role.ADVISOR, state=AccountState.DISABLED)
    await stores.add(admin, now=NOW)
    await stores.add(target, now=NOW)

    enabled = await service.enable_user(admin.id, target.id)

    assert enabled.state is AccountState.ACTIVE
    assert stores.users_by_id[target.id].state is AccountState.ACTIVE
    assert "user_enabled" in stores.events


@pytest.mark.asyncio
async def test_advisor_may_not_enable_an_account() -> None:
    service, stores, _ = build_service()
    advisor = make_user(identifier="advisor", role=Role.ADVISOR)
    target = make_user(identifier="target", role=Role.ADVISOR, state=AccountState.DISABLED)
    await stores.add(advisor, now=NOW)
    await stores.add(target, now=NOW)

    with pytest.raises(AuthorizationError):
        await service.enable_user(advisor.id, target.id)

    assert stores.users_by_id[target.id].state is AccountState.DISABLED


@pytest.mark.asyncio
async def test_identify_for_password_setup_returns_temporary_staff_identity() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(
        service,
        make_user(identifier="advisor", role=Role.ADVISOR, state=AccountState.TEMPORARY_PASSWORD),
        "temporary",
    )
    await stores.add(advisor, now=NOW)

    identity = await service.identify_for_password_setup("advisor@example.com", "temporary")
    await service.complete_temporary_password_change(advisor.id, "New!StrongPass1")
    session = await service.login_after_password_setup(advisor.id)

    assert identity == advisor.id
    assert session is not None
    assert len(service._login_limiter.calls) == 1
    assert service._rate_limit_keys.scopes == ["staff_login"]


@pytest.mark.asyncio
async def test_identify_for_password_setup_rejects_active_staff() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(service, make_user(identifier="advisor", role=Role.ADVISOR), "temporary")
    await stores.add(advisor, now=NOW)

    identity = await service.identify_for_password_setup("advisor@example.com", "temporary")

    assert identity is None


@pytest.mark.asyncio
async def test_identify_for_password_setup_rejects_unknown_or_wrong_temporary_password() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(
        service,
        make_user(identifier="advisor", role=Role.ADVISOR, state=AccountState.TEMPORARY_PASSWORD),
        "temporary",
    )
    await stores.add(advisor, now=NOW)

    unknown = await service.identify_for_password_setup("nobody@example.com", "temporary")
    wrong = await service.identify_for_password_setup("advisor@example.com", "wrong")

    assert unknown is None
    assert wrong is None


@pytest.mark.asyncio
async def test_identify_for_password_setup_rejects_disabled_expired_and_customer_accounts() -> None:
    service, stores, _ = build_service()
    disabled = seed_password(
        service,
        make_user(identifier="disabled", role=Role.ADVISOR, state=AccountState.DISABLED),
        "temporary",
    )
    expired = replace(
        seed_password(
            service,
            make_user(identifier="expired", role=Role.ADVISOR, state=AccountState.TEMPORARY_PASSWORD),
            "temporary",
        ),
        temporary_password_expires_at=NOW - timedelta(microseconds=1),
    )
    customer = seed_password(
        service,
        make_user(identifier="customer", role=Role.CUSTOMER, state=AccountState.TEMPORARY_PASSWORD),
        "temporary",
    )
    for user in (disabled, expired, customer):
        await stores.add(user, now=NOW)

    disabled_identity = await service.identify_for_password_setup("disabled@example.com", "temporary")
    expired_identity = await service.identify_for_password_setup("expired@example.com", "temporary")
    customer_identity = await service.identify_for_password_setup("customer@example.com", "temporary")

    assert disabled_identity is None
    assert expired_identity is None
    assert customer_identity is None


@pytest.mark.asyncio
async def test_staff_logs_in_with_a_non_gmail_address() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(service, make_user(identifier="advisor", role=Role.ADVISOR), "advisor")
    await stores.add(advisor, now=NOW)

    session = await service.login("advisor@example.com", "advisor")

    assert session is not None
    assert session.user_id == advisor.id
    assert "staff_logged_in" in stores.events


@pytest.mark.asyncio
async def test_customer_may_not_use_the_staff_door() -> None:
    service, stores, _ = build_service()
    customer = seed_password(service, make_user(identifier="customer", role=Role.CUSTOMER), "customer")
    await stores.add(customer, now=NOW)

    assert await service.login("customer@example.com", "customer") is None


@pytest.mark.asyncio
async def test_temporary_password_state_blocks_session_issue() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(
        service,
        make_user(identifier="advisor", role=Role.ADVISOR, state=AccountState.TEMPORARY_PASSWORD),
        "advisor",
    )
    await stores.add(advisor, now=NOW)

    with pytest.raises(TemporaryPasswordRequiredError):
        await service.login("advisor@example.com", "advisor")


@pytest.mark.asyncio
async def test_unknown_staff_email_is_indistinguishable_from_a_wrong_password() -> None:
    service, _, _ = build_service()

    assert await service.login("nobody@example.com", "whatever") is None


@pytest.mark.asyncio
async def test_staff_login_uses_a_scope_separate_from_customer_login() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(service, make_user(identifier="advisor", role=Role.ADVISOR), "advisor")
    await stores.add(advisor, now=NOW)

    await service.login("advisor@example.com", "advisor")

    assert service._rate_limit_keys.scopes == ["staff_login"]


@pytest.mark.asyncio
async def test_successful_staff_login_persists_refresh_token() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(service, make_user(identifier="advisor", role=Role.ADVISOR), "advisor")
    await stores.add(advisor, now=NOW)

    session = await service.login("advisor@example.com", "advisor")

    assert session is not None
    refresh_hash = TokenHash(f"token-hash:{session.refresh_token.reveal()}")
    assert stores.refresh_by_hash[refresh_hash].user_id == advisor.id


@pytest.mark.asyncio
async def test_staff_login_rate_limit_rejection_has_no_side_effects() -> None:
    service, stores, _ = build_service()
    advisor = seed_password(service, make_user(identifier="advisor", role=Role.ADVISOR), "advisor")
    await stores.add(advisor, now=NOW)
    service._login_limiter.allowed = False

    with pytest.raises(AbuseLimitExceededError):
        await service.login("advisor@example.com", "advisor")

    assert not stores.refresh_by_hash
    assert not stores.events
    assert service._token_factory._next == 0


@pytest.mark.asyncio
async def test_five_positional_constructor_requires_dependencies_for_login() -> None:
    stores = FakeStores()
    service = StaffAuthService(
        FakeTransaction(stores), FixedClock(NOW), FakeHasher(), FakeTokenFactory(), FakeEmailSender()
    )

    with pytest.raises(RuntimeError, match="without login dependencies"):
        await service.login("advisor@example.com", "advisor")


@pytest.mark.asyncio
async def test_5_10_role_change_revokes_sessions_and_protects_last_active_admin() -> None:
    service, stores, _ = build_service()
    first = make_user(identifier="first", role=Role.ADMIN)
    second = make_user(identifier="second", role=Role.ADMIN)
    await stores.add(first, now=NOW)
    await stores.add(second, now=NOW)
    token = RefreshToken(
        token_hash=TokenHash("role-token"),
        session_id=SessionId("role-session"),
        family_id=FamilyId("role-family"),
        user_id=second.id,
        issued_at=NOW,
        family_expires_at=NOW.replace(year=2027),
    )
    stores.refresh_by_hash[token.token_hash] = token

    changed = await service.change_role(first.id, second.id, Role.ADVISOR)

    assert changed.role is Role.ADVISOR
    assert stores.refresh_by_hash[token.token_hash].revocation_reason is RevocationReason.ADMIN_REVOKED
