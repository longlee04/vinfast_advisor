"""PRD 5.3: moi ung vien phai luu lai tang da di toi de HITL truy vet."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.contracts import CandidateInput
from src.agents.models import RunCandidateRow


async def _run_id(agent_session):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    clock = SystemClock()
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    return await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)


@pytest.mark.asyncio
async def test_save_candidates_records_layer_and_leaves_rank_empty(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    vehicle_id = uuid4()

    await repository.save_candidates(run_id, [CandidateInput(vehicle_id=vehicle_id, layer_reached="L3")])

    row = await agent_session.scalar(select(RunCandidateRow).where(RunCandidateRow.run_id == run_id))
    assert row.vehicle_id == vehicle_id
    assert row.layer_reached == "L3"
    assert row.rank is None


@pytest.mark.asyncio
async def test_set_candidate_ranks_fills_only_the_listed_vehicles(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    ranked, unranked = uuid4(), uuid4()
    await repository.save_candidates(
        run_id,
        [
            CandidateInput(vehicle_id=ranked, layer_reached="L2"),
            CandidateInput(vehicle_id=unranked, layer_reached="L2"),
        ],
    )

    await repository.set_candidate_ranks(run_id, {ranked: 1})

    rows = (
        (await agent_session.execute(select(RunCandidateRow).where(RunCandidateRow.run_id == run_id))).scalars().all()
    )
    by_vehicle = {row.vehicle_id: row.rank for row in rows}
    assert by_vehicle[ranked] == 1
    assert by_vehicle[unranked] is None
