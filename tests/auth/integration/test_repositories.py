"""Auth repository tests against a real PostgreSQL server.

These tests exist because the interesting behavior is not in the Python: it is in
the unique constraint, the row lock, the conditional `UPDATE`, and the
`ON CONFLICT DO UPDATE`. A fake or an in-memory database would let every one of
those pass while being wrong in production.

Concurrency is exercised with two genuinely separate sessions running under
`asyncio.gather`, because a single session serializes its own statements and would
prove nothing about two parallel requests holding the same credential.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.auth.contracts import REFRESH_TOKEN_TTL_SECONDS
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import FixedClock
from src.auth.domain.errors import (
    RefreshTokenReplayError,
    TokenAlreadyConsumedError,
    TokenPurposeMismatchError,
)
from src.auth.domain.sessions import (
    OneTimeToken,
    RefreshToken,
    RevocationReason,
    TokenPurpose,
)
from src.auth.domain.values import (
    FamilyId,
    NormalizedEmail,
    PasswordHash,
    SessionId,
    TokenHash,
    UserId,
)
from src.auth.infrastructure.repositories import (
    AuthRepositories,
    AuthUnitOfWork,
    ConcurrentTokenUseError,
    EmailAlreadyRegisteredError,
    build_rate_limit_key,
    build_repositories,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
PASSWORD_HASH = PasswordHash("$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA")
OTHER_PASSWORD_HASH = PasswordHash("$argon2id$v=19$m=65536,t=3,p=4$b3RoZXJzYWx0$b3RoZXI")

# A limiter key is derived, never composed by hand in a test: doing it the wrong
# way here is how the wrong way reaches production.
RATE_LIMIT_PEPPER = "test-rate-limit-pepper"
LOGIN_IP_KEY = build_rate_limit_key("login", "198.51.100.7", pepper=RATE_LIMIT_PEPPER)
LOGIN_EMAIL_KEY = build_rate_limit_key("login", "victim@gmail.com", pepper=RATE_LIMIT_PEPPER)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


def make_user(
    *,
    email: str = "customer@gmail.com",
    role: Role = Role.CUSTOMER,
    state: AccountState = AccountState.ACTIVE,
    password_hash: PasswordHash = PASSWORD_HASH,
) -> User:
    return User(
        id=UserId(uuid.uuid4().hex),
        email=NormalizedEmail.parse(email),
        role=role,
        state=state,
        password_hash=password_hash,
        created_at=NOW,
    )


def make_refresh_token(
    user: User,
    *,
    token_hash: str | None = None,
    family_id: str | None = None,
    session_id: str | None = None,
    issued_at: datetime = NOW,
    family_expires_at: datetime | None = None,
) -> RefreshToken:
    return RefreshToken(
        token_hash=TokenHash(token_hash or uuid.uuid4().hex),
        session_id=SessionId(session_id or uuid.uuid4().hex),
        family_id=FamilyId(family_id or uuid.uuid4().hex),
        user_id=user.id,
        issued_at=issued_at,
        family_expires_at=family_expires_at or NOW + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
    )


def make_one_time_token(
    user: User,
    *,
    purpose: TokenPurpose = TokenPurpose.EMAIL_VERIFICATION,
    token_hash: str | None = None,
    issued_at: datetime = NOW,
    ttl_seconds: int = 3600,
) -> OneTimeToken:
    return OneTimeToken(
        token_hash=TokenHash(token_hash or uuid.uuid4().hex),
        purpose=purpose,
        user_id=user.id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One transaction, committed on clean exit exactly as `AuthUnitOfWork` does.

    Exposed separately from `repositories` so a test can issue raw SQL (for
    example a `DELETE` that exercises a foreign-key rule) in the same transaction
    instead of reaching into repository internals.
    """
    async with session_factory() as active, active.begin():
        yield active


@pytest_asyncio.fixture
async def repositories(session: AsyncSession) -> AuthRepositories:
    return build_repositories(session)


async def _persist_user(uow: AuthUnitOfWork, user: User) -> User:
    async with uow.transaction() as repos:
        await repos.users.add(user, now=NOW)
    return user


class TestUserPersistence:
    @pytest.mark.asyncio
    async def test_added_user_round_trips(self, repositories: AuthRepositories) -> None:
        user = make_user()
        await repositories.users.add(user, now=NOW)
        loaded = await repositories.users.get_by_id(user.id)
        assert loaded == user

    @pytest.mark.asyncio
    async def test_lookup_by_normalized_email(self, repositories: AuthRepositories) -> None:
        """The stored value is the normalized address the application looks up."""
        user = make_user(email="  Customer@Gmail.COM ")
        await repositories.users.add(user, now=NOW)
        loaded = await repositories.users.get_by_email(NormalizedEmail.parse("customer@gmail.com"))
        assert loaded is not None
        assert loaded.id == user.id

    @pytest.mark.asyncio
    async def test_missing_user_returns_none(self, repositories: AuthRepositories) -> None:
        assert await repositories.users.get_by_id(UserId(uuid.uuid4().hex)) is None
        assert await repositories.users.get_by_email(NormalizedEmail.parse("no@gmail.com")) is None

    @pytest.mark.asyncio
    async def test_duplicate_email_is_rejected_by_the_constraint(self, uow: AuthUnitOfWork) -> None:
        """The database decides, not a prior SELECT."""
        first = make_user(email="taken@gmail.com")
        await _persist_user(uow, first)
        second = make_user(email="taken@gmail.com")
        with pytest.raises(EmailAlreadyRegisteredError):
            async with uow.transaction() as repos:
                await repos.users.add(second, now=NOW)

    @pytest.mark.asyncio
    async def test_duplicate_email_error_does_not_disclose_the_address(self, uow: AuthUnitOfWork) -> None:
        await _persist_user(uow, make_user(email="private@gmail.com"))
        with pytest.raises(EmailAlreadyRegisteredError) as exc:
            async with uow.transaction() as repos:
                await repos.users.add(make_user(email="private@gmail.com"), now=NOW)
        assert "private@gmail.com" not in str(exc.value)

    @pytest.mark.asyncio
    async def test_duplicate_email_leaves_the_transaction_usable(self, uow: AuthUnitOfWork) -> None:
        """The savepoint is what allows an audit write after the rejection.

        Without it PostgreSQL aborts the whole transaction on the violation, and
        recording "registration rejected" would fail too.
        """
        await _persist_user(uow, make_user(email="dup@gmail.com"))
        async with uow.transaction() as repos:
            with pytest.raises(EmailAlreadyRegisteredError):
                await repos.users.add(make_user(email="dup@gmail.com"), now=NOW)
            await repos.security_events.append(event_type="registration_rejected", occurred_at=NOW)
        async with uow.transaction() as repos:
            events = await repos.security_events.list_recent()
        assert [event.event_type for event in events] == ["registration_rejected"]

    @pytest.mark.asyncio
    async def test_duplicate_email_is_case_insensitive(self, uow: AuthUnitOfWork) -> None:
        await _persist_user(uow, make_user(email="mixed@gmail.com"))
        with pytest.raises(EmailAlreadyRegisteredError):
            async with uow.transaction() as repos:
                await repos.users.add(make_user(email="MIXED@gmail.com"), now=NOW)

    @pytest.mark.asyncio
    async def test_save_persists_a_state_transition(self, repositories: AuthRepositories) -> None:
        user = make_user(state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        verified = user.verify_email()
        await repositories.users.save(verified, now=NOW + timedelta(minutes=1))
        loaded = await repositories.users.get_by_id(user.id)
        assert loaded is not None
        assert loaded.state is AccountState.ACTIVE

    @pytest.mark.asyncio
    async def test_save_persists_a_new_password_hash(self, repositories: AuthRepositories) -> None:
        user = make_user()
        await repositories.users.add(user, now=NOW)
        await repositories.users.save(user.change_password(OTHER_PASSWORD_HASH), now=NOW)
        loaded = await repositories.users.get_by_id(user.id)
        assert loaded is not None
        assert loaded.password_hash == OTHER_PASSWORD_HASH

    @pytest.mark.asyncio
    async def test_no_plaintext_column_exists(self, engine: AsyncEngine) -> None:
        """Only hashes are storable; there is no column a plaintext could go in."""
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'auth_users'")
            )
            columns = {row[0] for row in result.fetchall()}
        assert "password_hash" in columns
        assert not {"password", "plaintext_password", "secret"} & columns

    @pytest.mark.asyncio
    async def test_active_admin_count(self, repositories: AuthRepositories) -> None:
        await repositories.users.add(make_user(email="a1@gmail.com", role=Role.ADMIN), now=NOW)
        await repositories.users.add(
            make_user(email="a2@gmail.com", role=Role.ADMIN, state=AccountState.DISABLED), now=NOW
        )
        await repositories.users.add(make_user(email="c1@gmail.com"), now=NOW)
        assert await repositories.users.count_active_admins() == 1
        assert await repositories.users.lock_active_admin_count() == 1

    @pytest.mark.asyncio
    async def test_list_page_filters_orders_and_reports_last_activity(self, repositories: AuthRepositories) -> None:
        users = (
            User(
                id=UserId("order-a"),
                email=NormalizedEmail.parse("order-a@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW + timedelta(seconds=30),
            ),
            User(
                id=UserId("order-b"),
                email=NormalizedEmail.parse("order-b@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW + timedelta(seconds=20),
            ),
            User(
                id=UserId("order-c"),
                email=NormalizedEmail.parse("order-c@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW + timedelta(minutes=1),
            ),
            User(
                id=UserId("disabled"),
                email=NormalizedEmail.parse("disabled@example.com"),
                role=Role.ADVISOR,
                state=AccountState.DISABLED,
                password_hash=PASSWORD_HASH,
                created_at=NOW,
            ),
            User(
                id=UserId("underscore"),
                email=NormalizedEmail.parse("under_score@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW,
            ),
            User(
                id=UserId("underxscore"),
                email=NormalizedEmail.parse("underxscore@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW,
            ),
            User(
                id=UserId("backslash"),
                email=NormalizedEmail.parse(r"back\slash@example.com"),
                role=Role.ADVISOR,
                state=AccountState.ACTIVE,
                password_hash=PASSWORD_HASH,
                created_at=NOW,
            ),
        )
        for user in users:
            await repositories.users.add(user, now=NOW)

        first_activity = NOW + timedelta(minutes=5)
        latest_activity = NOW + timedelta(minutes=10)
        await repositories.security_events.append(
            event_type="staff_logged_in", occurred_at=first_activity, actor_user_id=users[0].id
        )
        await repositories.security_events.append(
            event_type="staff_logged_in", occurred_at=latest_activity, actor_user_id=users[0].id
        )

        first = await repositories.users.list_page(
            role=Role.ADVISOR, state=AccountState.ACTIVE, email_query=None, page=1, page_size=2
        )
        assert first.total == 6
        assert [item.id for item in first.items] == [users[2].id, users[0].id]
        assert first.items[1].last_activity_at == latest_activity

        second = await repositories.users.list_page(
            role=Role.ADVISOR, state=AccountState.ACTIVE, email_query=None, page=2, page_size=2
        )
        assert [item.id for item in second.items] == [users[1].id, users[6].id]

        state_filtered = await repositories.users.list_page(
            role=Role.ADVISOR,
            state=AccountState.DISABLED,
            email_query=None,
            page=1,
            page_size=20,
        )
        assert [item.id for item in state_filtered.items] == [users[3].id]

        underscore_filtered = await repositories.users.list_page(
            role=None, state=None, email_query="_", page=1, page_size=20
        )
        assert [item.id for item in underscore_filtered.items] == [users[4].id]

        backslash_filtered = await repositories.users.list_page(
            role=None, state=None, email_query="\\", page=1, page_size=20
        )
        assert [item.id for item in backslash_filtered.items] == [users[6].id]

        wildcard = await repositories.users.list_page(role=None, state=None, email_query="%", page=1, page_size=20)
        assert wildcard.total == 0


class TestTransactionBoundary:
    @pytest.mark.asyncio
    async def test_rollback_discards_every_write_in_the_flow(self, uow: AuthUnitOfWork) -> None:
        """A flow lands whole or not at all.

        The user insert and the event append are in one transaction; a failure
        after both must leave neither, or the audit log would describe an account
        that does not exist.
        """
        user = make_user(email="rollback@gmail.com")
        with pytest.raises(RuntimeError):
            async with uow.transaction() as repos:
                await repos.users.add(user, now=NOW)
                await repos.security_events.append(event_type="registered", occurred_at=NOW)
                raise RuntimeError("flow failed after writing")

        async with uow.transaction() as repos:
            assert await repos.users.get_by_id(user.id) is None
            assert await repos.security_events.list_recent() == []

    @pytest.mark.asyncio
    async def test_rollback_of_a_rotation_keeps_the_original_token_usable(self, uow: AuthUnitOfWork) -> None:
        """A failed refresh must not leave the caller's token revoked."""
        user = await _persist_user(uow, make_user(email="rot-rollback@gmail.com"))
        original = make_refresh_token(user)
        async with uow.transaction() as repos:
            await repos.refresh_tokens.add(original)

        with pytest.raises(RuntimeError):
            async with uow.transaction() as repos:
                current = await repos.refresh_tokens.get_for_rotation(original.token_hash)
                assert current is not None
                revoked, successor = current.rotate(NOW, TokenHash(uuid.uuid4().hex))
                await repos.refresh_tokens.rotate(revoked, successor)
                raise RuntimeError("mail delivery failed after rotation")

        async with uow.transaction() as repos:
            reloaded = await repos.refresh_tokens.get(original.token_hash)
        assert reloaded is not None
        assert not reloaded.is_revoked

    @pytest.mark.asyncio
    async def test_commit_persists_across_transactions(self, uow: AuthUnitOfWork) -> None:
        user = await _persist_user(uow, make_user(email="committed@gmail.com"))
        async with uow.transaction() as repos:
            assert await repos.users.get_by_id(user.id) is not None


class TestRefreshTokenFamilies:
    @pytest.mark.asyncio
    async def test_token_round_trips(self, repositories: AuthRepositories) -> None:
        user = make_user(email="rt@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)
        assert await repositories.refresh_tokens.get(token.token_hash) == token

    @pytest.mark.asyncio
    async def test_rotation_revokes_current_and_appends_one_successor(self, repositories: AuthRepositories) -> None:
        user = make_user(email="rt-rotate@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)

        revoked, successor = token.rotate(NOW + timedelta(minutes=5), TokenHash(uuid.uuid4().hex))
        await repositories.refresh_tokens.rotate(revoked, successor)

        family = await repositories.refresh_tokens.list_family(token.family_id)
        assert len(family) == 2
        stored_original, stored_successor = family
        assert stored_original.revocation_reason is RevocationReason.ROTATED
        assert not stored_successor.is_revoked

    @pytest.mark.asyncio
    async def test_rotation_does_not_extend_the_absolute_expiry(self, repositories: AuthRepositories) -> None:
        """The successor inherits the family deadline instead of recomputing it."""
        user = make_user(email="rt-expiry@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)

        revoked, successor = token.rotate(NOW + timedelta(days=10), TokenHash(uuid.uuid4().hex))
        await repositories.refresh_tokens.rotate(revoked, successor)

        stored = await repositories.refresh_tokens.get(successor.token_hash)
        assert stored is not None
        assert stored.family_expires_at == token.family_expires_at

    @pytest.mark.asyncio
    async def test_replay_of_a_rotated_token_is_detected(self, repositories: AuthRepositories) -> None:
        """A token presented after rotation reads as replay, not plain revocation."""
        user = make_user(email="rt-replay@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)
        revoked, successor = token.rotate(NOW, TokenHash(uuid.uuid4().hex))
        await repositories.refresh_tokens.rotate(revoked, successor)

        replayed = await repositories.refresh_tokens.get_for_rotation(token.token_hash)
        assert replayed is not None
        with pytest.raises(RefreshTokenReplayError):
            replayed.assert_usable(NOW + timedelta(minutes=1))

    @pytest.mark.asyncio
    async def test_replay_evidence_survives_a_later_family_revocation(self, repositories: AuthRepositories) -> None:
        """A logout sweep must not overwrite the `rotated` reason.

        That reason is the only record distinguishing a leaked-and-replayed token
        from an ordinary logout.
        """
        user = make_user(email="rt-evidence@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)
        revoked, successor = token.rotate(NOW, TokenHash(uuid.uuid4().hex))
        await repositories.refresh_tokens.rotate(revoked, successor)

        await repositories.refresh_tokens.revoke_family(
            token.family_id, now=NOW + timedelta(minutes=1), reason=RevocationReason.LOGOUT
        )
        stored = await repositories.refresh_tokens.get(token.token_hash)
        assert stored is not None
        assert stored.revocation_reason is RevocationReason.ROTATED

    @pytest.mark.asyncio
    async def test_replay_revokes_one_family_only(self, repositories: AuthRepositories) -> None:
        """Killing every session on one suspicious token would be a DoS lever."""
        user = make_user(email="rt-families@gmail.com")
        await repositories.users.add(user, now=NOW)
        compromised = make_refresh_token(user)
        other_device = make_refresh_token(user)
        await repositories.refresh_tokens.add(compromised)
        await repositories.refresh_tokens.add(other_device)

        await repositories.refresh_tokens.revoke_family(
            compromised.family_id, now=NOW, reason=RevocationReason.REPLAY_DETECTED
        )

        survivor = await repositories.refresh_tokens.get(other_device.token_hash)
        assert survivor is not None
        assert not survivor.is_revoked

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_covers_every_family(self, repositories: AuthRepositories) -> None:
        user = make_user(email="rt-logout-all@gmail.com")
        await repositories.users.add(user, now=NOW)
        tokens = [make_refresh_token(user) for _ in range(3)]
        for token in tokens:
            await repositories.refresh_tokens.add(token)

        revoked = await repositories.refresh_tokens.revoke_all_for_user(
            user.id, now=NOW, reason=RevocationReason.LOGOUT_ALL
        )
        assert revoked == 3
        for token in tokens:
            stored = await repositories.refresh_tokens.get(token.token_hash)
            assert stored is not None and stored.is_revoked

    @pytest.mark.asyncio
    async def test_revoke_all_ignores_another_users_sessions(self, repositories: AuthRepositories) -> None:
        owner = make_user(email="rt-owner@gmail.com")
        bystander = make_user(email="rt-bystander@gmail.com")
        await repositories.users.add(owner, now=NOW)
        await repositories.users.add(bystander, now=NOW)
        owner_token = make_refresh_token(owner)
        bystander_token = make_refresh_token(bystander)
        await repositories.refresh_tokens.add(owner_token)
        await repositories.refresh_tokens.add(bystander_token)

        await repositories.refresh_tokens.revoke_all_for_user(owner.id, now=NOW, reason=RevocationReason.LOGOUT_ALL)
        untouched = await repositories.refresh_tokens.get(bystander_token.token_hash)
        assert untouched is not None
        assert not untouched.is_revoked

    @pytest.mark.asyncio
    async def test_rotating_an_already_rotated_token_is_refused(self, repositories: AuthRepositories) -> None:
        """The conditional UPDATE, not a prior read, is what refuses this."""
        user = make_user(email="rt-double@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)
        revoked, successor = token.rotate(NOW, TokenHash(uuid.uuid4().hex))
        await repositories.refresh_tokens.rotate(revoked, successor)

        with pytest.raises(ConcurrentTokenUseError):
            await repositories.refresh_tokens.rotate(revoked, make_refresh_token(user, family_id=str(token.family_id)))

    @pytest.mark.asyncio
    async def test_expired_families_are_deletable(self, repositories: AuthRepositories) -> None:
        user = make_user(email="rt-sweep@gmail.com")
        await repositories.users.add(user, now=NOW)
        expired = make_refresh_token(user, family_expires_at=NOW - timedelta(days=1))
        live = make_refresh_token(user)
        await repositories.refresh_tokens.add(expired)
        await repositories.refresh_tokens.add(live)

        deleted = await repositories.refresh_tokens.delete_expired(now=NOW)
        assert deleted == 1
        assert await repositories.refresh_tokens.get(expired.token_hash) is None
        assert await repositories.refresh_tokens.get(live.token_hash) is not None

    @pytest.mark.asyncio
    async def test_deleting_a_user_removes_their_sessions(
        self, repositories: AuthRepositories, session: AsyncSession
    ) -> None:
        """`ON DELETE CASCADE`: a removed account leaves no live credential."""
        user = make_user(email="rt-cascade@gmail.com")
        await repositories.users.add(user, now=NOW)
        token = make_refresh_token(user)
        await repositories.refresh_tokens.add(token)

        await session.execute(text("DELETE FROM auth_users WHERE id = :id"), {"id": str(user.id)})
        assert await repositories.refresh_tokens.get(token.token_hash) is None


class TestFirstAdminBootstrap:
    """The empty-table first-Admin race is decided by PostgreSQL."""

    @pytest.mark.asyncio
    async def test_concurrent_first_admin_claim_creates_exactly_one(
        self, session_factory: async_sessionmaker[AsyncSession], uow: AuthUnitOfWork
    ) -> None:
        first = make_user(email="first-admin@gmail.com", role=Role.ADMIN)
        second = make_user(email="second-admin@gmail.com", role=Role.ADMIN)

        outcomes = await asyncio.gather(
            _claim_first_admin_in_new_session(session_factory, first),
            _claim_first_admin_in_new_session(session_factory, second),
        )

        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1
        async with uow.transaction() as repos:
            assert await repos.users.count_active_admins() == 1


async def _claim_first_admin_in_new_session(session_factory: async_sessionmaker[AsyncSession], user: User) -> bool:
    """Attempt first-Admin bootstrap in an independent database transaction."""
    async with session_factory() as session, session.begin():
        return await build_repositories(session).users.claim_first_admin(user, now=NOW)


class TestConcurrentRefreshRotation:
    """Two parallel refreshes with the same token must produce one successor.

    This is the case a Python-side `if not token.is_revoked` check cannot handle:
    both requests read the token before either writes. The row lock is what makes
    the second request see the first request's revocation.
    """

    @pytest.mark.asyncio
    async def test_concurrent_refresh_produces_exactly_one_successor(
        self, session_factory: async_sessionmaker[AsyncSession], uow: AuthUnitOfWork
    ) -> None:
        user = await _persist_user(uow, make_user(email="concurrent@gmail.com"))
        token = make_refresh_token(user)
        async with uow.transaction() as repos:
            await repos.refresh_tokens.add(token)

        outcomes = await asyncio.gather(
            _rotate_in_new_session(session_factory, token.token_hash),
            _rotate_in_new_session(session_factory, token.token_hash),
            return_exceptions=True,
        )
        successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]

        assert len(successes) == 1
        assert len(failures) == 1
        # Either classification is correct: the loser either observes the rotated
        # token (replay) or loses the conditional UPDATE (concurrent use).
        assert isinstance(failures[0], RefreshTokenReplayError | ConcurrentTokenUseError)

        async with uow.transaction() as repos:
            family = await repos.refresh_tokens.list_family(token.family_id)
        live = [entry for entry in family if not entry.is_revoked]
        assert len(live) == 1
        assert len(family) == 2

    @pytest.mark.asyncio
    async def test_concurrent_refresh_keeps_the_family_deadline(
        self, session_factory: async_sessionmaker[AsyncSession], uow: AuthUnitOfWork
    ) -> None:
        user = await _persist_user(uow, make_user(email="concurrent2@gmail.com"))
        token = make_refresh_token(user)
        async with uow.transaction() as repos:
            await repos.refresh_tokens.add(token)

        await asyncio.gather(
            _rotate_in_new_session(session_factory, token.token_hash),
            _rotate_in_new_session(session_factory, token.token_hash),
            return_exceptions=True,
        )
        async with uow.transaction() as repos:
            family = await repos.refresh_tokens.list_family(token.family_id)
        assert {entry.family_expires_at for entry in family} == {token.family_expires_at}


async def _rotate_in_new_session(session_factory: async_sessionmaker[AsyncSession], token_hash: TokenHash) -> TokenHash:
    """Perform one full rotation in its own transaction, as a request would."""
    async with session_factory() as session, session.begin():
        repos = build_repositories(session)
        current = await repos.refresh_tokens.get_for_rotation(token_hash)
        if current is None:
            raise AssertionError("refresh token disappeared")
        successor_hash = TokenHash(uuid.uuid4().hex)
        revoked, successor = current.rotate(NOW + timedelta(minutes=1), successor_hash)
        await repos.refresh_tokens.rotate(revoked, successor)
        return successor_hash


class TestOneTimeTokens:
    @pytest.mark.asyncio
    async def test_token_round_trips(self, repositories: AuthRepositories) -> None:
        user = make_user(email="ott@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        token = make_one_time_token(user)
        await repositories.one_time_tokens.issue(token, now=NOW)
        assert await repositories.one_time_tokens.get(token.token_hash) == token

    @pytest.mark.asyncio
    async def test_issuing_supersedes_the_previous_token(self, repositories: AuthRepositories) -> None:
        """Latest-token-wins: a resend must not leave two usable credentials."""
        user = make_user(email="ott-resend@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        first = make_one_time_token(user)
        await repositories.one_time_tokens.issue(first, now=NOW)
        second = make_one_time_token(user, issued_at=NOW + timedelta(minutes=1))
        superseded = await repositories.one_time_tokens.issue(second, now=NOW + timedelta(minutes=1))

        assert superseded == 1
        stored_first = await repositories.one_time_tokens.get(first.token_hash)
        assert stored_first is not None and stored_first.is_superseded
        with pytest.raises(TokenAlreadyConsumedError):
            stored_first.assert_usable(
                NOW + timedelta(minutes=2),
                purpose=TokenPurpose.EMAIL_VERIFICATION,
                user_id=user.id,
            )

    @pytest.mark.asyncio
    async def test_cross_purpose_issue_does_not_supersede(self, repositories: AuthRepositories) -> None:
        """Requesting a reset must not cancel a pending verification."""
        user = make_user(email="ott-cross@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        verification = make_one_time_token(user, purpose=TokenPurpose.EMAIL_VERIFICATION)
        await repositories.one_time_tokens.issue(verification, now=NOW)

        superseded = await repositories.one_time_tokens.issue(
            make_one_time_token(user, purpose=TokenPurpose.PASSWORD_RESET), now=NOW
        )
        assert superseded == 0
        stored = await repositories.one_time_tokens.get(verification.token_hash)
        assert stored is not None and not stored.is_superseded

    @pytest.mark.asyncio
    async def test_cross_purpose_consumption_is_refused(self, repositories: AuthRepositories) -> None:
        """A verification token cannot be spent as a password reset."""
        user = make_user(email="ott-cross2@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        token = make_one_time_token(user, purpose=TokenPurpose.EMAIL_VERIFICATION)
        await repositories.one_time_tokens.issue(token, now=NOW)

        stored = await repositories.one_time_tokens.get_for_consumption(token.token_hash)
        assert stored is not None
        with pytest.raises(TokenPurposeMismatchError):
            stored.consume(NOW, purpose=TokenPurpose.PASSWORD_RESET, user_id=user.id)

    @pytest.mark.asyncio
    async def test_cross_purpose_supersede_scope_is_per_user(self, repositories: AuthRepositories) -> None:
        """One user's resend must not invalidate another user's token."""
        first = make_user(email="ott-u1@gmail.com", state=AccountState.PENDING_VERIFICATION)
        second = make_user(email="ott-u2@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(first, now=NOW)
        await repositories.users.add(second, now=NOW)
        other_token = make_one_time_token(second)
        await repositories.one_time_tokens.issue(make_one_time_token(first), now=NOW)
        await repositories.one_time_tokens.issue(other_token, now=NOW)
        await repositories.one_time_tokens.issue(make_one_time_token(first), now=NOW)

        stored = await repositories.one_time_tokens.get(other_token.token_hash)
        assert stored is not None and not stored.is_superseded

    @pytest.mark.asyncio
    async def test_consumption_is_single_use(self, repositories: AuthRepositories) -> None:
        user = make_user(email="ott-single@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        token = make_one_time_token(user)
        await repositories.one_time_tokens.issue(token, now=NOW)

        consumed = token.consume(NOW, purpose=token.purpose, user_id=user.id)
        await repositories.one_time_tokens.mark_consumed(consumed)
        with pytest.raises(ConcurrentTokenUseError):
            await repositories.one_time_tokens.mark_consumed(consumed)

    @pytest.mark.asyncio
    async def test_consumed_token_is_not_marked_superseded_later(self, repositories: AuthRepositories) -> None:
        """A spent credential keeps its audit trail when a new token is issued."""
        user = make_user(email="ott-audit@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        token = make_one_time_token(user)
        await repositories.one_time_tokens.issue(token, now=NOW)
        await repositories.one_time_tokens.mark_consumed(token.consume(NOW, purpose=token.purpose, user_id=user.id))

        superseded = await repositories.one_time_tokens.issue(
            make_one_time_token(user, issued_at=NOW + timedelta(minutes=1)),
            now=NOW + timedelta(minutes=1),
        )
        assert superseded == 0
        stored = await repositories.one_time_tokens.get(token.token_hash)
        assert stored is not None
        assert stored.is_consumed and not stored.is_superseded

    @pytest.mark.asyncio
    async def test_expired_tokens_are_deletable(self, repositories: AuthRepositories) -> None:
        user = make_user(email="ott-sweep@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        expired = make_one_time_token(user, issued_at=NOW - timedelta(days=2), ttl_seconds=3600)
        live = make_one_time_token(user, purpose=TokenPurpose.PASSWORD_RESET)
        await repositories.one_time_tokens.issue(expired, now=NOW)
        await repositories.one_time_tokens.issue(live, now=NOW)

        deleted = await repositories.one_time_tokens.delete_expired(now=NOW)
        assert deleted == 1
        assert await repositories.one_time_tokens.get(expired.token_hash) is None
        assert await repositories.one_time_tokens.get(live.token_hash) is not None

    @pytest.mark.asyncio
    async def test_concurrent_consumption_succeeds_once(
        self, session_factory: async_sessionmaker[AsyncSession], uow: AuthUnitOfWork
    ) -> None:
        """Two requests submitting the same link produce one success."""
        user = await _persist_user(uow, make_user(email="ott-race@gmail.com", state=AccountState.PENDING_VERIFICATION))
        token = make_one_time_token(user)
        async with uow.transaction() as repos:
            await repos.one_time_tokens.issue(token, now=NOW)

        outcomes = await asyncio.gather(
            _consume_in_new_session(session_factory, token.token_hash, user.id),
            _consume_in_new_session(session_factory, token.token_hash, user.id),
            return_exceptions=True,
        )
        successes = [o for o in outcomes if not isinstance(o, BaseException)]
        failures = [o for o in outcomes if isinstance(o, BaseException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], TokenAlreadyConsumedError | ConcurrentTokenUseError)


async def _consume_in_new_session(
    session_factory: async_sessionmaker[AsyncSession],
    token_hash: TokenHash,
    user_id: UserId,
) -> None:
    async with session_factory() as session, session.begin():
        repos = build_repositories(session)
        stored = await repos.one_time_tokens.get_for_consumption(token_hash)
        if stored is None:
            raise AssertionError("one-time token disappeared")
        consumed = stored.consume(NOW, purpose=stored.purpose, user_id=user_id)
        await repos.one_time_tokens.mark_consumed(consumed)


class TestRateLimitCounters:
    @pytest.mark.asyncio
    async def test_first_attempt_creates_the_window(self, repositories: AuthRepositories) -> None:
        window = await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        assert window.attempts == 1

    @pytest.mark.asyncio
    async def test_repeated_attempts_increment_in_the_database(self, repositories: AuthRepositories) -> None:
        """`ON CONFLICT DO UPDATE`: a read-then-write would undercount."""
        for expected in (1, 2, 3):
            window = await repositories.rate_limits.register_attempt(
                LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
            )
            assert window.attempts == expected

    @pytest.mark.asyncio
    async def test_windows_are_counted_separately(self, repositories: AuthRepositories) -> None:
        await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        later = await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY,
            window_start=NOW + timedelta(minutes=15),
            expires_at=NOW + timedelta(minutes=30),
        )
        assert later.attempts == 1
        assert await repositories.rate_limits.attempts_in_window(LOGIN_IP_KEY, window_start=NOW) == 1

    @pytest.mark.asyncio
    async def test_keys_are_counted_separately(self, repositories: AuthRepositories) -> None:
        await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        other = await repositories.rate_limits.register_attempt(
            LOGIN_EMAIL_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        assert other.attempts == 1

    @pytest.mark.asyncio
    async def test_reset_clears_a_key(self, repositories: AuthRepositories) -> None:
        await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        await repositories.rate_limits.reset(LOGIN_IP_KEY)
        assert await repositories.rate_limits.attempts_in_window(LOGIN_IP_KEY, window_start=NOW) == 0

    @pytest.mark.asyncio
    async def test_expired_windows_are_deletable(self, repositories: AuthRepositories) -> None:
        await repositories.rate_limits.register_attempt(
            LOGIN_IP_KEY,
            window_start=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(hours=1),
        )
        await repositories.rate_limits.register_attempt(
            LOGIN_EMAIL_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
        )
        assert await repositories.rate_limits.delete_expired(now=NOW) == 1

    @pytest.mark.asyncio
    async def test_concurrent_attempts_are_not_lost(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Parallel failed logins must all be counted, or the limiter is bypassable."""

        async def attempt() -> int:
            async with session_factory() as session, session.begin():
                window = await build_repositories(session).rate_limits.register_attempt(
                    LOGIN_IP_KEY, window_start=NOW, expires_at=NOW + timedelta(minutes=15)
                )
                return window.attempts

        await asyncio.gather(*(attempt() for _ in range(5)))
        async with session_factory() as session, session.begin():
            total = await build_repositories(session).rate_limits.attempts_in_window(LOGIN_IP_KEY, window_start=NOW)
        assert total == 5


class TestRateLimitKeysAreNotAnAccountInventory:
    """A limiter table must not become a searchable list of accounts.

    The counters outlive the attempts they describe and are not deleted with an
    account, so a raw email or token stored here would leak long after the flow
    that created it.
    """

    def test_key_contains_no_raw_subject(self) -> None:
        key = build_rate_limit_key("login", "victim@gmail.com", pepper=RATE_LIMIT_PEPPER)
        assert "victim@gmail.com" not in key
        assert "victim" not in key
        assert key.startswith("login:")

    def test_key_is_stable_for_the_same_subject(self) -> None:
        """A limiter that produced a fresh key per call would never count twice."""
        first = build_rate_limit_key("login", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        second = build_rate_limit_key("login", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        assert first == second

    def test_different_subjects_get_different_keys(self) -> None:
        first = build_rate_limit_key("login", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        second = build_rate_limit_key("login", "b@gmail.com", pepper=RATE_LIMIT_PEPPER)
        assert first != second

    def test_same_subject_in_different_scopes_gets_different_keys(self) -> None:
        """Scope separation must be real, not just a prefix on a shared digest."""
        login = build_rate_limit_key("login", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        reset = build_rate_limit_key("reset", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        assert login.split(":", 1)[1] != reset.split(":", 1)[1]

    def test_pepper_changes_the_digest(self) -> None:
        """Without the server-side pepper a leaked table is dictionary-searchable."""
        first = build_rate_limit_key("login", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)
        second = build_rate_limit_key("login", "a@gmail.com", pepper="a-different-pepper")
        assert first != second

    @pytest.mark.asyncio
    async def test_raw_email_key_is_refused(self, repositories: AuthRepositories) -> None:
        """The repository rejects an unhashed key rather than trusting callers."""
        with pytest.raises(ValueError, match="hex digest"):
            await repositories.rate_limits.register_attempt(
                "login:victim@gmail.com", window_start=NOW, expires_at=NOW + timedelta(minutes=15)
            )

    @pytest.mark.asyncio
    async def test_rejection_does_not_echo_the_subject(self, repositories: AuthRepositories) -> None:
        with pytest.raises(ValueError) as exc:
            await repositories.rate_limits.register_attempt(
                "login:victim@gmail.com", window_start=NOW, expires_at=NOW + timedelta(minutes=15)
            )
        assert "victim@gmail.com" not in str(exc.value)

    @pytest.mark.asyncio
    async def test_empty_key_is_refused(self, repositories: AuthRepositories) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            await repositories.rate_limits.register_attempt(
                "", window_start=NOW, expires_at=NOW + timedelta(minutes=15)
            )

    @pytest.mark.asyncio
    async def test_reads_and_resets_also_validate_the_key(self, repositories: AuthRepositories) -> None:
        """Every entry point validates: one lax method is all an attacker needs."""
        with pytest.raises(ValueError, match="hex digest"):
            await repositories.rate_limits.attempts_in_window("login:victim@gmail.com", window_start=NOW)
        with pytest.raises(ValueError, match="hex digest"):
            await repositories.rate_limits.reset("login:victim@gmail.com")

    @pytest.mark.asyncio
    async def test_stored_keys_hold_no_address(self, repositories: AuthRepositories, session: AsyncSession) -> None:
        """Check the stored rows, not just the builder's return value."""
        key = build_rate_limit_key("login", "victim@gmail.com", pepper=RATE_LIMIT_PEPPER)
        await repositories.rate_limits.register_attempt(key, window_start=NOW, expires_at=NOW + timedelta(minutes=15))
        result = await session.execute(text("SELECT key FROM auth_rate_limit_counters"))
        stored = [row[0] for row in result.fetchall()]
        assert stored == [key]
        assert all("@" not in entry for entry in stored)

    def test_scope_with_a_separator_is_refused(self) -> None:
        """A ':' in the scope would make the key shape ambiguous."""
        with pytest.raises(ValueError, match="scope"):
            build_rate_limit_key("login:ip", "a@gmail.com", pepper=RATE_LIMIT_PEPPER)

    def test_missing_pepper_is_refused(self) -> None:
        with pytest.raises(ValueError, match="pepper"):
            build_rate_limit_key("login", "a@gmail.com", pepper="")


class TestSecurityEvents:
    @pytest.mark.asyncio
    async def test_event_round_trips_with_payload(self, repositories: AuthRepositories) -> None:
        user = make_user(email="ev@gmail.com")
        await repositories.users.add(user, now=NOW)
        await repositories.security_events.append(
            event_type="login_succeeded",
            occurred_at=NOW,
            actor_user_id=user.id,
            correlation_id="req-1",
            payload={"role": "customer"},
        )
        events = await repositories.security_events.list_recent()
        assert len(events) == 1
        assert events[0].event_type == "login_succeeded"
        assert events[0].payload == {"role": "customer"}

    @pytest.mark.asyncio
    async def test_event_without_an_actor_is_allowed(self, repositories: AuthRepositories) -> None:
        """A failed login for an unknown address has no actor to record."""
        await repositories.security_events.append(event_type="login_failed_unknown_account", occurred_at=NOW)
        events = await repositories.security_events.list_recent()
        assert events[0].actor_user_id is None

    @pytest.mark.asyncio
    async def test_deleting_a_user_keeps_the_event_history(
        self, repositories: AuthRepositories, session: AsyncSession
    ) -> None:
        """`ON DELETE SET NULL`: removing an account must not erase the audit trail."""
        user = make_user(email="ev-deleted@gmail.com")
        await repositories.users.add(user, now=NOW)
        await repositories.security_events.append(event_type="account_disabled", occurred_at=NOW, actor_user_id=user.id)
        await session.execute(text("DELETE FROM auth_users WHERE id = :id"), {"id": str(user.id)})
        events = await repositories.security_events.list_recent()
        assert len(events) == 1
        assert events[0].actor_user_id is None

    @pytest.mark.asyncio
    async def test_recent_events_are_newest_first(self, repositories: AuthRepositories) -> None:
        for index in range(3):
            await repositories.security_events.append(
                event_type=f"event_{index}", occurred_at=NOW + timedelta(seconds=index)
            )
        events = await repositories.security_events.list_recent(limit=2)
        assert [event.event_type for event in events] == ["event_2", "event_1"]

    @pytest.mark.asyncio
    async def test_empty_event_type_is_rejected(self, repositories: AuthRepositories) -> None:
        with pytest.raises(ValueError, match="event type"):
            await repositories.security_events.append(event_type="", occurred_at=NOW)


class TestTimezoneHandling:
    @pytest.mark.asyncio
    async def test_stored_timestamps_return_as_utc(self, repositories: AuthRepositories) -> None:
        """Every Auth instant is timezone-aware UTC on the way back out."""
        user = make_user(email="tz@gmail.com")
        await repositories.users.add(user, now=NOW)
        loaded = await repositories.users.get_by_id(user.id)
        assert loaded is not None
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at == NOW

    @pytest.mark.asyncio
    async def test_expiry_boundary_survives_the_round_trip(
        self, repositories: AuthRepositories, clock: FixedClock
    ) -> None:
        """Microsecond precision must not be lost, or expiry tests mean nothing."""
        user = make_user(email="tz-expiry@gmail.com", state=AccountState.PENDING_VERIFICATION)
        await repositories.users.add(user, now=NOW)
        token = make_one_time_token(user, issued_at=NOW, ttl_seconds=3600)
        await repositories.one_time_tokens.issue(token, now=NOW)
        stored = await repositories.one_time_tokens.get(token.token_hash)
        assert stored is not None
        clock.advance(3600)
        with pytest.raises(Exception, match="expired"):
            stored.assert_usable(clock.now(), purpose=token.purpose, user_id=user.id)
