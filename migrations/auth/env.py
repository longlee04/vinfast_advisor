"""Alembic environment for the Auth schema.

Two properties matter here:

* The database URL comes from `AUTH_DATABASE_URL` at run time, never from
  `alembic-auth.ini`, so no credential is committed.
* `target_metadata` is `AuthBase.metadata`, which contains only `auth_*` tables.
  An autogenerate run therefore cannot emit a change against a legacy table even
  if a legacy model is imported somewhere in the process.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.auth.infrastructure.models import AuthBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = AuthBase.metadata

REQUIRED_DRIVER = "postgresql+asyncpg"


def _database_url() -> str:
    """Return the Auth database URL, rejecting a non-PostgreSQL target.

    The driver check is repeated here rather than trusted from settings: a
    migration can be run by an operator straight from a shell, bypassing
    application startup validation entirely.
    """
    url = os.environ.get("AUTH_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "AUTH_DATABASE_URL is required to run Auth migrations; "
            "see .env.example for the local value"
        )
    driver = url.split("://", 1)[0]
    if driver != REQUIRED_DRIVER:
        # Report only the driver — the rest of the URL holds the password.
        raise RuntimeError(
            f"Auth migrations require the {REQUIRED_DRIVER} driver, got {driver!r}; "
            f"Auth never migrates a SQLite or synchronous target"
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
