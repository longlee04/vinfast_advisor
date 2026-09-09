"""A5-1/A5-2: vòng đời agent_runs và ghi snapshot bất biến."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.models import AgentRunRow, RunSnapshotRow


@pytest_asyncio.fixture
async def agent_session(migrated_engine: AsyncEngine, clean_agent_database: None) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        yield session


async def _session_id(agent_session: AsyncSession) -> str:
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, SystemClock()).ensure_session(
        session_id, customer_id, vehicle_type_hint=None
    )
    return session_id


@pytest.mark.asyncio
async def test_create_run_starts_in_capturing(agent_session: AsyncSession) -> None:
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())

    run_id = await repository.create_run(await _session_id(agent_session))

    assert isinstance(run_id, UUID)
    row = await agent_session.scalar(select(AgentRunRow).where(AgentRunRow.run_id == run_id))
    assert row.state == "CAPTURING"


@pytest.mark.asyncio
async def test_set_state_advances_the_run(agent_session: AsyncSession) -> None:
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await repository.create_run(await _session_id(agent_session))

    await repository.set_state(run_id, "SNAPSHOT_READY")

    row = await agent_session.scalar(select(AgentRunRow).where(AgentRunRow.run_id == run_id))
    assert row.state == "SNAPSHOT_READY"


@pytest.mark.asyncio
async def test_save_snapshot_persists_payload_under_the_run(agent_session: AsyncSession) -> None:
    repository = SqlAlchemyRunRepository(agent_session, SystemClock())
    run_id = await repository.create_run(await _session_id(agent_session))

    await repository.save_snapshot(run_id, {"candidates": [], "assertions": []})

    row = await agent_session.scalar(select(RunSnapshotRow).where(RunSnapshotRow.run_id == run_id))
    assert row.payload == {"candidates": [], "assertions": []}
