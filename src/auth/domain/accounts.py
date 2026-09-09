"""Account lifecycle entities and state transitions.

The lifecycle is modelled as an explicit state, not as a set of independent
booleans. `verified=True, disabled=True, temporary_password=True` is three flags
describing one state badly; asking "can this account start a session?" then means
re-deriving the answer at every call site, and one site will get it wrong.

Two lifecycles share one state machine:

    customer: PENDING_VERIFICATION -> ACTIVE            (-> DISABLED)
    staff:    TEMPORARY_PASSWORD   -> ACTIVE            (-> DISABLED)

Only `ACTIVE` may hold a normal session. That single rule is what stops an
unverified customer, or staff who have not yet replaced a temporary password,
from receiving normal credentials.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum, unique

from src.auth.domain.authorization import Role
from src.auth.domain.clock import ensure_utc, is_expired
from src.auth.domain.errors import (
    AccountDisabledError,
    AccountNotVerifiedError,
    AccountStateError,
    TemporaryPasswordExpiredError,
    TemporaryPasswordRequiredError,
)
from src.auth.domain.values import NormalizedEmail, PasswordHash, UserId


@unique
class AccountState(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    TEMPORARY_PASSWORD = "temporary_password"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class User:
    """An Auth account.

    Frozen: every transition returns a new instance, so a caller cannot mutate an
    account halfway through a flow and leave a partially applied change behind.
    Only `password_hash` is stored — never the plaintext (`AGENTS.md:52`).
    """

    id: UserId
    email: NormalizedEmail
    role: Role
    state: AccountState
    password_hash: PasswordHash
    created_at: datetime
    temporary_password_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        ensure_utc(self.created_at)
        if self.temporary_password_expires_at is not None:
            ensure_utc(self.temporary_password_expires_at)
        if not self.password_hash:
            raise AccountStateError("user must have a password hash")

    @property
    def is_active(self) -> bool:
        return self.state is AccountState.ACTIVE

    @property
    def is_disabled(self) -> bool:
        return self.state is AccountState.DISABLED

    @property
    def requires_password_change(self) -> bool:
        return self.state is AccountState.TEMPORARY_PASSWORD

    def assert_can_start_session(self) -> None:
        """Raise unless this account may receive normal session credentials.

        Each rejection is a distinct typed error so the application layer can
        choose what is safe to disclose; the domain does not decide that.
        """
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("account is disabled")
        if self.state is AccountState.PENDING_VERIFICATION:
            raise AccountNotVerifiedError("account email is not verified")
        if self.state is AccountState.TEMPORARY_PASSWORD:
            raise TemporaryPasswordRequiredError("temporary password must be changed first")
        if self.state is not AccountState.ACTIVE:
            raise AccountStateError(f"account state {self.state.value} cannot start a session")

    def verify_email(self) -> "User":
        """Move a pending customer to active after successful verification."""
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("a disabled account cannot be verified")
        if self.state is not AccountState.PENDING_VERIFICATION:
            raise AccountStateError(f"account in state {self.state.value} is not awaiting verification")
        return replace(self, state=AccountState.ACTIVE)

    def complete_temporary_password_change(self, new_hash: PasswordHash, now: datetime | None = None) -> "User":
        """Replace an unexpired temporary password and activate the staff account."""
        if (
            now is not None
            and self.temporary_password_expires_at is not None
            and is_expired(now, self.temporary_password_expires_at)
        ):
            raise TemporaryPasswordExpiredError("temporary password expired")
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("a disabled account cannot change its password")
        if self.state is not AccountState.TEMPORARY_PASSWORD:
            raise AccountStateError("account is not awaiting a temporary-password change")
        if not new_hash:
            raise AccountStateError("new password hash must not be empty")
        if new_hash == self.password_hash:
            raise AccountStateError("new password hash must differ from the temporary one")
        return replace(
            self,
            state=AccountState.ACTIVE,
            password_hash=new_hash,
            temporary_password_expires_at=None,
        )

    def change_password(self, new_hash: PasswordHash) -> "User":
        """Replace the password of an already active account."""
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("a disabled account cannot change its password")
        if self.state is AccountState.PENDING_VERIFICATION:
            raise AccountNotVerifiedError("an unverified account cannot change its password")
        if self.state is AccountState.TEMPORARY_PASSWORD:
            raise TemporaryPasswordRequiredError("use the temporary-password change flow for this account")
        if not new_hash:
            raise AccountStateError("new password hash must not be empty")
        return replace(self, password_hash=new_hash)

    def reset_password(self, new_hash: PasswordHash) -> "User":
        """Apply a recovery reset.

        Reset also completes verification: proving control of the mailbox is the
        same evidence email verification asks for, so forcing a separate
        verification step afterwards would strand the user.
        """
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("a disabled account cannot reset its password")
        if not new_hash:
            raise AccountStateError("new password hash must not be empty")
        return replace(self, state=AccountState.ACTIVE, password_hash=new_hash)

    def change_role(self, role: Role) -> "User":
        """Assign an administrator-approved role to this account."""
        return replace(self, role=role)

    def disable(self) -> "User":
        if self.state is AccountState.DISABLED:
            raise AccountDisabledError("account is already disabled")
        return replace(self, state=AccountState.DISABLED)

    def enable(self, *, state: AccountState = AccountState.ACTIVE) -> "User":
        """Re-enable a disabled account.

        Re-enabling never resurrects sessions: revocation is recorded on the
        session records themselves, which this transition does not touch.
        """
        if self.state is not AccountState.DISABLED:
            raise AccountStateError("only a disabled account can be enabled")
        if state is AccountState.DISABLED:
            raise AccountStateError("cannot enable an account into the disabled state")
        return replace(self, state=state)


def initial_customer_state() -> AccountState:
    """Customers must prove mailbox control before they can sign in."""
    return AccountState.PENDING_VERIFICATION


def initial_staff_state() -> AccountState:
    """Staff are created with a temporary password they must replace."""
    return AccountState.TEMPORARY_PASSWORD


@dataclass(frozen=True, slots=True)
class UserProfile:
    """User profile data for customer and advisor roles."""

    user_id: UserId
    full_name: str | None = None
    phone_number: str | None = None
    address: str | None = None
    showroom_name: str | None = None
    avatar_url: str | None = None
    vehicle_preference: str | None = None
    budget_preference: str | None = None
    seats_preference: str | None = None
    home_charging: bool | None = None
    title: str | None = None
    bio: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
