"""Time policy for the Auth domain.

Domain and application code never call the wall clock directly. They receive a
`Clock` and ask it for the current instant, which is what makes expiry-boundary
behavior testable at microsecond precision instead of approximately.

All Auth instants are timezone-aware UTC. A naive datetime is rejected rather
than assumed to be UTC: assuming is how a token silently gains or loses hours
when a replica runs in a different local zone.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class NaiveDatetimeError(ValueError):
    """Raised when a datetime without timezone information reaches Auth."""


class Clock(Protocol):
    """Supplies the current UTC instant."""

    def now(self) -> datetime: ...


def ensure_utc(moment: datetime) -> datetime:
    """Return `moment` as UTC, rejecting naive datetimes."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise NaiveDatetimeError("Auth timestamps must be timezone-aware UTC")
    return moment.astimezone(UTC)


def is_expired(now: datetime, expires_at: datetime) -> bool:
    """Return whether `expires_at` has been reached.

    Exact expiry counts as expired: validity is `now < expires_at`. A credential
    that is valid *at* its stated expiry would be valid for one extra tick, and
    "valid until 10:00" is clearer than "valid through 10:00 inclusive".
    """
    return ensure_utc(now) >= ensure_utc(expires_at)


def expires_after(now: datetime, ttl_seconds: int) -> datetime:
    """Return the UTC expiry instant `ttl_seconds` after `now`."""
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    return ensure_utc(now) + timedelta(seconds=ttl_seconds)


class FixedClock:
    """Deterministic clock for tests and for pinning an instant within a flow.

    Reusing one instant across a multi-step flow also prevents a race where two
    steps of the same operation disagree about "now".
    """

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        self._now = ensure_utc(now)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)
