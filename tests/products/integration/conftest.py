"""Real PostgreSQL fixtures for Product module integration tests.

The schema is created by running the real Alembic command, never
``metadata.create_all``, so tests exercise the migration chain a deployment
actually runs.
"""

import os
import socket
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
PRODUCT_TEST_DATABASE_URL = os.environ.get("PRODUCT_DATABASE_URL", "").strip() or DEFAULT_TEST_DATABASE_URL
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TEST_DATABASE_PREFIX = "p150_product_test_"


def _server_is_reachable(database_url: str) -> bool:
    parts = urlsplit(database_url)
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


def run_product_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one isolated Product migration command."""
    environment = os.environ.copy()
    environment["PRODUCT_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic-products.ini", *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _database_url_parts(database_url: str) -> SplitResult:
    return urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))


def _database_url_with_name(database_url: str, database_name: str) -> str:
    parts = _database_url_parts(database_url)
    replaced = urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, parts.fragment))
    return replaced.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _create_test_database() -> tuple[str, str]:
    parts = _database_url_parts(PRODUCT_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    database_name = f"{_TEST_DATABASE_PREFIX}{uuid.uuid4().hex}"
    engine = create_async_engine(
        maintenance_url.replace("postgresql://", "postgresql+asyncpg://", 1),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))
    finally:
        await engine.dispose()
    return _database_url_with_name(PRODUCT_TEST_DATABASE_URL, database_name), database_name


async def _drop_test_database(database_name: str) -> None:
    parts = _database_url_parts(PRODUCT_TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    engine = create_async_engine(
        maintenance_url.replace("postgresql://", "postgresql+asyncpg://", 1),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS false'))
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE "{database_name}"'))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def product_database_url() -> AsyncIterator[str]:
    """Create and remove an isolated PostgreSQL database for Product tests."""
    if not _server_is_reachable(PRODUCT_TEST_DATABASE_URL):
        pytest.skip("PostgreSQL is not reachable; start it with 'docker compose up -d postgres'")
    database_url, database_name = await _create_test_database()
    try:
        yield database_url
    finally:
        await _drop_test_database(database_name)


@pytest_asyncio.fixture
async def product_transition_database_url() -> AsyncIterator[str]:
    """Create isolated database for one Product migration transition test."""
    if not _server_is_reachable(PRODUCT_TEST_DATABASE_URL):
        pytest.skip("PostgreSQL is not reachable; start it with 'docker compose up -d postgres'")
    database_url, database_name = await _create_test_database()
    try:
        yield database_url
    finally:
        await _drop_test_database(database_name)


@pytest_asyncio.fixture(scope="session")
async def _product_migrations_applied(product_database_url: str) -> None:
    """Apply the full Product migration chain once per session."""
    completed = run_product_alembic(product_database_url, "upgrade", "head")
    assert completed.returncode == 0, completed.stderr


@pytest_asyncio.fixture
async def migrated_product_engine(
    product_database_url: str, _product_migrations_applied: None
) -> AsyncIterator[AsyncEngine]:
    """Fresh engine bound to the already-migrated schema for each test."""
    engine = create_async_engine(product_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def product_session(
    migrated_product_engine: AsyncEngine, clean_product_database: None
) -> AsyncIterator[AsyncSession]:
    """One transaction for Product integration assertions."""
    session_factory = async_sessionmaker(migrated_product_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        yield session


@pytest_asyncio.fixture
async def product_session_factory(
    migrated_product_engine: AsyncEngine, clean_product_database: None
) -> async_sessionmaker[AsyncSession]:
    """Independent session source bound to the migrated engine."""
    return async_sessionmaker(migrated_product_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def clean_product_database(migrated_product_engine: AsyncEngine) -> AsyncIterator[None]:
    """Remove Product rows before and after each test."""
    tables = (
        "offer_adjustment_log, offer_adjustment_policies, promotion_vehicles, promotions, "
        "tco_assumptions, battery_policies, motorbikes, cars, vehicles"
    )
    async with migrated_product_engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    try:
        yield
    finally:
        async with migrated_product_engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
