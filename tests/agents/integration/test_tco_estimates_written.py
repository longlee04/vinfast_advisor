"""PRD 5.5/5.11: TCO cua mot run duoc dong bang, khong tinh lai."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.models import TcoEstimateRow
from src.agents.tools.tco import DetailedTcoResult


async def _run_id(agent_session):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    clock = SystemClock()
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    return await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)


def _result(vehicle_id, assumption_id) -> DetailedTcoResult:
    components = {
        "promoted_purchase_price_vnd": Decimal("900000000"),
        "rolling_fees_vnd": Decimal("35000000"),
        "energy_vnd": Decimal("18000000"),
        "battery_vnd": Decimal("0"),
        "scheduled_maintenance_vnd": Decimal("7000000"),
    }
    return DetailedTcoResult(
        vehicle_id=vehicle_id,
        total_vnd=sum(components.values(), start=Decimal("0")),
        components_vnd=components,
        assumptions_id=assumption_id,
        computed_at=datetime(2026, 8, 11, tzinfo=UTC),
        monthly_distance_km=Decimal("900.00"),
    )


@pytest.mark.asyncio
async def test_save_tco_estimate_persists_every_component(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    vehicle_id, assumption_id = uuid4(), uuid4()

    await repository.save_tco_estimate(run_id, _result(vehicle_id, assumption_id))

    row = await agent_session.scalar(select(TcoEstimateRow).where(TcoEstimateRow.run_id == run_id))
    assert row.vehicle_id == vehicle_id
    assert row.assumption_id == assumption_id
    assert row.total_vnd == 960000000
    assert row.energy_vnd == 18000000


@pytest.mark.asyncio
async def test_unavailable_result_is_not_persisted(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    unavailable = DetailedTcoResult(
        vehicle_id=uuid4(),
        total_vnd=None,
        components_vnd={},
        assumptions_id=None,
        computed_at=datetime(2026, 8, 11, tzinfo=UTC),
        unavailable_reason="TCO_UNAVAILABLE: daily_distance_km",
    )

    await repository.save_tco_estimate(run_id, unavailable)

    rows = (await agent_session.execute(select(TcoEstimateRow).where(TcoEstimateRow.run_id == run_id))).scalars().all()
    assert rows == []
