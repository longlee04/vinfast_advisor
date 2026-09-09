"""PostgreSQL integrity tests for customer-turn bottleneck signals."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

SESSION_ID = UUID("20000000-0000-0000-0000-000000000001")
CURRENT_TURN_ID = UUID("20000000-0000-0000-0000-000000000002")
ANCHOR_TURN_ID = UUID("20000000-0000-0000-0000-000000000003")
OTHER_SESSION_ID = UUID("20000000-0000-0000-0000-000000000004")
OTHER_SESSION_ANCHOR_TURN_ID = UUID("20000000-0000-0000-0000-000000000005")


async def _seed_outcomes(engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO conversation_sessions "
                "(session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) "
                "VALUES (:session_id, 'customer', 'ACTIVE', :now, :now, :now, :now)"
            ),
            {"session_id": SESSION_ID, "now": now},
        )
        await connection.execute(
            text(
                "INSERT INTO conversation_sessions "
                "(session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) "
                "VALUES (:session_id, 'other-customer', 'ACTIVE', :now, :now, :now, :now)"
            ),
            {"session_id": OTHER_SESSION_ID, "now": now},
        )
        for outcome_id, session_id, client_turn_id, turn_number in (
            (uuid4(), SESSION_ID, ANCHOR_TURN_ID, 1),
            (uuid4(), SESSION_ID, CURRENT_TURN_ID, 2),
            (uuid4(), OTHER_SESSION_ID, OTHER_SESSION_ANCHOR_TURN_ID, 1),
        ):
            await connection.execute(
                text(
                    "INSERT INTO conversation_turn_outcomes "
                    "(outcome_id, session_id, client_turn_id, turn_number, status, created_at, updated_at) "
                    "VALUES (:outcome_id, :session_id, :client_turn_id, :turn_number, "
                    "'COMPLETED', :now, :now)"
                ),
                {
                    "outcome_id": outcome_id,
                    "session_id": session_id,
                    "client_turn_id": client_turn_id,
                    "turn_number": turn_number,
                    "now": now,
                },
            )


def _insert_signal_sql() -> str:
    return (
        "INSERT INTO conversation_turn_bottlenecks "
        "(signal_id, session_id, client_turn_id, anchor_client_turn_id, label, evidence_quote, "
        "model_name, prompt_version, status, claimed_by, claimed_at, lease_expires_at, "
        "created_at, updated_at) VALUES "
        "(:signal_id, :session_id, :client_turn_id, :anchor_client_turn_id, :label, 'quote', "
        "'model', 'v1', :status, :claimed_by, :claimed_at, :lease_expires_at, :now, :now)"
    )


def _valid_signal() -> dict[str, str | UUID | datetime | None]:
    return {
        "signal_id": uuid4(),
        "session_id": SESSION_ID,
        "client_turn_id": CURRENT_TURN_ID,
        "anchor_client_turn_id": ANCHOR_TURN_ID,
        "label": "PRICE",
        "status": "PENDING",
        "claimed_by": None,
        "claimed_at": None,
        "lease_expires_at": None,
        "now": datetime.now(UTC),
    }


@pytest.mark.asyncio
async def test_valid_signal_cascades_when_current_outcome_deleted(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    await _seed_outcomes(migrated_engine)
    values = _valid_signal()

    # When
    async with migrated_engine.begin() as connection:
        await connection.execute(text(_insert_signal_sql()), values)
        await connection.execute(
            text(
                "DELETE FROM conversation_turn_outcomes "
                "WHERE session_id = :session_id AND client_turn_id = :client_turn_id"
            ),
            values,
        )

    # Then
    async with migrated_engine.connect() as connection:
        count = await connection.scalar(text("SELECT count(*) FROM conversation_turn_bottlenecks"))
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "invalid_value"),
    [
        ("label", "NONE"),
        ("status", "UNAVAILABLE"),
        ("anchor_client_turn_id", OTHER_SESSION_ANCHOR_TURN_ID),
    ],
)
async def test_signal_rejects_invalid_label_status_or_anchor(
    migrated_engine: AsyncEngine,
    clean_agent_database: None,
    override: str,
    invalid_value: str | UUID,
) -> None:
    # Given
    await _seed_outcomes(migrated_engine)
    values = _valid_signal()
    values[override] = invalid_value

    # When / Then
    with pytest.raises(IntegrityError):
        async with migrated_engine.begin() as connection:
            await connection.execute(text(_insert_signal_sql()), values)


@pytest.mark.asyncio
async def test_signal_rejects_duplicate_current_turn(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given
    await _seed_outcomes(migrated_engine)
    first = _valid_signal()
    duplicate = {**first, "signal_id": uuid4()}

    # When / Then
    with pytest.raises(IntegrityError):
        async with migrated_engine.begin() as connection:
            await connection.execute(text(_insert_signal_sql()), first)
            await connection.execute(text(_insert_signal_sql()), duplicate)


@pytest.mark.asyncio
async def test_signal_rejects_partial_claim_triple(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    # Given
    await _seed_outcomes(migrated_engine)
    values = {**_valid_signal(), "claimed_by": "advisor"}

    # When / Then
    with pytest.raises(IntegrityError):
        async with migrated_engine.begin() as connection:
            await connection.execute(text(_insert_signal_sql()), values)
