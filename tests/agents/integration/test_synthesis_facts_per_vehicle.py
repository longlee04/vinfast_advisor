"""Fact tong hop phai thuoc dung xe dung dau, khong lan sang candidate khac.

`run_evidence` co tinh trai phang fact cua MOI candidate cho guardrail doi chieu.
Khi mot run co tu hai xe cung loai tro len, cung mot `fact_code` xuat hien nhieu
lan; neu `load_facts` khong loc theo xe thi tang tong hop vo o "unique fact
codes" va ca luot chat tra 500.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.synthesis_source import SqlAlchemySynthesisDataSource
from src.agents.models import AgentRunRow, ConversationSessionRow, RunEvidenceRow
from src.products.infrastructure.models import VehiclePriceRow, VehicleRow

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


async def _seed_vehicle(engine: AsyncEngine, model_name: str) -> tuple[UUID, UUID]:
    """Tao mot xe kem mot gia khoi diem, tra ve (vehicle_id, price_id)."""
    vehicle_id = uuid4()
    price_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(VehicleRow).values(
                vehicle_id=str(vehicle_id),
                vehicle_type="CAR",
                brand="VinFast",
                model_name=f"{model_name} {vehicle_id}",
                status="ACTIVE",
                slug=f"{model_name.lower()}-{vehicle_id}",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(VehiclePriceRow).values(
                price_id=str(price_id),
                vehicle_id=str(vehicle_id),
                price_type="STARTING_PRICE",
                amount_vnd=800_000_000,
                currency="VND",
                region_code="VN",
                status="ACTIVE",
                valid_from=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return vehicle_id, price_id


async def _seed_run(engine: AsyncEngine) -> UUID:
    session_id = uuid4()
    run_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="SNAPSHOT_READY",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return run_id


async def _seed_evidence(
    engine: AsyncEngine,
    run_id: UUID,
    *,
    fact_code: str,
    value_text: str,
    source_table: str,
    source_id: UUID,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(RunEvidenceRow).values(
                evidence_id=uuid4(),
                run_id=run_id,
                fact_code=fact_code,
                value_text=value_text,
                source_table=source_table,
                source_id=source_id,
                created_at=NOW,
            )
        )


@pytest_asyncio.fixture
async def seeded_vehicles(migrated_engine: AsyncEngine):
    top = await _seed_vehicle(migrated_engine, "Smoke Top")
    other = await _seed_vehicle(migrated_engine, "Smoke Other")
    yield top, other
    async with migrated_engine.begin() as connection:
        ids = [str(top[0]), str(other[0])]
        await connection.execute(delete(VehiclePriceRow).where(VehiclePriceRow.vehicle_id.in_(ids)))
        await connection.execute(delete(VehicleRow).where(VehicleRow.vehicle_id.in_(ids)))


@pytest.mark.asyncio
async def test_load_facts_keeps_only_the_top_vehicle_spec_facts(
    migrated_engine: AsyncEngine, clean_agent_database: None, seeded_vehicles
) -> None:
    # Given
    (top_id, _top_price), (other_id, _other_price) = seeded_vehicles
    run_id = await _seed_run(migrated_engine)
    await _seed_evidence(
        migrated_engine,
        run_id,
        fact_code="CAR_RANGE_KM",
        value_text="399",
        source_table="cars",
        source_id=top_id,
    )
    await _seed_evidence(
        migrated_engine,
        run_id,
        fact_code="CAR_RANGE_KM",
        value_text="470",
        source_table="cars",
        source_id=other_id,
    )

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    facts = await SqlAlchemySynthesisDataSource(session_factory).load_facts(run_id=run_id, vehicle_ids=(top_id,))

    # Then
    assert [fact.value_text for fact in facts] == ["399"]
    assert {fact.fact_code for fact in facts} == {"CAR_RANGE_KM"}


@pytest.mark.asyncio
async def test_load_facts_resolves_price_evidence_back_to_its_vehicle(
    migrated_engine: AsyncEngine, clean_agent_database: None, seeded_vehicles
) -> None:
    # Given — evidence gia tro toi `price_id`, khong phai `vehicle_id`
    (top_id, top_price), (_other_id, other_price) = seeded_vehicles
    run_id = await _seed_run(migrated_engine)
    await _seed_evidence(
        migrated_engine,
        run_id,
        fact_code="STARTING_PRICE_VND",
        value_text="800000000",
        source_table="vehicle_prices",
        source_id=top_price,
    )
    await _seed_evidence(
        migrated_engine,
        run_id,
        fact_code="STARTING_PRICE_VND",
        value_text="950000000",
        source_table="vehicle_prices",
        source_id=other_price,
    )

    # When
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    facts = await SqlAlchemySynthesisDataSource(session_factory).load_facts(run_id=run_id, vehicle_ids=(top_id,))

    # Then
    assert [fact.value_text for fact in facts] == ["800000000"]
