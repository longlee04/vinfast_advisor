from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationMemoryRepository,
    SqlAlchemyConversationRepository,
)
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.conversation_memory import ConversationState
from src.agents.errors import ConversationArchivedError, ConversationNotFoundError
from src.agents.ports import ClockPort


class MutableClock(ClockPort):
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 15, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current


@dataclass(frozen=True, slots=True)
class Transaction:
    conversations: SqlAlchemyConversationRepository
    memory: SqlAlchemyConversationMemoryRepository


@pytest.mark.asyncio
async def test_owned_lifecycle_list_cursor_archive_and_delete(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = MutableClock()
    uow = AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            conversations=SqlAlchemyConversationRepository(session, clock),
            memory=SqlAlchemyConversationMemoryRepository(session, clock),
        ),
    )

    async with uow.transaction() as transaction:
        first = await transaction.conversations.create("customer-1")
    clock.current += timedelta(minutes=1)
    async with uow.transaction() as transaction:
        second = await transaction.conversations.create("customer-1")

    async with uow.transaction() as transaction:
        page_one = await transaction.conversations.list_owned("customer-1", limit=1)
        page_two = await transaction.conversations.list_owned("customer-1", limit=1, cursor=page_one.next_cursor)

    assert [item.conversation_id for item in page_one.items] == [second.conversation_id]
    assert page_one.next_cursor is not None
    assert [item.conversation_id for item in page_two.items] == [first.conversation_id]
    assert page_two.next_cursor is None

    async with uow.transaction() as transaction:
        archived = await transaction.conversations.archive(first.conversation_id, "customer-1")
        visible = await transaction.conversations.list_owned("customer-1", limit=10)
        detail = await transaction.conversations.get_owned(first.conversation_id, "customer-1")

    assert archived.state is ConversationState.ARCHIVED
    assert detail.state is ConversationState.ARCHIVED
    assert [item.conversation_id for item in visible.items] == [second.conversation_id]

    async with factory() as session, session.begin():
        legacy_sessions = SqlAlchemySessionRepository(session, clock)
        with pytest.raises(ConversationArchivedError):
            await legacy_sessions.ensure_session(str(first.conversation_id), "customer-1", None)

    async with uow.transaction() as transaction:
        with pytest.raises(ConversationNotFoundError):
            await transaction.conversations.get_owned(second.conversation_id, "customer-2")
        await transaction.conversations.delete(second.conversation_id, "customer-1")
        with pytest.raises(ConversationNotFoundError):
            await transaction.conversations.get_owned(second.conversation_id, "customer-1")


@pytest.mark.asyncio
async def test_message_pages_are_chronological_and_owner_scoped(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = MutableClock()
    uow = AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            conversations=SqlAlchemyConversationRepository(session, clock),
            memory=SqlAlchemyConversationMemoryRepository(session, clock),
        ),
    )

    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        for index in range(3):
            await transaction.memory.append(
                str(conversation.conversation_id),
                "customer-1",
                "USER" if index % 2 == 0 else "ASSISTANT",
                f"message-{index + 1}",
                uuid4(),
            )

    async with uow.transaction() as transaction:
        first_page = await transaction.conversations.read_messages(conversation.conversation_id, "customer-1", limit=2)
        second_page = await transaction.conversations.read_messages(
            conversation.conversation_id,
            "customer-1",
            limit=2,
            cursor=first_page.next_cursor,
        )

    assert [item.content for item in first_page.items] == ["message-1", "message-2"]
    assert [item.content for item in second_page.items] == ["message-3"]
    assert all(item.message_id is not None for item in first_page.items)

    async with uow.transaction() as transaction:
        with pytest.raises(ConversationNotFoundError):
            await transaction.conversations.read_messages(conversation.conversation_id, "customer-2", limit=10)
