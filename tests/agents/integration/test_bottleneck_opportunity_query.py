"""PostgreSQL query tests for confirmed-signal sales opportunities."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.clock import SystemClock
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import (
    ConversationSessionRow,
    ConversationSlotRow,
    ConversationTurnBottleneckRow,
    ConversationTurnOutcomeRow,
)

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)


async def _seed_session(
    engine: AsyncEngine,
    *,
    customer_id: str,
    activity: datetime,
    status: str = "ACTIVE",
) -> UUID:
    session_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id=customer_id,
                status=status,
                started_at=activity,
                last_activity_at=activity,
                created_at=activity,
                updated_at=activity,
            )
        )
    return session_id


async def _seed_signal(
    engine: AsyncEngine,
    session_id: UUID,
    *,
    turn_number: int,
    label: Bottleneck,
    status: str = "CORRECT",
) -> None:
    client_turn_id = uuid4()
    anchor_turn_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationTurnOutcomeRow),
            [
                {
                    "outcome_id": uuid4(),
                    "session_id": session_id,
                    "client_turn_id": anchor_turn_id,
                    "turn_number": turn_number * 2 - 1,
                    "status": "COMPLETED",
                    "recommendations": [{"vehicle_id": "vf8"}],
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "outcome_id": uuid4(),
                    "session_id": session_id,
                    "client_turn_id": client_turn_id,
                    "turn_number": turn_number * 2,
                    "status": "COMPLETED",
                    "recommendations": [],
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )
        await connection.execute(
            insert(ConversationTurnBottleneckRow).values(
                signal_id=uuid4(),
                session_id=session_id,
                client_turn_id=client_turn_id,
                anchor_client_turn_id=anchor_turn_id,
                label=label.value,
                evidence_quote=f"evidence-{turn_number}",
                model_name="test-model",
                prompt_version="v1",
                status=status,
                created_at=NOW + timedelta(minutes=turn_number),
                updated_at=NOW + timedelta(minutes=turn_number),
            )
        )


@pytest.mark.asyncio
async def test_query_requires_distinct_correct_labels_and_active_24h_session(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    qualifying = await _seed_session(migrated_engine, customer_id="qualified", activity=NOW - timedelta(minutes=5))
    duplicate = await _seed_session(migrated_engine, customer_id="duplicate", activity=NOW - timedelta(minutes=10))
    stale = await _seed_session(migrated_engine, customer_id="stale", activity=NOW - timedelta(hours=25))
    inactive = await _seed_session(
        migrated_engine,
        customer_id="inactive",
        activity=NOW,
        status="COMPLETED",
    )
    for session_id in (qualifying, stale, inactive):
        await _seed_signal(migrated_engine, session_id, turn_number=1, label=Bottleneck.PRICE)
        await _seed_signal(migrated_engine, session_id, turn_number=2, label=Bottleneck.RANGE)
    await _seed_signal(migrated_engine, duplicate, turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, duplicate, turn_number=2, label=Bottleneck.PRICE)
    await _seed_signal(
        migrated_engine,
        duplicate,
        turn_number=3,
        label=Bottleneck.RANGE,
        status="PENDING",
    )
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    # When
    async with factory() as session:
        rows = await SqlAlchemyBottleneckSignalRepository(session, SystemClock()).list_opportunities(
            since=NOW - timedelta(hours=24),
            limit=100,
        )

    # Then
    assert [row.session_id for row in rows] == [qualifying]
    assert rows[0].customer_id == "qualified"
    assert [item.label for item in rows[0].evidence] == [
        Bottleneck.PRICE,
        Bottleneck.RANGE,
    ]


@pytest.mark.asyncio
async def test_query_and_slots_batch_use_at_most_two_statements_for_100_sessions(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    session_ids: list[UUID] = []
    for position in range(100):
        session_id = await _seed_session(
            migrated_engine,
            customer_id=f"customer-{position}",
            activity=NOW - timedelta(seconds=position),
        )
        session_ids.append(session_id)
        await _seed_signal(migrated_engine, session_id, turn_number=1, label=Bottleneck.PRICE)
        await _seed_signal(migrated_engine, session_id, turn_number=2, label=Bottleneck.RANGE)
    async with migrated_engine.begin() as connection:
        await connection.execute(
            insert(ConversationSlotRow),
            [
                {
                    "session_id": session_id,
                    "slot_name": "color_preference",
                    "slot_value_text": "red",
                    "confirmed_at": NOW,
                    "updated_at": NOW,
                }
                for session_id in session_ids
            ],
        )
    statements = 0

    def count_statement(
        _connection: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal statements
        statements += 1

    event.listen(migrated_engine.sync_engine, "before_cursor_execute", count_statement)
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    # When
    try:
        async with factory() as session:
            repository = SqlAlchemyBottleneckSignalRepository(session, SystemClock())
            rows = await repository.list_opportunities(
                since=NOW - timedelta(hours=24),
                limit=100,
            )
            slots = await repository.load_opportunity_slots(tuple(row.session_id for row in rows))
    finally:
        event.remove(migrated_engine.sync_engine, "before_cursor_execute", count_statement)

    # Then
    assert len(rows) == 100
    assert len(slots) == 100
    assert statements <= 2
    assert [row.session_id for row in rows] == session_ids
