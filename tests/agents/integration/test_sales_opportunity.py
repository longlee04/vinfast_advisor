"""Integration tests for set-based SalesOpportunityService."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.clock import SystemClock
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import ConversationSessionRow
from src.agents.services.sales_opportunity import SalesOpportunityService
from tests.agents.integration.test_bottleneck_opportunity_query import _seed_signal

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


async def _seed_session(
    engine: AsyncEngine,
    *,
    customer_id: str,
    last_activity_at: datetime,
    status: str = "ACTIVE",
) -> str:
    session_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id=customer_id,
                status=status,
                started_at=NOW,
                last_activity_at=last_activity_at,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return session_id


async def _service(engine: AsyncEngine) -> SalesOpportunityService:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    return SalesOpportunityService(repository=SqlAlchemyBottleneckSignalRepository(session, SystemClock()))


@pytest.mark.asyncio
async def test_list_opportunities_filters_sessions_with_2_plus_bottlenecks(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    single = await _seed_session(migrated_engine, customer_id="c-b", last_activity_at=NOW)
    qualified = await _seed_session(migrated_engine, customer_id="c-c", last_activity_at=NOW)
    await _seed_signal(migrated_engine, UUID(single), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(qualified), turn_number=1, label=Bottleneck.PRICE)
    await _seed_signal(migrated_engine, UUID(qualified), turn_number=2, label=Bottleneck.RANGE)
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    # When
    async with factory() as session:
        service = SalesOpportunityService(SqlAlchemyBottleneckSignalRepository(session, SystemClock()))
        opportunities = await service.list_opportunities(NOW)

    # Then
    assert [item.session_id for item in opportunities] == [qualified]
    assert set(opportunities[0].bottlenecks) == {"PRICE", "RANGE"}


@pytest.mark.asyncio
async def test_list_opportunities_skips_inactive_and_stale_sessions(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    archived = await _seed_session(
        migrated_engine,
        customer_id="c-a",
        last_activity_at=NOW,
        status="COMPLETED",
    )
    stale = await _seed_session(
        migrated_engine,
        customer_id="c-b",
        last_activity_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    for session_id in (archived, stale):
        await _seed_signal(migrated_engine, UUID(session_id), turn_number=1, label=Bottleneck.PRICE)
        await _seed_signal(migrated_engine, UUID(session_id), turn_number=2, label=Bottleneck.RANGE)
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    # When
    async with factory() as session:
        service = SalesOpportunityService(SqlAlchemyBottleneckSignalRepository(session, SystemClock()))
        opportunities = await service.list_opportunities(NOW)

    # Then
    assert opportunities == []
