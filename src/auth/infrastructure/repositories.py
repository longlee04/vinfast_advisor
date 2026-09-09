"""SQLAlchemy async repositories for the Auth schema.

Two rules shape every method here:

* **No repository commits.** Transaction boundaries belong to the caller
  (`AuthUnitOfWork`), because a single Auth flow spans several repositories —
  rotating a refresh token also writes a security event, and consuming a reset
  token also updates the user. If each repository committed on its own, a failure
  halfway through would leave the database in a state no flow can produce.
* **Concurrency is decided by the database, not by application code.** Refresh
  rotation and one-time-token consumption are both "check then write" against a
  credential an attacker can submit twice in parallel. A Python-side check would
  let two concurrent requests both pass it, so each is expressed as either a
  `SELECT ... FOR UPDATE` row lock or a conditional `UPDATE` whose row count is
  the verdict.

Rows are translated to domain objects at the boundary, so no domain module
imports SQLAlchemy (`AGENTS.md:27-28`).
"""

import hashlib
import hmac
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, Result, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth.application.contracts import UserPage, UserSummary
from src.auth.domain.accounts import AccountState, User, UserProfile
from src.auth.domain.authorization import Role
from src.auth.domain.clock import ensure_utc
from src.auth.domain.errors import AuthDomainError, ConcurrentTokenUseError
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
from src.auth.infrastructure.models import (
    BootstrapAdminClaimRow,
    OneTimeTokenRow,
    RateLimitCounterRow,
    RefreshTokenRow,
    SecurityEventRow,
    UserProfileRow,
    UserRow,
)

# Any writable field on a rate-limit counter is derived, so a conflicting insert
# can be resolved in the database instead of round-tripping a read.
_ATTEMPT_INCREMENT: Final[int] = 1


def _rowcount(result: Result[Any]) -> int:
    """Return the affected row count of a DML statement.

    `AsyncSession.execute` is typed as returning `Result`, but an UPDATE/DELETE
    always yields a `CursorResult`, which is where `rowcount` lives. The cast
    states that narrowing explicitly instead of suppressing the type error — and
    the row count is not incidental here: it is the verdict of every conditional
    write in this module.
    """
    return int(cast(CursorResult[Any], result).rowcount)


class EmailAlreadyRegisteredError(AuthDomainError):
    """The normalized email is already present.

    Raised from the unique-constraint violation rather than from a prior SELECT:
    two concurrent registrations both pass a pre-check, and only the constraint
    is authoritative.
    """

    code = "email_already_registered"


def _to_user(row: UserRow) -> User:
    return User(
        id=UserId(row.id),
        email=NormalizedEmail(row.email),
        role=Role(row.role),
        state=AccountState(row.state),
        password_hash=PasswordHash(row.password_hash),
        created_at=ensure_utc(row.created_at),
        temporary_password_expires_at=(
            ensure_utc(row.temporary_password_expires_at) if row.temporary_password_expires_at is not None else None
        ),
    )


def _to_refresh_token(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        token_hash=TokenHash(row.token_hash),
        session_id=SessionId(row.session_id),
        family_id=FamilyId(row.family_id),
        user_id=UserId(row.user_id),
        issued_at=ensure_utc(row.issued_at),
        family_expires_at=ensure_utc(row.family_expires_at),
        revoked_at=ensure_utc(row.revoked_at) if row.revoked_at else None,
        revocation_reason=(RevocationReason(row.revocation_reason) if row.revocation_reason else None),
    )


def _to_one_time_token(row: OneTimeTokenRow) -> OneTimeToken:
    return OneTimeToken(
        token_hash=TokenHash(row.token_hash),
        purpose=TokenPurpose(row.purpose),
        user_id=UserId(row.user_id),
        issued_at=ensure_utc(row.issued_at),
        expires_at=ensure_utc(row.expires_at),
        consumed_at=ensure_utc(row.consumed_at) if row.consumed_at else None,
        superseded_at=ensure_utc(row.superseded_at) if row.superseded_at else None,
    )


class UserRepository:
    """Reads and writes Auth accounts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User, *, now: datetime) -> None:
        """Insert a new account, translating the unique-email violation.

        A `SAVEPOINT` wraps the insert: on PostgreSQL a constraint violation
        aborts the whole transaction, so without a nested block the caller could
        not continue (for example to record a security event about the rejected
        registration).
        """
        moment = ensure_utc(now)
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    insert(UserRow).values(
                        id=str(user.id),
                        email=str(user.email),
                        role=user.role.value,
                        state=user.state.value,
                        password_hash=str(user.password_hash),
                        temporary_password_expires_at=user.temporary_password_expires_at,
                        created_at=ensure_utc(user.created_at),
                        updated_at=moment,
                    )
                )
        except IntegrityError as error:
            if _violates(error, "uq_auth_users_email"):
                # The address is not echoed: this error can reach a log line, and
                # the address is the account identity.
                raise EmailAlreadyRegisteredError("email is already registered") from None
            raise

    async def claim_first_admin(self, user: User, *, now: datetime) -> bool:
        """Atomically insert the sole bootstrap Admin without an advisory lock.

        A singleton claim row turns the empty-table race into a unique-key race.
        PostgreSQL arbitrates `ON CONFLICT DO NOTHING` across transactions, so only
        the winner can continue to insert the account and bind the claim within the
        same unit of work.
        """
        claim = (
            pg_insert(BootstrapAdminClaimRow)
            .values(key="first_admin")
            .on_conflict_do_nothing(index_elements=[BootstrapAdminClaimRow.key])
            .returning(BootstrapAdminClaimRow.key)
        )
        result = await self._session.execute(claim)
        if result.scalar_one_or_none() is None:
            return False
        await self.add(user, now=now)
        await self._session.execute(
            update(BootstrapAdminClaimRow)
            .where(BootstrapAdminClaimRow.key == "first_admin")
            .values(user_id=str(user.id))
        )
        return True

    async def get_by_id(self, user_id: UserId) -> User | None:
        row = await self._session.get(UserRow, str(user_id))
        return _to_user(row) if row else None

    async def get_by_email(self, email: NormalizedEmail) -> User | None:
        """Look up by the normalized address, matching the unique constraint."""
        result = await self._session.execute(select(UserRow).where(UserRow.email == str(email)))
        row = result.scalar_one_or_none()
        return _to_user(row) if row else None

    async def get_for_update(self, user_id: UserId) -> User | None:
        """Read an account with its row locked for the rest of the transaction.

        Used by flows that decide based on the account's state and then change it
        (password change, verification, disable) so two concurrent requests cannot
        both observe the pre-change state.
        """
        result = await self._session.execute(select(UserRow).where(UserRow.id == str(user_id)).with_for_update())
        row = result.scalar_one_or_none()
        return _to_user(row) if row else None

    async def list_page(
        self,
        *,
        role: Role | None,
        state: AccountState | None,
        email_query: str | None,
        page: int,
        page_size: int,
    ) -> UserPage:
        """Return one page of accounts with their latest security-event time."""
        last_activity = (
            select(func.max(SecurityEventRow.occurred_at))
            .where(SecurityEventRow.actor_user_id == UserRow.id)
            .correlate(UserRow)
            .scalar_subquery()
        )
        conditions = []
        if role is not None:
            conditions.append(UserRow.role == role.value)
        if state is not None:
            conditions.append(UserRow.state == state.value)
        if email_query:
            escaped = email_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(UserRow.email.ilike(f"%{escaped}%", escape="\\"))

        total = await self._session.scalar(select(func.count()).select_from(UserRow).where(*conditions))
        rows = await self._session.execute(
            select(
                UserRow.id,
                UserRow.email,
                UserRow.role,
                UserRow.state,
                UserRow.created_at,
                last_activity.label("last_activity_at"),
            )
            .where(*conditions)
            .order_by(UserRow.created_at.desc(), UserRow.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return UserPage(
            items=tuple(
                UserSummary(
                    id=UserId(row.id),
                    email=NormalizedEmail.parse(row.email),
                    role=Role(row.role),
                    state=AccountState(row.state),
                    created_at=ensure_utc(row.created_at),
                    last_activity_at=(ensure_utc(row.last_activity_at) if row.last_activity_at is not None else None),
                )
                for row in rows
            ),
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    async def save(self, user: User, *, now: datetime) -> None:
        """Persist a transitioned account. Identity and creation time are fixed."""
        result = await self._session.execute(
            update(UserRow)
            .where(UserRow.id == str(user.id))
            .values(
                email=str(user.email),
                role=user.role.value,
                state=user.state.value,
                password_hash=str(user.password_hash),
                temporary_password_expires_at=user.temporary_password_expires_at,
                updated_at=ensure_utc(now),
            )
        )
        if _rowcount(result) != 1:
            raise ConcurrentTokenUseError("account row was removed during the operation")

    async def count_active_admins(self) -> int:
        """Count active admins, for last-active-admin protection."""
        result = await self._session.execute(
            select(func.count())
            .select_from(UserRow)
            .where(UserRow.role == Role.ADMIN.value, UserRow.state == AccountState.ACTIVE.value)
        )
        return int(result.scalar_one())

    async def lock_active_admin_count(self) -> int:
        """Count active admins with those rows locked.

        Demoting or disabling the last admin is a check-then-act on a *set*, not a
        single row: without locking the counted rows, two concurrent requests
        could each see two admins and each remove one.
        """
        result = await self._session.execute(
            select(UserRow.id)
            .where(UserRow.role == Role.ADMIN.value, UserRow.state == AccountState.ACTIVE.value)
            .with_for_update()
        )
        return len(result.scalars().all())


class RefreshTokenRepository:
    """Reads and writes refresh-token families."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> None:
        await self._session.execute(insert(RefreshTokenRow).values(**_refresh_values(token)))

    async def get(self, token_hash: TokenHash) -> RefreshToken | None:
        row = await self._session.get(RefreshTokenRow, str(token_hash))
        return _to_refresh_token(row) if row else None

    async def get_for_rotation(self, token_hash: TokenHash) -> RefreshToken | None:
        """Read a refresh token with its row locked.

        Rotation reads the token, decides it is usable, then writes a revocation
        and a successor. Two parallel refreshes with the same cookie must not both
        get past the decision, so the lock is taken before the check — the second
        request blocks and then sees the token already rotated, which is exactly
        the replay signal.
        """
        result = await self._session.execute(
            select(RefreshTokenRow).where(RefreshTokenRow.token_hash == str(token_hash)).with_for_update()
        )
        row = result.scalar_one_or_none()
        return _to_refresh_token(row) if row else None

    async def has_live_session(self, session_id: str, user_id: UserId, *, now: datetime) -> bool:
        """Return whether the session row remains active for the owner."""
        result = await self._session.execute(
            select(RefreshTokenRow.session_id)
            .where(
                RefreshTokenRow.session_id == session_id,
                RefreshTokenRow.user_id == str(user_id),
                RefreshTokenRow.revoked_at.is_(None),
                RefreshTokenRow.family_expires_at > now,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_family(self, family_id: FamilyId) -> tuple[RefreshToken, ...]:
        result = await self._session.execute(
            select(RefreshTokenRow)
            .where(RefreshTokenRow.family_id == str(family_id))
            .order_by(RefreshTokenRow.issued_at)
        )
        return tuple(_to_refresh_token(row) for row in result.scalars().all())

    async def rotate(self, revoked: RefreshToken, successor: RefreshToken) -> None:
        """Apply a rotation produced by `RefreshToken.rotate`.

        The revocation is a conditional `UPDATE` on `revoked_at IS NULL`: if a
        concurrent transaction already rotated this token, zero rows match and the
        rotation is refused instead of creating a second successor. That is what
        keeps a family a chain rather than a tree.
        """
        result = await self._session.execute(
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.token_hash == str(revoked.token_hash),
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked.revoked_at,
                revocation_reason=(revoked.revocation_reason.value if revoked.revocation_reason else None),
            )
        )
        if _rowcount(result) != 1:
            raise ConcurrentTokenUseError("refresh token was already rotated")
        await self.add(successor)

    async def revoke_family(self, family_id: FamilyId, *, now: datetime, reason: RevocationReason) -> int:
        """Revoke every live token in one family. Returns rows revoked.

        Only rows with `revoked_at IS NULL` are touched, so an earlier reason is
        preserved: a token revoked by rotation must keep reading as `rotated`,
        because that record is the evidence replay detection relies on.
        """
        result = await self._session.execute(
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.family_id == str(family_id),
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=ensure_utc(now), revocation_reason=reason.value)
        )
        return _rowcount(result)

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime, reason: RevocationReason) -> int:
        """Revoke every live token for a user across all devices."""
        result = await self._session.execute(
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.user_id == str(user_id),
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=ensure_utc(now), revocation_reason=reason.value)
        )
        return _rowcount(result)

    async def delete_expired(self, *, now: datetime) -> int:
        """Drop families past their absolute expiry.

        Expired rows carry no authorization value; keeping them only grows a table
        of credential hashes.
        """
        result = await self._session.execute(
            delete(RefreshTokenRow).where(RefreshTokenRow.family_expires_at <= ensure_utc(now))
        )
        return _rowcount(result)


def _refresh_values(token: RefreshToken) -> dict[str, object]:
    return {
        "token_hash": str(token.token_hash),
        "session_id": str(token.session_id),
        "family_id": str(token.family_id),
        "user_id": str(token.user_id),
        "issued_at": ensure_utc(token.issued_at),
        "family_expires_at": ensure_utc(token.family_expires_at),
        "revoked_at": ensure_utc(token.revoked_at) if token.revoked_at else None,
        "revocation_reason": token.revocation_reason.value if token.revocation_reason else None,
    }


class OneTimeTokenRepository:
    """Reads and writes verification and reset tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(self, token: OneTimeToken, *, now: datetime) -> int:
        """Supersede prior live tokens for the same (user, purpose), then insert.

        Latest-token-wins: a resend must not leave two usable credentials
        outstanding. Superseding is scoped to one purpose so requesting a password
        reset cannot silently cancel a pending email verification.
        """
        moment = ensure_utc(now)
        superseded = await self._session.execute(
            update(OneTimeTokenRow)
            .where(
                OneTimeTokenRow.user_id == str(token.user_id),
                OneTimeTokenRow.purpose == token.purpose.value,
                OneTimeTokenRow.consumed_at.is_(None),
                OneTimeTokenRow.superseded_at.is_(None),
            )
            .values(superseded_at=moment)
        )
        await self._session.execute(
            insert(OneTimeTokenRow).values(
                token_hash=str(token.token_hash),
                purpose=token.purpose.value,
                user_id=str(token.user_id),
                issued_at=ensure_utc(token.issued_at),
                expires_at=ensure_utc(token.expires_at),
            )
        )
        return _rowcount(superseded)

    async def get(self, token_hash: TokenHash) -> OneTimeToken | None:
        row = await self._session.get(OneTimeTokenRow, str(token_hash))
        return _to_one_time_token(row) if row else None

    async def get_for_consumption(self, token_hash: TokenHash) -> OneTimeToken | None:
        """Read a one-time token with its row locked, before validating it."""
        result = await self._session.execute(
            select(OneTimeTokenRow).where(OneTimeTokenRow.token_hash == str(token_hash)).with_for_update()
        )
        row = result.scalar_one_or_none()
        return _to_one_time_token(row) if row else None

    async def mark_consumed(self, token: OneTimeToken) -> None:
        """Record consumption with a conditional `UPDATE`.

        The `consumed_at IS NULL AND superseded_at IS NULL` predicate is the
        single-use guarantee: two requests submitting the same token concurrently
        produce one matching row and one refusal, no matter how the interleaving
        falls out.
        """
        result = await self._session.execute(
            update(OneTimeTokenRow)
            .where(
                OneTimeTokenRow.token_hash == str(token.token_hash),
                OneTimeTokenRow.consumed_at.is_(None),
                OneTimeTokenRow.superseded_at.is_(None),
            )
            .values(consumed_at=token.consumed_at)
        )
        if _rowcount(result) != 1:
            raise ConcurrentTokenUseError("token was already used")

    async def delete_expired(self, *, now: datetime) -> int:
        result = await self._session.execute(
            delete(OneTimeTokenRow).where(OneTimeTokenRow.expires_at <= ensure_utc(now))
        )
        return _rowcount(result)


@dataclass(frozen=True, slots=True)
class RateLimitWindow:
    """The state of one fixed window after an attempt was counted."""

    key: str
    window_start: datetime
    attempts: int


# `scope:digest`, where the digest is lowercase hex. Enforced rather than merely
# documented: without a check, the first caller in a hurry stores
# `login:alice@gmail.com`, and the limiter table becomes an account inventory that
# survives every account deletion.
_RATE_LIMIT_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_.:-]{1,64}:[0-9a-f]{32}$")
_RATE_LIMIT_DIGEST_CHARS: Final[int] = 32


def build_rate_limit_key(scope: str, subject: str, *, pepper: str) -> str:
    """Return a non-reversible limiter key for `subject` within `scope`.

    HMAC, not a bare hash: an email address has far too little entropy for a
    plain digest to resist a dictionary sweep of a leaked table. The pepper is a
    server-side secret, so an attacker holding only the table cannot recover which
    accounts were being attacked.

    `scope` stays in the clear — knowing that a row counts login attempts
    discloses nothing, and the limiter needs to bucket by scope.
    """
    if not scope or ":" in scope:
        raise ValueError("rate-limit scope must be non-empty and contain no ':'")
    if not subject:
        raise ValueError("rate-limit subject must not be empty")
    if not pepper:
        raise ValueError("rate-limit pepper must not be empty")
    digest = hmac.new(pepper.encode("utf-8"), f"{scope}\x00{subject}".encode(), hashlib.sha256).hexdigest()[
        :_RATE_LIMIT_DIGEST_CHARS
    ]
    return f"{scope}:{digest}"


class RateLimitRepository:
    """Fixed-window abuse counters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_attempt(self, key: str, *, window_start: datetime, expires_at: datetime) -> RateLimitWindow:
        """Count one attempt and return the new total.

        A single `INSERT ... ON CONFLICT DO UPDATE` does the whole thing: a
        read-then-write would undercount under concurrency, which is precisely the
        condition a limiter exists to handle.
        """
        _assert_hashed_key(key)
        start = ensure_utc(window_start)
        statement = (
            pg_insert(RateLimitCounterRow)
            .values(
                key=key,
                window_start=start,
                attempts=_ATTEMPT_INCREMENT,
                expires_at=ensure_utc(expires_at),
            )
            .on_conflict_do_update(
                index_elements=[RateLimitCounterRow.key, RateLimitCounterRow.window_start],
                set_={"attempts": RateLimitCounterRow.attempts + _ATTEMPT_INCREMENT},
            )
            .returning(RateLimitCounterRow.attempts)
        )
        result = await self._session.execute(statement)
        return RateLimitWindow(key=key, window_start=start, attempts=int(result.scalar_one()))

    async def attempts_in_window(self, key: str, *, window_start: datetime) -> int:
        _assert_hashed_key(key)
        result = await self._session.execute(
            select(RateLimitCounterRow.attempts).where(
                RateLimitCounterRow.key == key,
                RateLimitCounterRow.window_start == ensure_utc(window_start),
            )
        )
        return int(result.scalar_one_or_none() or 0)

    async def reset(self, key: str) -> int:
        """Clear a key's counters, for example after a successful login."""
        _assert_hashed_key(key)
        result = await self._session.execute(delete(RateLimitCounterRow).where(RateLimitCounterRow.key == key))
        return _rowcount(result)

    async def delete_expired(self, *, now: datetime) -> int:
        result = await self._session.execute(
            delete(RateLimitCounterRow).where(RateLimitCounterRow.expires_at <= ensure_utc(now))
        )
        return _rowcount(result)


class SecurityEventRepository:
    """Append-only security audit log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        event_type: str,
        occurred_at: datetime,
        actor_user_id: UserId | None = None,
        correlation_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Append one event.

        `payload` must already be minimized by the caller. This method does not
        sanitize it — a repository cannot tell an allowlisted identifier from a
        raw token — but it is the reason payload construction stays in the
        application layer rather than passing request objects down here.
        """
        if not event_type:
            raise ValueError("security event type must not be empty")
        await self._session.execute(
            insert(SecurityEventRow).values(
                event_type=event_type,
                occurred_at=ensure_utc(occurred_at),
                actor_user_id=str(actor_user_id) if actor_user_id else None,
                correlation_id=correlation_id,
                payload=payload or {},
            )
        )

    async def list_recent(self, *, limit: int = 50) -> Sequence[SecurityEventRow]:
        result = await self._session.execute(select(SecurityEventRow).order_by(SecurityEventRow.id.desc()).limit(limit))
        return result.scalars().all()


class UserProfileRepository:
    """PostgreSQL storage for user profiles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> UserProfile | None:
        row = await self._session.scalar(select(UserProfileRow).where(UserProfileRow.user_id == str(user_id)))
        if row is None:
            return None
        return UserProfile(
            user_id=UserId(row.user_id),
            full_name=row.full_name,
            phone_number=row.phone_number,
            address=row.address,
            showroom_name=row.showroom_name,
            avatar_url=row.avatar_url,
            vehicle_preference=row.vehicle_preference,
            budget_preference=row.budget_preference,
            seats_preference=row.seats_preference,
            home_charging=row.home_charging,
            title=row.title,
            bio=row.bio,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def save(self, profile: UserProfile, *, now: datetime) -> None:
        now_utc = ensure_utc(now)
        stmt = (
            pg_insert(UserProfileRow)
            .values(
                user_id=str(profile.user_id),
                full_name=profile.full_name,
                phone_number=profile.phone_number,
                address=profile.address,
                showroom_name=profile.showroom_name,
                avatar_url=profile.avatar_url,
                vehicle_preference=profile.vehicle_preference,
                budget_preference=profile.budget_preference,
                seats_preference=profile.seats_preference,
                home_charging=profile.home_charging,
                title=profile.title,
                bio=profile.bio,
                created_at=now_utc,
                updated_at=now_utc,
            )
            .on_conflict_do_update(
                index_elements=[UserProfileRow.user_id],
                set_={
                    "full_name": profile.full_name,
                    "phone_number": profile.phone_number,
                    "address": profile.address,
                    "showroom_name": profile.showroom_name,
                    "avatar_url": profile.avatar_url,
                    "vehicle_preference": profile.vehicle_preference,
                    "budget_preference": profile.budget_preference,
                    "seats_preference": profile.seats_preference,
                    "home_charging": profile.home_charging,
                    "title": profile.title,
                    "bio": profile.bio,
                    "updated_at": now_utc,
                },
            )
        )
        await self._session.execute(stmt)


@dataclass(frozen=True, slots=True)
class AuthRepositories:
    """The repository set bound to one transaction."""

    users: UserRepository
    profiles: UserProfileRepository
    refresh_tokens: RefreshTokenRepository
    one_time_tokens: OneTimeTokenRepository
    rate_limits: RateLimitRepository
    security_events: SecurityEventRepository


def build_repositories(session: AsyncSession) -> AuthRepositories:
    return AuthRepositories(
        users=UserRepository(session),
        profiles=UserProfileRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        one_time_tokens=OneTimeTokenRepository(session),
        rate_limits=RateLimitRepository(session),
        security_events=SecurityEventRepository(session),
    )


class AuthUnitOfWork:
    """Owns the transaction boundary for Auth flows.

    Exposed as an async context manager so the commit is one visible statement at
    the end of a flow: commit on clean exit, roll back on any exception. Nothing
    inside a repository commits, so a flow either lands whole or not at all.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AuthRepositories]:
        async with self._session_factory() as session, session.begin():
            yield build_repositories(session)


def _assert_hashed_key(key: str) -> None:
    """Reject a limiter key that is not `scope:<hex digest>`.

    The rejection message deliberately does not echo the key: the offending value
    is exactly the identifier (an email, an IP, a token) that must not reach a log.
    """
    if not key:
        raise ValueError("rate-limit key must not be empty")
    if not _RATE_LIMIT_KEY_PATTERN.fullmatch(key):
        raise ValueError("rate-limit key must be 'scope:<hex digest>'; build it with build_rate_limit_key")


def _violates(error: IntegrityError, constraint: str) -> bool:
    """Report whether an IntegrityError names a specific constraint.

    Matching on the constraint name keeps the translation precise: catching every
    IntegrityError as "email taken" would mislabel an unrelated violation.
    """
    return constraint in str(error.orig)


__all__ = [
    "AuthRepositories",
    "AuthUnitOfWork",
    "ConcurrentTokenUseError",
    "EmailAlreadyRegisteredError",
    "OneTimeTokenRepository",
    "RateLimitRepository",
    "RateLimitWindow",
    "RefreshTokenRepository",
    "SecurityEventRepository",
    "UserRepository",
    "build_rate_limit_key",
    "build_repositories",
]
