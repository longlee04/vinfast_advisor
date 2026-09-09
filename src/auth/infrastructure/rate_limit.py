"""PostgreSQL-backed fixed-window rate-limit adapters."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth.infrastructure.repositories import RateLimitRepository, build_rate_limit_key


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """A bounded fixed window enforced by the Auth PostgreSQL database."""

    attempts: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.window_seconds < 1:
            raise ValueError("rate-limit policy values must be positive")


class PostgresRateLimiter:
    """Atomically count attempts through the persisted Auth counter table."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        policy: RateLimitPolicy,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy

    async def allow(self, key: str, *, now: datetime) -> bool:
        """Count one attempt and report whether it remains inside the configured bound."""
        window_start = _window_start(now, self._policy.window_seconds)
        expires_at = window_start + timedelta(seconds=self._policy.window_seconds)
        async with self._session_factory() as session, session.begin():
            window = await RateLimitRepository(session).register_attempt(
                key,
                window_start=window_start,
                expires_at=expires_at,
            )
        return window.attempts <= self._policy.attempts


@dataclass(frozen=True, slots=True)
class HmacRateLimitKeyBuilder:
    """Derive non-reversible limiter keys without storing account identities."""

    pepper: str

    def build(self, scope: str, subject: str) -> str:
        return build_rate_limit_key(scope, subject, pepper=self.pepper)


def _window_start(now: datetime, window_seconds: int) -> datetime:
    """Round an aware instant down to its fixed-window boundary in UTC."""
    instant = now.astimezone(UTC)
    epoch = int(instant.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)
