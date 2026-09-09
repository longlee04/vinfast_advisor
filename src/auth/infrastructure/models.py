"""SQLAlchemy models for the Auth schema.

Every table is prefixed `auth_` so the Auth schema is visibly separate from the
legacy SQLite-backed tables and an Alembic autogenerate run cannot mistake one
for the other.

Storage rules enforced at the schema level, not just in application code:

* No column can hold a plaintext credential. Passwords and all tokens are stored
  as `*_hash`, so a database dump or a stray log of a row cannot leak one
  (`AGENTS.md:52`).
* Every timestamp is `TIMESTAMP WITH TIME ZONE`. A naive column would silently
  reinterpret an instant when a replica runs in another zone, and expiry is
  exactly where that matters.
* Identity uniqueness is on the *normalized* email, matching
  `NormalizedEmail.parse`, so a constraint violation and an application lookup
  can never disagree.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Column widths. Hash columns are sized for Argon2id encoded output and hex
# digests with headroom; they are bounded rather than TEXT so an oversized value
# fails at the boundary instead of being stored.
EMAIL_LENGTH = 254
PASSWORD_HASH_LENGTH = 255
TOKEN_HASH_LENGTH = 128
IDENTIFIER_LENGTH = 64
ENUM_LENGTH = 32
RATE_LIMIT_KEY_LENGTH = 200


class AuthBase(DeclarativeBase):
    """Declarative base for Auth tables only.

    A dedicated base keeps `AuthBase.metadata` free of legacy tables, so Auth
    migrations can never emit a change against a legacy table.
    """


class UserRow(AuthBase):
    """An Auth account."""

    __tablename__ = "auth_users"

    id: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), primary_key=True)
    # Stores the normalized (trimmed, lowercased) address. The unique constraint
    # is therefore on exactly the value the application looks up.
    email: Mapped[str] = mapped_column(String(EMAIL_LENGTH), nullable=False)
    role: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    state: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_LENGTH), nullable=False)
    temporary_password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("email", name="uq_auth_users_email"),
        CheckConstraint("email = lower(email)", name="ck_auth_users_email_normalized"),
        CheckConstraint("length(password_hash) > 0", name="ck_auth_users_password_hash_present"),
        CheckConstraint(
            "role IN ('customer', 'advisor', 'admin')",
            name="ck_auth_users_role",
        ),
        CheckConstraint(
            "state IN ('pending_verification', 'temporary_password', 'active', 'disabled')",
            name="ck_auth_users_state",
        ),
        # Partial index: last-active-Admin protection counts active admins, and
        # that is the only query needing this shape.
        Index(
            "ix_auth_users_active_admins",
            "id",
            postgresql_where=text("role = 'admin' AND state = 'active'"),
        ),
    )


class BootstrapAdminClaimRow(AuthBase):
    """Singleton claim that makes first-Admin bootstrap atomic.

    PostgreSQL unique-key conflict arbitration covers the otherwise-unlockable
    empty-user-table case. The claim and user insertion share one transaction,
    so a later failure releases the claim too.
    """

    __tablename__ = "auth_bootstrap_admin_claims"

    key: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(IDENTIFIER_LENGTH),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_bootstrap_claims_user"),
        nullable=True,
        unique=True,
    )


class UserProfileRow(AuthBase):
    """Personal profile details for a Customer or Advisor account."""

    __tablename__ = "auth_user_profiles"

    user_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_LENGTH),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_user_profiles_user"),
        primary_key=True,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    showroom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vehicle_preference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    budget_preference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seats_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    home_charging: Mapped[bool | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RefreshTokenRow(AuthBase):
    """One link in a refresh-token family.

    A family is the chain produced by one login. `family_expires_at` is copied to
    every successor rather than recomputed, which is what keeps the 30-day
    absolute lifetime absolute across rotations.
    """

    __tablename__ = "auth_refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), nullable=False)
    family_id: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_LENGTH),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_refresh_tokens_user"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    family_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(ENUM_LENGTH), nullable=True)

    __table_args__ = (
        # Rotation, replay detection, and logout-all each look up by a different
        # key, so all three get an index.
        Index("ix_auth_refresh_tokens_family", "family_id"),
        Index("ix_auth_refresh_tokens_user", "user_id"),
        Index("ix_auth_refresh_tokens_session", "session_id"),
        Index("ix_auth_refresh_tokens_family_expiry", "family_expires_at"),
        CheckConstraint("length(token_hash) > 0", name="ck_auth_refresh_tokens_hash_present"),
        # A revoked row must say why: replay detection reads the reason to tell a
        # rotated token apart from an ordinary logout.
        CheckConstraint(
            "(revoked_at IS NULL) = (revocation_reason IS NULL)",
            name="ck_auth_refresh_tokens_revocation_paired",
        ),
        CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN ("
            "'logout', 'logout_all', 'rotated', 'replay_detected', "
            "'password_reset', 'password_changed', 'account_disabled', 'admin_revoked')",
            name="ck_auth_refresh_tokens_revocation_reason",
        ),
    )


class OneTimeTokenRow(AuthBase):
    """A verification or reset token. Stored hash-only, purpose- and user-bound."""

    __tablename__ = "auth_one_time_tokens"

    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_LENGTH),
        ForeignKey("auth_users.id", ondelete="CASCADE", name="fk_auth_one_time_tokens_user"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Latest-token-wins supersedes prior tokens for the same (user, purpose),
        # so that pair is the hot lookup.
        Index("ix_auth_one_time_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_auth_one_time_tokens_expiry", "expires_at"),
        CheckConstraint("length(token_hash) > 0", name="ck_auth_one_time_tokens_hash_present"),
        CheckConstraint("expires_at > issued_at", name="ck_auth_one_time_tokens_expiry_after_issue"),
        CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name="ck_auth_one_time_tokens_purpose",
        ),
        # A token cannot be both spent and replaced: consuming records that the
        # credential was actually used, which superseding must not overwrite.
        CheckConstraint(
            "consumed_at IS NULL OR superseded_at IS NULL",
            name="ck_auth_one_time_tokens_single_terminal_state",
        ),
    )


class RateLimitCounterRow(AuthBase):
    """Fixed-window abuse counter.

    `key` is a namespaced, non-reversible identifier (for example
    `login:ip:<hash>`), never a raw email or token: a limiter table is a poor
    place to keep an account inventory.
    """

    __tablename__ = "auth_rate_limit_counters"

    key: Mapped[str] = mapped_column(String(RATE_LIMIT_KEY_LENGTH), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Bounded cleanup sweeps by expiry.
        Index("ix_auth_rate_limit_counters_expiry", "expires_at"),
        CheckConstraint("attempts >= 0", name="ck_auth_rate_limit_counters_attempts_non_negative"),
        CheckConstraint("length(key) > 0", name="ck_auth_rate_limit_counters_key_present"),
    )


class SecurityEventRow(AuthBase):
    """Append-only audit record.

    `payload` holds an allowlisted, minimized JSONB object. Nothing here may hold
    a password, raw token, or cookie value; the column exists for identifiers and
    outcomes, not for request bodies.
    """

    __tablename__ = "auth_security_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(ENUM_LENGTH), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable and ON DELETE SET NULL: an event about a failed login for an
    # unknown account has no actor, and deleting a user must not erase history.
    actor_user_id: Mapped[str | None] = mapped_column(
        String(IDENTIFIER_LENGTH),
        ForeignKey("auth_users.id", ondelete="SET NULL", name="fk_auth_security_events_actor"),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        Index("ix_auth_security_events_occurred_at", "occurred_at"),
        Index("ix_auth_security_events_type", "event_type"),
        Index("ix_auth_security_events_actor", "actor_user_id"),
        CheckConstraint("length(event_type) > 0", name="ck_auth_security_events_type_present"),
    )


__all__ = [
    "AuthBase",
    "BootstrapAdminClaimRow",
    "OneTimeTokenRow",
    "RateLimitCounterRow",
    "RefreshTokenRow",
    "SecurityEventRow",
    "UserRow",
]
