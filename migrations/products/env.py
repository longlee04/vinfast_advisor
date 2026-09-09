"""Alembic environment for the Product schema.

URL is read from PRODUCT_DATABASE_URL at run time.
target_metadata is ProductBase.metadata — only product_* tables.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.products.infrastructure.models import ProductBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ProductBase.metadata


def _database_url() -> str:
    url = os.environ.get("PRODUCT_DATABASE_URL", "").strip()
    if not url:
        # fall back to AUTH_DATABASE_URL for convenience in single-db setups
        url = os.environ.get("AUTH_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "PRODUCT_DATABASE_URL (or AUTH_DATABASE_URL) is required to run "
            "Product migrations; see .env.example"
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
        version_table="alembic_version_products",
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        version_table="alembic_version_products",
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
