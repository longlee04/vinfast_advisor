"""Acceptance tests for the ``agent_0024`` snapshot migration."""

from collections.abc import Sequence
from datetime import UTC, datetime
from subprocess import CompletedProcess
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.agents.integration.conftest import expected_agent_head, run_alembic

REVIEW_QUEUE_COLUMNS = {
    "profile_snapshot",
    "handoff_requested",
    "first_viewed_at",
    "offer_suggestion_ignored",
}
REVIEW_QUEUE_INDEXES = {"ix_review_queue_offer_state"}
CONVERSATION_SESSION_INDEXES = {"ix_conversation_sessions_state_last_activity"}
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


async def _column_names(database_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: {column["name"] for column in inspect(sync).get_columns(table_name)}
            )
    finally:
        await engine.dispose()


async def _index_names(database_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: {index["name"] for index in inspect(sync).get_indexes(table_name)}
            )
    finally:
        await engine.dispose()


async def _prepare_agent_0018(database_url: str) -> None:
    for configuration, variable, revision in PREREQUISITE_MIGRATIONS:
        _assert_alembic_succeeds(run_alembic(database_url, configuration, variable, "upgrade", revision))

    current_revision = await _agent_revision(database_url)
    if current_revision != "agent_0018":
        command = "upgrade" if current_revision is None else "downgrade"
        _assert_alembic_succeeds(
            run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", command, "agent_0018")
        )


def _restore_agent_head(database_url: str) -> None:
    _assert_alembic_succeeds(run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head"))


async def _create_legacy_review_row(database_url: str) -> None:
    """Insert one row without the new columns, as if written before agent_0024."""
    engine = create_async_engine(database_url)
    session_id = uuid4()
    run_id = uuid4()
    review_id = uuid4()
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO conversation_sessions (session_id, customer_id, status, started_at, "
                    "last_activity_at, created_at, updated_at) VALUES (:session_id, :customer_id, "
                    "'ACTIVE', :now, :now, :now, :now)"
                ),
                {"session_id": session_id, "customer_id": "legacy-customer", "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO agent_runs (run_id, session_id, state, created_at, updated_at) "
                    "VALUES (:run_id, :session_id, 'PENDING_REVIEW', :now, :now)"
                ),
                {"run_id": run_id, "session_id": session_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO review_queue (review_id, session_id, run_id, content, status, "
                    "created_at, updated_at) VALUES (:review_id, :session_id, :run_id, 'content', "
                    "'PENDING', :now, :now)"
                ),
                {
                    "review_id": review_id,
                    "session_id": session_id,
                    "run_id": run_id,
                    "now": now,
                },
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_agent_0024_upgrade_adds_columns_and_indexes(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0018(agent_database_url)

    try:
        # When
        completed = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "agent_0024",
        )

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0024"

        assert REVIEW_QUEUE_COLUMNS <= await _column_names(agent_database_url, "review_queue")
        assert REVIEW_QUEUE_INDEXES <= await _index_names(agent_database_url, "review_queue")
        assert CONVERSATION_SESSION_INDEXES <= await _index_names(agent_database_url, "conversation_sessions")
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0024_downgrade_removes_columns_and_indexes(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0018(agent_database_url)
    _assert_alembic_succeeds(
        run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "agent_0024",
        )
    )

    try:
        # When
        completed = run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "downgrade",
            "agent_0018",
        )

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0018"
        assert REVIEW_QUEUE_COLUMNS.isdisjoint(await _column_names(agent_database_url, "review_queue"))
        assert REVIEW_QUEUE_INDEXES.isdisjoint(await _index_names(agent_database_url, "review_queue"))
        assert CONVERSATION_SESSION_INDEXES.isdisjoint(await _index_names(agent_database_url, "conversation_sessions"))
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0024_legacy_row_gets_defaults(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0018(agent_database_url)
    _assert_alembic_succeeds(
        run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "agent_0024",
        )
    )

    try:
        # When
        await _create_legacy_review_row(agent_database_url)

        # Then: pre-migration row backfilled with defaults, snapshot NULL.
        engine = create_async_engine(agent_database_url)
        try:
            async with engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT profile_snapshot, handoff_requested, first_viewed_at, "
                                "offer_suggestion_ignored FROM review_queue"
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
            assert row["profile_snapshot"] is None
            assert row["handoff_requested"] is False
            assert row["first_viewed_at"] is None
            assert row["offer_suggestion_ignored"] is False
        finally:
            await engine.dispose()
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0024_upgrade_is_idempotent_on_head(agent_database_url: str) -> None:
    # Given: full agent head already applied by the conftest session fixture.
    _assert_alembic_succeeds(
        run_alembic(
            agent_database_url,
            "alembic-agent.ini",
            "AGENT_DATABASE_URL",
            "upgrade",
            "head",
        )
    )

    # When: re-running upgrade on an already-head database.
    completed = run_alembic(
        agent_database_url,
        "alembic-agent.ini",
        "AGENT_DATABASE_URL",
        "upgrade",
        "head",
    )

    # Then: no-op, no error, and current head remains agent_0025.
    _assert_alembic_succeeds(completed)
    assert await _agent_revision(agent_database_url) == expected_agent_head()
