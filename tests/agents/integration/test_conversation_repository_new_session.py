"""Phiên chưa tồn tại khác phiên của người khác (A2-2)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.errors import SessionOwnershipError


@pytest.mark.asyncio
async def test_unknown_session_returns_no_slots_instead_of_ownership_error(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        repository = SqlAlchemySessionRepository(session, SystemClock())

        slots = await repository.get_slots(str(uuid4()), f"customer-{uuid4()}")

    assert slots == {}


@pytest.mark.asyncio
async def test_session_owned_by_another_customer_still_raises(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    session_id, owner = str(uuid4()), f"owner-{uuid4()}"
    async with session_factory.begin() as session:
        repository = SqlAlchemySessionRepository(session, SystemClock())
        await repository.ensure_session(session_id, owner, vehicle_type_hint=None)

    async with session_factory.begin() as session:
        repository = SqlAlchemySessionRepository(session, SystemClock())

        with pytest.raises(SessionOwnershipError):
            await repository.get_slots(session_id, f"intruder-{uuid4()}")
