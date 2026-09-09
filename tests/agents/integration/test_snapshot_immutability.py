"""PostgreSQL acceptance test for A5-2 snapshot immutability."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.models import AgentRunRow, ConversationSessionRow, RunSnapshotRow
from src.agents.services.snapshotting import (
    DefaultSnapshottingService,
    SnapshotCandidate,
    SnapshotFact,
    parse_snapshot,
)
from src.products.infrastructure.models import VehiclePriceRow, VehicleRow

NOW = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)
VEHICLE_ID = UUID("60000000-0000-0000-0000-000000000001")
PRICE_ID = UUID("70000000-0000-0000-0000-000000000001")


class FixedClock:
    def now(self) -> datetime:
        return NOW


class SqlCatalogSource:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load(self, *, candidate_ids: tuple[UUID, ...], at: datetime) -> tuple[SnapshotCandidate, ...]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(VehicleRow.vehicle_id, VehiclePriceRow.price_id, VehiclePriceRow.amount_vnd)
                    .join(VehiclePriceRow, VehiclePriceRow.vehicle_id == VehicleRow.vehicle_id)
                    .where(
                        VehicleRow.vehicle_id.in_([str(item) for item in candidate_ids]),
                        VehiclePriceRow.price_type == "STARTING_PRICE",
                        VehiclePriceRow.status == "ACTIVE",
                        VehiclePriceRow.valid_from <= at,
                    )
                )
            ).all()
        return tuple(
            SnapshotCandidate(
                vehicle_id=UUID(row.vehicle_id),
                facts=(
                    SnapshotFact(
                        fact_code="STARTING_PRICE_VND",
                        value_text=str(row.amount_vnd),
                        source_table="vehicle_prices",
                        source_id=UUID(row.price_id),
                    ),
                ),
            )
            for row in rows
        )


class SqlRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_snapshot(self, run_id: UUID, payload: dict) -> None:
        await self._session.execute(
            insert(RunSnapshotRow).values(
                snapshot_id=uuid4(),
                run_id=run_id,
                captured_at=NOW,
                payload=payload,
                created_at=NOW,
            )
        )

    async def set_state(self, run_id: UUID, state: str) -> None:
        await self._session.execute(update(AgentRunRow).where(AgentRunRow.run_id == run_id).values(state=state))

    async def save_evidence(self, run_id: UUID, facts) -> None:
        return None

    async def save_candidates(self, run_id: UUID, candidates) -> None:
        return None

    async def save_scores(self, run_id: UUID, scores) -> None:
        return None

    async def set_candidate_ranks(self, run_id: UUID, ranks) -> None:
        return None

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]:
        return []

    async def save_tco_estimate(self, run_id: UUID, result) -> None:
        return None


def _transaction(session: AsyncSession):
    return SimpleNamespace(runs=SqlRunRepository(session))


@pytest.mark.asyncio
async def test_real_catalog_price_update_after_snapshot_does_not_change_run_result(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_id = uuid4()
    run_id = uuid4()
    async with migrated_engine.begin() as connection:
        await connection.execute(
            insert(VehicleRow).values(
                vehicle_id=str(VEHICLE_ID),
                vehicle_type="CAR",
                brand="VinFast",
                model_name="Snapshot Test",
                status="ACTIVE",
                slug=f"snapshot-test-{run_id}",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(VehiclePriceRow).values(
                price_id=str(PRICE_ID),
                vehicle_id=str(VEHICLE_ID),
                price_type="STARTING_PRICE",
                amount_vnd=700_000_000,
                currency="VND",
                region_code="VN",
                status="ACTIVE",
                valid_from=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="snapshot-customer",
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
                created_at=NOW,
                updated_at=NOW,
            )
        )

    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    service = DefaultSnapshottingService(
        source=SqlCatalogSource(migrated_engine),
        unit_of_work=AgentUnitOfWork(session_factory, _transaction),
        clock=FixedClock(),
    )

    try:
        await service.snapshot(run_id=run_id, candidate_ids=[VEHICLE_ID], assertions=[])
        async with migrated_engine.begin() as connection:
            await connection.execute(
                update(VehiclePriceRow).where(VehiclePriceRow.price_id == str(PRICE_ID)).values(amount_vnd=800_000_000)
            )
        async with migrated_engine.connect() as connection:
            live_price = await connection.scalar(
                select(VehiclePriceRow.amount_vnd).where(VehiclePriceRow.price_id == str(PRICE_ID))
            )
            payload = await connection.scalar(select(RunSnapshotRow.payload).where(RunSnapshotRow.run_id == run_id))
            run_state = await connection.scalar(select(AgentRunRow.state).where(AgentRunRow.run_id == run_id))

        snapshot = parse_snapshot(payload)
        assert live_price == 800_000_000
        assert snapshot.candidates[0].facts[0].value_text == "700000000"
        assert run_state == "SNAPSHOT_READY"
    finally:
        async with migrated_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM vehicle_prices WHERE price_id = :price_id"), {"price_id": PRICE_ID}
            )
            await connection.execute(
                text("DELETE FROM vehicles WHERE vehicle_id = :vehicle_id"), {"vehicle_id": VEHICLE_ID}
            )
