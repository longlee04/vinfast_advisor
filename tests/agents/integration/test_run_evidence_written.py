"""PRD 8.4: moi so lieu phai co evidence cung run de guardrail doi chieu."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.contracts import EvidenceInput
from src.agents.models import RunEvidenceRow


async def _run_id(agent_session):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    clock = SystemClock()
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    return await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)


@pytest.mark.asyncio
async def test_save_evidence_persists_one_row_per_fact(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    source_id = uuid4()

    await repository.save_evidence(
        run_id,
        [
            EvidenceInput(
                fact_code="PRICE_VND",
                value_text="799000000",
                source_table="vehicle_prices",
                source_id=source_id,
            )
        ],
    )

    row = await agent_session.scalar(select(RunEvidenceRow).where(RunEvidenceRow.run_id == run_id))
    assert row.fact_code == "PRICE_VND"
    assert row.value_text == "799000000"
    assert row.source_table == "vehicle_prices"
    assert row.source_id == source_id


@pytest.mark.asyncio
async def test_save_evidence_of_empty_list_writes_nothing(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)

    await repository.save_evidence(run_id, [])

    rows = (await agent_session.execute(select(RunEvidenceRow).where(RunEvidenceRow.run_id == run_id))).scalars().all()
    assert rows == []
