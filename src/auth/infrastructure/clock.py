"""Real UTC clock.

This is the only place in Auth that reads the wall clock. It lives in
infrastructure rather than in the domain so that `src/auth/domain/` contains no
`datetime.now()` call at all — an architecture check can then assert that
property mechanically instead of relying on reviewers to spot a stray call.

Domain and application code depend on the `Clock` protocol; the composition root
injects this implementation in production and a `FixedClock` in tests.
"""

from datetime import UTC, datetime


class SystemClock:
    """Returns the current UTC instant. Constructed at the composition boundary."""

    def now(self) -> datetime:
        return datetime.now(UTC)
