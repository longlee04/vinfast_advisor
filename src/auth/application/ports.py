"""Application ports for customer authentication."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from src.auth.application.contracts import UserPage
from src.auth.domain.accounts import AccountState, User, UserProfile
from src.auth.domain.authorization import Role
from src.auth.domain.sessions import OneTimeToken, RefreshToken, RevocationReason
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, PlaintextToken, TokenHash, UserId


class UserStore(Protocol):
    async def add(self, user: User, *, now: datetime) -> None: ...
    async def claim_first_admin(self, user: User, *, now: datetime) -> bool: ...
    async def get_by_email(self, email: NormalizedEmail) -> User | None: ...
    async def get_by_id(self, user_id: UserId) -> User | None: ...
    async def get_for_update(self, user_id: UserId) -> User | None: ...
    async def lock_active_admin_count(self) -> int: ...
    async def list_page(
        self,
        *,
        role: Role | None,
        state: AccountState | None,
        email_query: str | None,
        page: int,
        page_size: int,
    ) -> UserPage: ...
    async def save(self, user: User, *, now: datetime) -> None: ...


class UserProfileStore(Protocol):
    async def get(self, user_id: UserId) -> UserProfile | None: ...
    async def save(self, profile: UserProfile, *, now: datetime) -> None: ...


class RefreshStore(Protocol):
    async def add(self, token: RefreshToken) -> None: ...
    async def get(self, token_hash: TokenHash) -> RefreshToken | None: ...
    async def get_for_rotation(self, token_hash: TokenHash) -> RefreshToken | None: ...
    async def rotate(self, revoked: RefreshToken, successor: RefreshToken) -> None: ...
    async def has_live_session(self, session_id: str, user_id: UserId, *, now: datetime) -> bool: ...
    async def revoke_family(self, family_id: str, *, now: datetime, reason: RevocationReason) -> int: ...
    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime, reason: RevocationReason) -> int: ...


class OneTimeTokenStore(Protocol):
    async def issue(self, token: OneTimeToken, *, now: datetime) -> int: ...
    async def get(self, token_hash: TokenHash) -> OneTimeToken | None: ...
    async def get_for_consumption(self, token_hash: TokenHash) -> OneTimeToken | None: ...
    async def mark_consumed(self, token: OneTimeToken) -> None: ...


class SecurityEventStore(Protocol):
    async def append(self, *, event_type: str, occurred_at: datetime, actor_user_id: UserId | None = None) -> None: ...


class AuthStores(Protocol):
    users: UserStore
    profiles: UserProfileStore
    refresh_tokens: RefreshStore
    one_time_tokens: OneTimeTokenStore
    security_events: SecurityEventStore


class AuthTransaction(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[AuthStores]:
        """Yield a unit of work that commits only on normal context exit.

        Any exception escaping the context must roll back every mutation made
        through the yielded stores before it is re-raised.
        """


class AbuseLimitExceededError(RuntimeError):
    """Raised when an application abuse-control policy refuses an operation."""


class RecoveryRateLimiter(Protocol):
    async def allow(self, key: str, *, now: datetime) -> bool:
        """Return whether this recovery operation may proceed."""


class RateLimitKeyBuilder(Protocol):
    def build(self, scope: str, subject: str) -> str:
        """Build a non-reversible key from a recovery identity."""


class EmailDeliveryError(RuntimeError):
    """Raised when an email provider cannot deliver a requested message."""


class EmailSender(Protocol):
    async def send_verification(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        """Deliver an account-verification credential."""

    async def send_temporary_password(self, *, recipient: NormalizedEmail, password: PlaintextPassword) -> None: ...

    async def send_password_reset(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        """Deliver a password-reset credential or raise `EmailDeliveryError`."""


class TokenFactory(Protocol):
    def new_secret(self) -> str: ...
    def hash(self, secret: str) -> TokenHash: ...


class AccessTokenIssuer(Protocol):
    def issue(self, *, user_id: UserId, session_id: str, expires_at: datetime) -> str: ...
    def validate(self, token: str, *, now: datetime) -> tuple[UserId, str] | None: ...
