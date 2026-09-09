"""Alembic environment for the Document schema."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.document.infrastructure.models import DocumentBase
from src.images.infrastructure.models import ImageRow  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DocumentBase.metadata
_REQUIRED_DRIVER = "postgresql+asyncpg"


def _database_url() -> str:
    url = os.environ.get("DOCUMENT_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DOCUMENT_DATABASE_URL is required to run Document migrations")
    driver = url.split("://", 1)[0]
    if driver != _REQUIRED_DRIVER:
        raise RuntimeError(f"Document migrations require {_REQUIRED_DRIVER}, got {driver!r}")
    return url


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table="document_alembic_version",
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
    raise RuntimeError("Document offline migrations are not supported")
run_migrations_online()
