"""PRD 5.3: diem va >=2 ly do phai luu lai cho HITL."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.contracts import ScoreInput
from src.agents.models import ScoringResultRow


async def _run_id(agent_session):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    clock = SystemClock()
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    return await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)


@pytest.mark.asyncio
async def test_save_scores_persists_score_and_reason_payload(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)
    vehicle_id = uuid4()

    await repository.save_scores(
        run_id,
        [
            ScoreInput(
                vehicle_id=vehicle_id,
                score=Decimal("12.500"),
                reasons=("[slot=vehicle_type] dung loai xe", "[slot=budget_vnd] trong ngan sach"),
            )
        ],
    )

    row = await agent_session.scalar(select(ScoringResultRow).where(ScoringResultRow.run_id == run_id))
    assert row.vehicle_id == vehicle_id
    assert row.score == Decimal("12.500")
    assert [item["reason"] for item in row.reasons] == [
        "[slot=vehicle_type] dung loai xe",
        "[slot=budget_vnd] trong ngan sach",
    ]


@pytest.mark.asyncio
async def test_save_scores_rejects_a_candidate_with_a_single_reason(agent_session):
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await _run_id(agent_session)

    # SAVEPOINT: CHECK vi pham lam abort ca transaction cua fixture, khong con
    # chay duoc lenh nao sau do. begin_nested() gioi han thiet hai trong bai nay.
    with pytest.raises(IntegrityError):
        async with agent_session.begin_nested():
            await repository.save_scores(
                run_id,
                [ScoreInput(vehicle_id=uuid4(), score=Decimal("1.000"), reasons=("chi mot ly do",))],
            )
