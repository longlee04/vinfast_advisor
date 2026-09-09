"""Create and guard disposable PostgreSQL databases for integration tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

_DATABASE_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
_UUID_HEX_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_PROTECTED_DATABASE_NAMES = frozenset(
    {
        "p150_auth",
        "p150_dev",
        "p150_staging",
        "postgres",
        "template0",
        "template1",
    }
)


class UnsafeTestDatabaseError(RuntimeError):
    """Raised before SQL when a database is not proven disposable."""


@dataclass(frozen=True, slots=True)
class TemporaryPostgresDatabase:
    """Identity and URLs for one fixture-owned PostgreSQL database."""

    admin_url: str
    database_url: str
    database_name: str
    expected_prefix: str


def database_name_from_url(database_url: str) -> str:
    """Return a validated database name from a SQLAlchemy PostgreSQL URL."""
    try:
        parsed = make_url(database_url)
    except ArgumentError as error:
        raise UnsafeTestDatabaseError("test database URL is invalid") from error
    if parsed.drivername not in {"postgresql", "postgresql+asyncpg"}:
        raise UnsafeTestDatabaseError("test database URL must use PostgreSQL")
    if not parsed.host:
        raise UnsafeTestDatabaseError("test database URL must include a host")
    database_name = (parsed.database or "").strip()
    if not database_name or not _DATABASE_NAME_PATTERN.fullmatch(database_name):
        raise UnsafeTestDatabaseError("test database URL has an unsafe database name")
    return database_name


def database_url_with_name(database_url: str, database_name: str) -> str:
    """Replace only the database component of a PostgreSQL URL."""
    database_name_from_url(database_url)
    if not _DATABASE_NAME_PATTERN.fullmatch(database_name):
        raise UnsafeTestDatabaseError("replacement database name is unsafe")
    return make_url(database_url).set(database=database_name).render_as_string(hide_password=False)


def generate_test_database_name(expected_prefix: str) -> str:
    """Generate a PostgreSQL-safe fixture-owned database name."""
    _validate_expected_prefix(expected_prefix)
    return f"{expected_prefix}{uuid4().hex}"


def assert_disposable_database_name(
    database_name: str,
    *,
    expected_prefix: str,
    owned_database_name: str | None = None,
) -> None:
    """Reject protected, malformed, wrongly scoped, or non-owned databases."""
    _validate_expected_prefix(expected_prefix)
    normalized = database_name.strip().lower()
    if normalized in _PROTECTED_DATABASE_NAMES or "prod" in normalized:
        raise UnsafeTestDatabaseError(f"database {normalized!r} is protected")
    if not _DATABASE_NAME_PATTERN.fullmatch(normalized):
        raise UnsafeTestDatabaseError("database name contains unsafe characters")
    if not normalized.startswith(expected_prefix):
        raise UnsafeTestDatabaseError(
            f"database must start with the test prefix {expected_prefix!r}"
        )
    suffix = normalized.removeprefix(expected_prefix)
    if not _UUID_HEX_PATTERN.fullmatch(suffix):
        raise UnsafeTestDatabaseError("database name must end with a generated UUID")
    if owned_database_name is not None and normalized != owned_database_name:
        raise UnsafeTestDatabaseError("refusing to mutate a database not owned by this fixture")


def assert_disposable_database_url(
    database_url: str,
    *,
    expected_prefix: str,
    owned_database_name: str | None = None,
) -> str:
    """Validate a disposable database URL and return its database name."""
    database_name = database_name_from_url(database_url)
    assert_disposable_database_name(
        database_name,
        expected_prefix=expected_prefix,
        owned_database_name=owned_database_name,
    )
    return database_name


async def create_temporary_database(
    admin_url: str,
    *,
    expected_prefix: str,
) -> TemporaryPostgresDatabase:
    """Create one fixture-owned database through a PostgreSQL maintenance URL."""
    database_name_from_url(admin_url)
    database_name = generate_test_database_name(expected_prefix)
    assert_disposable_database_name(database_name, expected_prefix=expected_prefix)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))
    finally:
        await engine.dispose()
    database_url = database_url_with_name(admin_url, database_name)
    return TemporaryPostgresDatabase(
        admin_url=admin_url,
        database_url=database_url,
        database_name=database_name,
        expected_prefix=expected_prefix,
    )


async def assert_connection_uses_temporary_database(
    connection: AsyncConnection,
    database: TemporaryPostgresDatabase,
) -> None:
    """Verify the live connection targets exactly the fixture-owned database."""
    assert_disposable_database_url(
        database.database_url,
        expected_prefix=database.expected_prefix,
        owned_database_name=database.database_name,
    )
    current_database = await connection.scalar(text("SELECT current_database()"))
    if current_database != database.database_name:
        raise UnsafeTestDatabaseError(
            "live connection does not target the fixture-owned test database"
        )


async def drop_temporary_database(database: TemporaryPostgresDatabase) -> None:
    """Terminate remaining clients and drop exactly one fixture-owned database."""
    assert_disposable_database_url(
        database.database_url,
        expected_prefix=database.expected_prefix,
        owned_database_name=database.database_name,
    )
    engine = create_async_engine(database.admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database.database_name},
            )
            await connection.execute(text(f'DROP DATABASE "{database.database_name}"'))
    finally:
        await engine.dispose()


def _validate_expected_prefix(expected_prefix: str) -> None:
    if not re.fullmatch(r"p150_[a-z0-9]+_test_", expected_prefix):
        raise UnsafeTestDatabaseError("test database prefix is invalid")
