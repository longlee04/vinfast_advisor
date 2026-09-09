"""Session, refresh-family, and one-time-token policy.

The refresh model is a *family*: one login creates a family, and each rotation
revokes the current token and appends exactly one successor. Presenting a token
that was already rotated is a replay, and the only safe reading is that the token
leaked, so the whole family dies rather than just that token.

Two invariants are load-bearing:

* Rotation never extends the family's absolute expiry. Otherwise an attacker with
  a live token could refresh forever and the 30-day bound would mean nothing.
* Replay revokes one family, not every session. Killing all devices on a single
  suspicious token would let anyone log a user out of everything by replaying a
  token they hold.

One-time tokens (verification, reset) are hash-only, purpose-bound, user-bound,
and single-use. Latest-token-wins: issuing a new one invalidates the previous, so
a resend cannot leave two usable credentials outstanding.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum, unique

from src.auth.domain.clock import ensure_utc, is_expired
from src.auth.domain.errors import (
    RefreshTokenReplayError,
    SessionExpiredError,
    SessionRevokedError,
    TokenAlreadyConsumedError,
    TokenExpiredError,
    TokenPurposeMismatchError,
)
from src.auth.domain.values import FamilyId, SessionId, TokenHash, UserId


@unique
class TokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


@unique
class RevocationReason(StrEnum):
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    ROTATED = "rotated"
    REPLAY_DETECTED = "replay_detected"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_DISABLED = "account_disabled"
    ADMIN_REVOKED = "admin_revoked"


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """One link in a refresh family. Stored as a hash, never as plaintext."""

    token_hash: TokenHash
    session_id: SessionId
    family_id: FamilyId
    user_id: UserId
    issued_at: datetime
    # Absolute family deadline, copied to every successor and never recomputed.
    family_expires_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: RevocationReason | None = None

    def __post_init__(self) -> None:
        ensure_utc(self.issued_at)
        ensure_utc(self.family_expires_at)
        if self.revoked_at is not None:
            ensure_utc(self.revoked_at)
        if not self.token_hash:
            raise ValueError("refresh token must have a hash")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired_at(self, now: datetime) -> bool:
        return is_expired(now, self.family_expires_at)

    def assert_usable(self, now: datetime) -> None:
        """Raise unless this token may be exchanged right now.

        Replay is distinguished from ordinary revocation: only a token revoked by
        rotation and then presented again indicates a leaked credential.
        """
        if self.revocation_reason is RevocationReason.ROTATED:
            raise RefreshTokenReplayError("refresh token was already rotated")
        if self.is_revoked:
            raise SessionRevokedError("refresh token was revoked")
        if self.is_expired_at(now):
            raise SessionExpiredError("refresh family has reached its absolute expiry")

    def revoke(self, now: datetime, reason: RevocationReason) -> "RefreshToken":
        """Return a revoked copy. Re-revoking keeps the original reason.

        The first reason is the true one: a token rotated and later swept by a
        logout-all must still read as `ROTATED`, or replay detection loses the
        evidence it depends on.
        """
        if self.is_revoked:
            return self
        return replace(self, revoked_at=ensure_utc(now), revocation_reason=reason)

    def rotate(self, now: datetime, successor_hash: TokenHash) -> tuple["RefreshToken", "RefreshToken"]:
        """Revoke this token and return `(revoked_current, successor)`.

        The successor inherits `family_expires_at` unchanged, which is what keeps
        the 30-day absolute bound absolute.
        """
        self.assert_usable(now)
        if not successor_hash:
            raise ValueError("successor token must have a hash")
        if successor_hash == self.token_hash:
            raise ValueError("successor token hash must differ from the rotated token")

        moment = ensure_utc(now)
        revoked = self.revoke(moment, RevocationReason.ROTATED)
        successor = RefreshToken(
            token_hash=successor_hash,
            session_id=self.session_id,
            family_id=self.family_id,
            user_id=self.user_id,
            issued_at=moment,
            family_expires_at=self.family_expires_at,
        )
        return revoked, successor


@dataclass(frozen=True, slots=True)
class OneTimeToken:
    """A verification or reset token: hash-only, purpose-bound, single-use."""

    token_hash: TokenHash
    purpose: TokenPurpose
    user_id: UserId
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        ensure_utc(self.issued_at)
        ensure_utc(self.expires_at)
        if self.consumed_at is not None:
            ensure_utc(self.consumed_at)
        if self.superseded_at is not None:
            ensure_utc(self.superseded_at)
        if not self.token_hash:
            raise ValueError("one-time token must have a hash")

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_superseded(self) -> bool:
        return self.superseded_at is not None

    def assert_usable(self, now: datetime, *, purpose: TokenPurpose, user_id: UserId) -> None:
        """Raise unless this token may be consumed for this purpose and user.

        Purpose and owner are checked before expiry so a reset token can never be
        spent as a verification token, regardless of timing.
        """
        if self.purpose is not purpose:
            raise TokenPurposeMismatchError("token was issued for a different purpose")
        if self.user_id != user_id:
            raise TokenPurposeMismatchError("token was issued for a different user")
        if self.is_consumed:
            raise TokenAlreadyConsumedError("token was already used")
        if self.is_superseded:
            raise TokenAlreadyConsumedError("token was replaced by a newer one")
        if is_expired(now, self.expires_at):
            raise TokenExpiredError("token has expired")

    def consume(self, now: datetime, *, purpose: TokenPurpose, user_id: UserId) -> "OneTimeToken":
        """Return a consumed copy after validating purpose, owner, and expiry."""
        self.assert_usable(now, purpose=purpose, user_id=user_id)
        return replace(self, consumed_at=ensure_utc(now))

    def supersede(self, now: datetime) -> "OneTimeToken":
        """Invalidate this token because a newer one was issued (latest wins).

        A consumed token stays consumed: that record is the audit trail showing
        the credential was actually spent.
        """
        if self.is_consumed or self.is_superseded:
            return self
        return replace(self, superseded_at=ensure_utc(now))


def revoke_family(
    tokens: tuple[RefreshToken, ...],
    now: datetime,
    reason: RevocationReason,
) -> tuple[RefreshToken, ...]:
    """Revoke every token in one family."""
    return tuple(token.revoke(now, reason) for token in tokens)


def revoke_all_families(
    tokens: tuple[RefreshToken, ...],
    now: datetime,
    reason: RevocationReason,
) -> tuple[RefreshToken, ...]:
    """Revoke every token for a user across all their devices."""
    return tuple(token.revoke(now, reason) for token in tokens)
