"""Alembic environment for the Locations schema.

URL is read from LOCATIONS_DATABASE_URL at run time, falling back to
AUTH_DATABASE_URL for single-database local setups. target_metadata is
LocationsBase.metadata, so an autogenerate run can only ever emit changes
against the `locations` table.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.locations.infrastructure.models import LocationsBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = LocationsBase.metadata

VERSION_TABLE = "locations_alembic_version"


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Only include tables that belong to LocationsBase.metadata."""
    if type_ == "table":
        return name in target_metadata.tables
    return True


def _database_url() -> str:
    url = os.environ.get("LOCATIONS_DATABASE_URL", "").strip()
    if not url:
        url = os.environ.get("AUTH_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "LOCATIONS_DATABASE_URL (or AUTH_DATABASE_URL) is required to run "
            "Locations migrations; see .env.example"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        version_table=VERSION_TABLE,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        version_table=VERSION_TABLE,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
