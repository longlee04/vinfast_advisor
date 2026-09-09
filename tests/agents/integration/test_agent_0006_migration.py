"""Acceptance tests for the A9-1 ``agent_0006`` migration and the ``funnel_metrics`` view."""

from collections.abc import Sequence
from datetime import UTC, datetime
from subprocess import CompletedProcess
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.agents.models import (
    AgentRunRow,
    ConversationSessionRow,
    ConversationSlotRow,
    ReviewQueueRow,
)
from src.agents.models import TestDriveBookingRow as BookingRow
from tests.agents.integration.conftest import run_alembic

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
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


async def _view_exists(database_url: str) -> bool:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return bool(await connection.scalar(text("SELECT to_regclass('public.funnel_metrics') IS NOT NULL")))
    finally:
        await engine.dispose()


async def _prepare_agent_0005(database_url: str) -> None:
    for configuration, variable, revision in PREREQUISITE_MIGRATIONS:
        _assert_alembic_succeeds(run_alembic(database_url, configuration, variable, "upgrade", revision))

    current_revision = await _agent_revision(database_url)
    command = "upgrade" if current_revision is None else "downgrade"
    if current_revision != "agent_0005":
        _assert_alembic_succeeds(
            run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", command, "agent_0005")
        )


def _restore_agent_head(database_url: str) -> None:
    _assert_alembic_succeeds(run_alembic(database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head"))


@pytest.mark.asyncio
async def test_agent_0006_upgrade_creates_the_funnel_metrics_view(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0005(agent_database_url)

    try:
        # When
        completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "agent_0006")

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0006"
        assert await _view_exists(agent_database_url) is True
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0006_downgrade_returns_to_the_previous_revision(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0005(agent_database_url)
    _assert_alembic_succeeds(
        run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "agent_0006")
    )

    try:
        # When
        completed = run_alembic(
            agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0005"
        )

        # Then
        _assert_alembic_succeeds(completed)
        assert await _agent_revision(agent_database_url) == "agent_0005"
    finally:
        _restore_agent_head(agent_database_url)


@pytest.mark.asyncio
async def test_agent_0006_downgrade_actually_drops_the_view(agent_database_url: str) -> None:
    # Given
    await _prepare_agent_0005(agent_database_url)
    _assert_alembic_succeeds(
        run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "agent_0006")
    )

    try:
        # When
        _assert_alembic_succeeds(
            run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0005")
        )

        # Then — the view is gone, not merely left behind while the revision moved
        assert await _view_exists(agent_database_url) is False
    finally:
        _restore_agent_head(agent_database_url)


async def _seed_funnel(engine: AsyncEngine) -> None:
    """Four sessions, each stopping at a different stage of the funnel.

    Session 4 has a queue item that is still ``PENDING``: without it, dropping the
    ``status = 'APPROVED'`` filter from the view would still produce the right
    number and the cross-check would pass on a broken view.
    """
    async with engine.begin() as connection:
        for index, customer_id in enumerate(("customer-1", "customer-2", "customer-3", "customer-4")):
            session_id = uuid4()
            await connection.execute(
                insert(ConversationSessionRow).values(
                    session_id=session_id,
                    customer_id=customer_id,
                    started_at=NOW,
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            if index == 0:
                continue  # session 1 stops at "started"

            # sessions 2 and 3 captured a need profile
            await connection.execute(
                insert(ConversationSlotRow).values(
                    session_id=session_id,
                    slot_name="budget_max_vnd",
                    slot_value_number=700000000,
                    confirmed_at=NOW,
                    updated_at=NOW,
                )
            )
            run_id = uuid4()
            await connection.execute(
                insert(AgentRunRow).values(
                    run_id=run_id,
                    session_id=session_id,
                    state="PENDING_REVIEW" if index == 1 else "APPROVED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            if index == 1:
                continue  # session 2 stops at "has a recommendation"

            # session 4 reached the queue but is still waiting for review
            await connection.execute(
                insert(ReviewQueueRow).values(
                    review_id=uuid4(),
                    session_id=session_id,
                    run_id=run_id,
                    content="ban nhap",
                    status="APPROVED" if index == 2 else "PENDING",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            if index == 3:
                continue
            await connection.execute(
                insert(BookingRow).values(
                    booking_id=uuid4(),
                    customer_id=customer_id,
                    vehicle_id=uuid4(),
                    showroom="VinFast Long Bien",
                    scheduled_at=NOW,
                    status="REQUESTED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column,expected",
    [
        ("sessions_started", 4),
        ("sessions_with_profile", 3),
        ("sessions_with_recommendation", 3),
        ("sessions_approved", 1),
        ("sessions_booked", 1),
    ],
)
async def test_funnel_metrics_matches_the_source_tables(
    migrated_engine: AsyncEngine, clean_agent_database: None, column: str, expected: int
) -> None:
    # Given
    await _seed_funnel(migrated_engine)

    # When
    async with migrated_engine.connect() as connection:
        value = await connection.scalar(text(f"SELECT {column} FROM funnel_metrics"))

    # Then
    assert value == expected


@pytest.mark.asyncio
async def test_funnel_metrics_is_empty_when_no_session_exists(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — negative case: nothing seeded at all
    # When
    async with migrated_engine.connect() as connection:
        rows = (await connection.execute(text("SELECT * FROM funnel_metrics"))).all()

    # Then
    assert rows == []


@pytest.mark.asyncio
async def test_a_session_without_any_run_counts_as_zero_not_null(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — negative case: a bare session must not turn counters into NULL
    async with migrated_engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=uuid4(),
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )

    # When
    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT sessions_with_profile, sessions_with_recommendation, "
                    "sessions_approved, sessions_booked FROM funnel_metrics"
                )
            )
        ).one()

    # Then
    assert list(row) == [0, 0, 0, 0]


@pytest.mark.asyncio
async def test_source_counts_confirm_the_view(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given — cross-check: the view must agree with plain counts on the source tables
    await _seed_funnel(migrated_engine)

    # When
    async with migrated_engine.connect() as connection:
        view_started = await connection.scalar(text("SELECT sessions_started FROM funnel_metrics"))
        source_rows = (await connection.execute(select(ConversationSessionRow.session_id))).all()

    # Then
    assert view_started == len(source_rows)
