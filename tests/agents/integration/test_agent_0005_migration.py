"""Acceptance tests for the A8-1 ``agent_0005`` migration."""

from collections.abc import Sequence
from subprocess import CompletedProcess

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.agents.integration.conftest import run_alembic

AGENT_0005_TABLES = {"test_drive_bookings", "internal_notices", "notice_reads"}
AGENT_0004_TABLES = {"review_queue"}
PREREQUISITE_MIGRATIONS: Sequence[tuple[str, str, str]] = (
    ("alembic-auth.ini", "AUTH_DATABASE_URL", "head"),
    ("alembic-document.ini", "DOCUMENT_DATABASE_URL", "4d0cument0001"),
    ("alembic-products.ini", "PRODUCT_DATABASE_URL", "head"),
    ("alembic-document.ini", "DOCUMENT_DATABASE_URL", "head"),
)


def _assert_alembic_succeeds(completed: CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stderr


async def _agent_revision(database_url: str) -> str | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            version_table_exists = await connection.scalar(
                text("SELECT to_regclass('public.agent_alembic_version') IS NOT NULL")
            )
            if not version_table_exists:
                return None
            return await connection.scalar(text("SELECT version_num FROM agent_alembic_version"))
    finally:
        await engine.dispose()


async def _agent_table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    finally:
        await engine.dispose()


async def _prepare_agent_0004(database_url: str) -> None:
    for configuration, variable, revision in PREREQUISITE_MIGRATIONS:
        _assert_alembic_succeeds(run_alembic(database_url, configuration, variable, "upgrade", revision))

    current_revision = await _agent_revision(database_url)
    command = "upgrade" if current_revision is None else "downgrade"
    if current_revision != "agent_0004":
        _assert_alembic_succeeds(
            run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", command, "agent_0004")
        )


def _restore_agent_head(database_url: str) -> None:
    _assert_alembic_succeeds(run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head"))


@pytest.mark.asyncio
async def test_agent_0005_upgrade_creates_booking_and_notice_tables(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0004(agent_database_url)

    try:
        # When
        completed = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "agent_0005",
        )

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0005"
        assert AGENT_0005_TABLES <= await _agent_table_names(agent_database_url)
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0005_downgrade_removes_only_booking_and_notice_tables(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0004(agent_database_url)
    _assert_alembic_succeeds(
        run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "agent_0005",
        )
    )

    try:
        # When
        completed = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "downgrade",
            "agent_0004",
        )

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0004"
        table_names = await _agent_table_names(agent_database_url)
        assert AGENT_0005_TABLES.isdisjoint(table_names)
        assert AGENT_0004_TABLES <= table_names
    finally:
        _restore_agent_head(agent_database_url)
