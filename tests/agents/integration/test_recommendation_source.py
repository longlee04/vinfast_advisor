"""A5-3: nguồn xếp hạng đọc snapshot, không đọc catalog sống."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.recommendation_source import SqlAlchemyRecommendationDataSource
from src.agents.adapters.run_repository import SqlAlchemyRunRepository


@pytest.mark.asyncio
async def test_load_returns_none_for_a_run_without_snapshot(agent_session_factory):
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    # Mở và commit trong một transaction riêng trước khi đọc lại — data source
    # giờ tự mở session mới cho từng lời gọi nên không còn thấy dữ liệu chưa
    # commit của một session khác.
    async with agent_session_factory() as session, session.begin():
        await SqlAlchemySessionRepository(session, clock).ensure_session(
            session_id, customer_id, vehicle_type_hint=None
        )
        run_id = await SqlAlchemyRunRepository(session, clock).create_run(session_id)

    assert await SqlAlchemyRecommendationDataSource(agent_session_factory).load(run_id) is None


@pytest.mark.asyncio
async def test_load_parses_the_persisted_snapshot(agent_session_factory):
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    async with agent_session_factory() as session, session.begin():
        await SqlAlchemySessionRepository(session, clock).ensure_session(
            session_id, customer_id, vehicle_type_hint=None
        )
        runs = SqlAlchemyRunRepository(session, clock)
        run_id = await runs.create_run(session_id)
        await runs.save_snapshot(run_id, {"candidates": [], "assertions": []})

    context = await SqlAlchemyRecommendationDataSource(agent_session_factory).load(run_id)

    assert context is not None
    assert context.snapshot.candidates == ()
