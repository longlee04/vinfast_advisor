from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationMemoryRepository,
)
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.conversation_memory import ConversationSummary
from src.agents.errors import SessionOwnershipError
from src.agents.ports import ClockPort, ConversationMemoryRepository

SESSION_ID = "10000000-0000-0000-0000-000000000071"
NOW = datetime(2026, 8, 15, tzinfo=UTC)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return NOW


@dataclass(frozen=True, slots=True)
class Transaction:
    memory: ConversationMemoryRepository


@pytest.mark.asyncio
async def test_repository_is_owned_append_only_and_idempotent(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    async with session_factory() as session, session.begin():
        await SqlAlchemySessionRepository(session, clock).ensure_session(SESSION_ID, "customer-1", None)
    uow = AgentUnitOfWork(
        session_factory,
        lambda session: Transaction(SqlAlchemyConversationMemoryRepository(session, clock)),
    )
    client_turn_id = uuid4()

    async with uow.transaction() as transaction:
        first = await transaction.memory.append(SESSION_ID, "customer-1", "USER", "VF 7 giá bao nhiêu?", client_turn_id)
    async with uow.transaction() as transaction:
        repeated = await transaction.memory.append(
            SESSION_ID, "customer-1", "USER", "nội dung retry khác", client_turn_id
        )
        assistant = await transaction.memory.append(
            SESSION_ID, "customer-1", "ASSISTANT", "Giá VF 7 ...", client_turn_id
        )
        completed = await transaction.memory.find_by_client_turn(SESSION_ID, "customer-1", client_turn_id)

    assert first == repeated
    assert [message.content for message in completed] == ["VF 7 giá bao nhiêu?", "Giá VF 7 ..."]
    assert assistant.turn_index == 2
    async with uow.transaction() as transaction:
        with pytest.raises(SessionOwnershipError):
            await transaction.memory.load_recent(SESSION_ID, "customer-2", 8)


@pytest.mark.asyncio
async def test_summary_marker_leaves_only_unsummarized_recent_messages(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    async with session_factory() as session, session.begin():
        await SqlAlchemySessionRepository(session, clock).ensure_session(SESSION_ID, "customer-1", None)
    repository_uow = AgentUnitOfWork(
        session_factory,
        lambda session: Transaction(SqlAlchemyConversationMemoryRepository(session, clock)),
    )
    async with repository_uow.transaction() as transaction:
        await transaction.memory.append(SESSION_ID, "customer-1", "USER", "câu 1", None)
        await transaction.memory.append(SESSION_ID, "customer-1", "ASSISTANT", "đáp 1", None)
        await transaction.memory.save_summary(SESSION_ID, "customer-1", ConversationSummary("Đã tóm tắt cặp 1.", 2))
        await transaction.memory.append(SESSION_ID, "customer-1", "USER", "câu 2", None)
    async with repository_uow.transaction() as transaction:
        summary, recent = await transaction.memory.load_recent(SESSION_ID, "customer-1", 8)

    assert summary == ConversationSummary("Đã tóm tắt cặp 1.", 2)
    assert [(message.turn_index, message.content) for message in recent] == [(3, "câu 2")]


@pytest.mark.asyncio
async def test_session_repository_round_trips_and_clears_active_task(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    payload = {
        "schema_version": 1,
        "task_type": "ON_ROAD_PRICE_LOOKUP",
        "status": "COMPLETED",
        "form": {"vehicle_id": "vf5", "province": "HN"},
        "revision": 1,
        "updated_at": NOW.isoformat(),
    }

    async with session_factory() as session, session.begin():
        repository = SqlAlchemySessionRepository(session, clock)
        await repository.ensure_session(SESSION_ID, "customer-1", None)
        await repository.save_active_task(SESSION_ID, payload)
    async with session_factory() as session, session.begin():
        repository = SqlAlchemySessionRepository(session, clock)
        assert await repository.load_active_task(SESSION_ID) == payload
        await repository.save_active_task(SESSION_ID, None)
    async with session_factory() as session, session.begin():
        repository = SqlAlchemySessionRepository(session, clock)
        assert await repository.load_active_task(SESSION_ID) is None
