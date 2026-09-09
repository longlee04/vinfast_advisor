from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus
from src.agents.errors import ConversationNotFoundError
from src.agents.models import ConversationTurnOutcomeRow
from src.agents.ports import ClockPort
from src.agents.services.turn_handoff import HANDOFF_MESSAGE


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 8, 15, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Transaction:
    conversations: SqlAlchemyConversationRepository
    outcomes: SqlAlchemyTurnOutcomeRepository


@pytest.mark.asyncio
async def test_concurrent_client_key_has_one_claim_and_one_outcome(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    uow = AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            SqlAlchemyConversationRepository(session, clock),
            SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
    client_turn_id = uuid4()

    async def claim() -> bool:
        async with uow.transaction() as transaction:
            result = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
            return result.claimed

    claims = await asyncio.gather(claim(), claim())

    assert sorted(claims) == [False, True]
    async with migrated_engine.connect() as connection:
        count = await connection.scalar(select(func.count()).select_from(ConversationTurnOutcomeRow))
    assert count == 1


@pytest.mark.asyncio
async def test_finalized_outcome_replays_exact_payload_and_is_owner_scoped(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    uow = AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            SqlAlchemyConversationRepository(session, clock),
            SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        claim = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        finalized = await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation.conversation_id,
                client_turn_id=client_turn_id,
                turn_number=claim.outcome.turn_number,
                status=TurnOutcomeStatus.COMPLETED,
                terminal_reason="CATALOG_LOOKUP",
                lookup_facts=({"vehicle_id": str(UUID(int=1)), "display_name": "VF 7"},),
            )
        )

    async with uow.transaction() as transaction:
        replay = await transaction.outcomes.get(conversation.conversation_id, "customer-1", client_turn_id)
        with pytest.raises(ConversationNotFoundError):
            await transaction.outcomes.get(conversation.conversation_id, "customer-2", client_turn_id)

    assert replay == finalized


@pytest.mark.asyncio
async def test_a_handoff_outcome_replays_the_fixed_message_never_the_review_id_as_content(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """T12: outcome của một lượt chuyển người (WAITING_REVIEW) chỉ được phát
    lại đúng `HANDOFF_MESSAGE` cố định - không phải nội dung tư vấn viên đọc,
    không phải bất kỳ dấu vết nội bộ nào (`review_id` không được lẫn vào
    `answer`)."""
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    uow = AgentUnitOfWork(
        factory,
        lambda session: Transaction(
            SqlAlchemyConversationRepository(session, clock),
            SqlAlchemyTurnOutcomeRepository(session, clock),
        ),
    )
    review_id = uuid4()
    async with uow.transaction() as transaction:
        conversation = await transaction.conversations.create("customer-1")
        client_turn_id = uuid4()
        claim = await transaction.outcomes.claim(conversation.conversation_id, "customer-1", client_turn_id)
        finalized = await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation.conversation_id,
                client_turn_id=client_turn_id,
                turn_number=claim.outcome.turn_number,
                status=TurnOutcomeStatus.WAITING_REVIEW,
                answer=HANDOFF_MESSAGE,
                review_id=review_id,
            )
        )

    async with uow.transaction() as transaction:
        replay = await transaction.outcomes.get(conversation.conversation_id, "customer-1", client_turn_id)

    assert replay == finalized
    assert replay.answer == HANDOFF_MESSAGE
    assert str(review_id) not in replay.answer
    assert replay.review_id == review_id
