"""Alembic environment for Agent schema."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.agents.models import AgentBase

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = AgentBase.metadata


def _database_url() -> str:
    url = os.environ.get("AGENT_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("AGENT_DATABASE_URL is required to run Agent migrations")
    if url.split("://", 1)[0] != "postgresql+asyncpg":
        raise RuntimeError("Agent migrations require postgresql+asyncpg")
    return url


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True, version_table="agent_alembic_version"
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    raise RuntimeError("Agent offline migrations are not supported")
run_migrations_online()
