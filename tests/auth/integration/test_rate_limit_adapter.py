"""Integration tests for the PostgreSQL-backed rate limiter adapter."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.infrastructure.rate_limit import HmacRateLimitKeyBuilder, PostgresRateLimiter, RateLimitPolicy

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_adapter_persists_counter_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    limiter = PostgresRateLimiter(session_factory, RateLimitPolicy(attempts=3, window_seconds=60))
    key = HmacRateLimitKeyBuilder("integration-pepper").build("login", "person@example.com")

    assert await limiter.allow(key, now=NOW) is True

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT attempts FROM auth_rate_limit_counters WHERE key = :key"),
                {"key": key},
            )
        ).one()
    assert row.attempts == 1


@pytest.mark.asyncio
async def test_adapter_key_excludes_raw_identity_and_token(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = "person@example.com"
    token = "raw-reset-token-value"
    key = HmacRateLimitKeyBuilder("integration-pepper").build("reset", f"{identity}:{token}")

    assert identity not in key
    assert token not in key
    assert await PostgresRateLimiter(session_factory, RateLimitPolicy(3, 60)).allow(key, now=NOW)


@pytest.mark.asyncio
async def test_adapter_rolls_over_at_injected_fixed_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    limiter = PostgresRateLimiter(session_factory, RateLimitPolicy(attempts=1, window_seconds=60))
    key = HmacRateLimitKeyBuilder("integration-pepper").build("login", "rollover@example.com")

    assert await limiter.allow(key, now=NOW) is True
    assert await limiter.allow(key, now=NOW + timedelta(seconds=59)) is False
    assert await limiter.allow(key, now=NOW + timedelta(seconds=60)) is True


@pytest.mark.asyncio
async def test_adapter_concurrent_increments_are_persisted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    limiter = PostgresRateLimiter(session_factory, RateLimitPolicy(attempts=20, window_seconds=60))
    key = HmacRateLimitKeyBuilder("integration-pepper").build("login", "concurrent@example.com")

    results = await asyncio.gather(*(limiter.allow(key, now=NOW) for _ in range(10)))

    assert sum(results) == 10
    async with session_factory() as session:
        count = (
            await session.execute(
                text("SELECT attempts FROM auth_rate_limit_counters WHERE key = :key"),
                {"key": key},
            )
        ).scalar_one()
    assert count == 10


@pytest.mark.asyncio
async def test_adapter_database_failure_is_explicit_and_has_no_memory_fallback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    key = HmacRateLimitKeyBuilder("integration-pepper").build("login", "failure@example.com")
    failing_engine = create_async_engine("postgresql+asyncpg://invalid:invalid@127.0.0.1:1/missing")
    failing_factory = async_sessionmaker(failing_engine, expire_on_commit=False)
    failing_limiter = PostgresRateLimiter(
        failing_factory,
        RateLimitPolicy(attempts=1, window_seconds=60),
    )
    try:
        with pytest.raises((SQLAlchemyError, OSError)):
            await failing_limiter.allow(key, now=NOW)
    finally:
        await failing_engine.dispose()

    async with session_factory() as session:
        count = (await session.execute(text("SELECT count(*) FROM auth_rate_limit_counters"))).scalar_one()
    assert count == 0
