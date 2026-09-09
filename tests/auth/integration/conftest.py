"""Fixtures for Auth tests that need a real PostgreSQL server.

Auth never runs on SQLite, so these tests do not either: row locks,
`ON CONFLICT DO UPDATE`, partial indexes, and `JSONB` are the mechanisms under
test, and an in-memory substitute would verify none of them.

The schema is created by running the real migration command rather than
`metadata.create_all`. If the two ever drift, `create_all` would hide it and the
tests would pass against a schema no deployment has.
"""

import os
import socket
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.auth.infrastructure.repositories import AuthUnitOfWork

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"

# Read at import time, on purpose: the autouse fixture in `tests/auth/conftest.py`
# clears every `AUTH_*` variable so settings tests are deterministic, which would
# otherwise erase the URL before any fixture could see it.
AUTH_TEST_DATABASE_URL = os.environ.get("AUTH_DATABASE_URL", "").strip() or DEFAULT_TEST_DATABASE_URL
_ACTIVE_TEST_DATABASE_URL = AUTH_TEST_DATABASE_URL

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TEST_DATABASE_PREFIX = "p150_auth_test_"

# Child tables first: `auth_security_events.actor_user_id` and the token tables
# reference `auth_users`.
_TABLES_IN_TRUNCATION_ORDER = (
    "auth_security_events",
    "auth_refresh_tokens",
    "auth_one_time_tokens",
    "auth_rate_limit_counters",
    "auth_users",
)

_CONNECT_TIMEOUT_SECONDS = 2.0


def _server_is_reachable(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def run_alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run an Auth Alembic command against the active test database."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic-auth.ini", *arguments],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "AUTH_DATABASE_URL": _ACTIVE_TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        check=False,
    )


def _database_url_parts(database_url: str) -> SplitResult:
    """Parse a PostgreSQL URL while preserving its driver and credentials."""
    return urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))


def _database_url_with_name(database_url: str, name: str) -> str:
    """Return `database_url` with its database path replaced by `name`."""
    parts = _database_url_parts(database_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


async def _create_test_database() -> tuple[str, str]:
    """Create an isolated database through PostgreSQL's maintenance database."""
    parts = _database_url_parts(AUTH_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    database_name = f"{_TEST_DATABASE_PREFIX}{uuid.uuid4().hex}"
    connection = await asyncpg.connect(maintenance_url)
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()
    return _database_url_with_name(AUTH_TEST_DATABASE_URL, database_name), database_name


async def _drop_test_database(database_name: str) -> None:
    """Drop only the temporary database created for this pytest session."""
    parts = _database_url_parts(AUTH_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    connection = await asyncpg.connect(maintenance_url)
    try:
        await connection.execute(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS false')
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await connection.execute(f'DROP DATABASE "{database_name}"')
    finally:
        await connection.close()


@pytest_asyncio.fixture(scope="session")
async def auth_database_url() -> AsyncIterator[str]:
    """Create, migrate, and remove a dedicated PostgreSQL test database."""
    global _ACTIVE_TEST_DATABASE_URL
    if not _server_is_reachable(AUTH_TEST_DATABASE_URL):
        pytest.skip("PostgreSQL is not reachable; start it with 'docker compose up -d postgres'")
    database_url, database_name = await _create_test_database()
    _ACTIVE_TEST_DATABASE_URL = database_url
    try:
        completed = run_alembic("upgrade", "head")
        if completed.returncode != 0:
            pytest.fail(f"alembic upgrade head failed:\n{completed.stderr}")
        yield database_url
    finally:
        await _drop_test_database(database_name)


@pytest_asyncio.fixture
async def engine(auth_database_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_async_engine(auth_database_url)
    try:
        yield created
    finally:
        await created.dispose()


@pytest_asyncio.fixture
async def clean_database(engine: AsyncEngine) -> AsyncIterator[None]:
    """Empty every Auth table before and after each test.

    Truncation runs on both sides of the test: a failure that leaves rows behind
    must not turn the next test red for an unrelated reason.
    """
    await _truncate(engine)
    try:
        yield
    finally:
        await _truncate(engine)


async def _truncate(engine: AsyncEngine) -> None:
    statement = text("TRUNCATE TABLE " + ", ".join(_TABLES_IN_TRUNCATION_ORDER) + " RESTART IDENTITY CASCADE")
    async with engine.begin() as connection:
        await connection.execute(statement)


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine, clean_database: None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def uow(session_factory: async_sessionmaker[AsyncSession]) -> AuthUnitOfWork:
    return AuthUnitOfWork(session_factory)
