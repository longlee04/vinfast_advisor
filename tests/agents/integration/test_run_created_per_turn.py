"""Một lượt truy xuất mở đúng một hàng agent_runs."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.models import AgentRunRow


async def _create_session(migrated_engine: AsyncEngine, session_id: str, customer_id: str) -> None:
    """Persist session before a separate graph transaction creates its run."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        repository = SqlAlchemySessionRepository(session, SystemClock())
        await repository.ensure_session(session_id, customer_id, vehicle_type_hint=None)


async def _run_count(agent_session, session_id: str) -> int:
    """Count runs for one conversation session."""
    total = await agent_session.scalar(
        select(func.count()).select_from(AgentRunRow).where(AgentRunRow.session_id == session_id)
    )
    return int(total or 0)


@pytest.mark.asyncio
async def test_advisory_retrieval_turn_opens_exactly_one_run(agent_composition, agent_session, migrated_engine) -> None:
    """A confirmed retrieval branch creates one durable run before layer1."""
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)
    await agent_composition.graph.ainvoke(
        {
            "session_id": session_id,
            "customer_id": customer_id,
            "user_message": "toi muon mua o to",
            "do_retrieve": True,
        }
    )

    assert await _run_count(agent_session, session_id) == 1


@pytest.mark.asyncio
async def test_ask_only_turn_does_not_open_run(agent_composition, agent_session) -> None:
    """A slot-only branch ends without creating an agent run."""
    session_id = str(uuid4())
    await agent_composition.graph.ainvoke(
        {
            "session_id": session_id,
            "customer_id": f"customer-{uuid4()}",
            "user_message": "toi can tu van",
            "do_retrieve": False,
        }
    )

    assert await _run_count(agent_session, session_id) == 0
