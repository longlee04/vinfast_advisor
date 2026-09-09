"""A2-2 conversation session and slot persistence integration tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.conversation_repository import (
    SqlAlchemyPendingFeatureMentionRepository,
    SqlAlchemySessionRepository,
)
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.values import SlotName
from src.agents.errors import SessionOwnershipError
from src.agents.models import ConversationSessionRow, ConversationSlotRow, PendingFeatureMentionRow
from src.agents.ports import ClockPort, SessionRepository
from src.agents.services.conversation import ConversationServiceImpl

NOW = datetime(2026, 8, 9, tzinfo=UTC)
SESSION_ID = "10000000-0000-0000-0000-000000000001"


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return NOW


@dataclass(frozen=True, slots=True)
class ConversationTransaction:
    sessions: SessionRepository


@pytest_asyncio.fixture
async def conversation_service(migrated_engine: AsyncEngine, clean_agent_database: None) -> ConversationServiceImpl:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    clock = FixedClock()
    unit_of_work = AgentUnitOfWork(
        session_factory,
        transaction_factory=lambda session: ConversationTransaction(SqlAlchemySessionRepository(session, clock)),
    )
    return ConversationServiceImpl(unit_of_work)


@pytest.mark.asyncio
async def test_budget_update_keeps_one_slot_row_with_newest_value(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.BUDGET_MAX_VND: 700_000_000})
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.BUDGET_MAX_VND: 800_000_000})

    async with migrated_engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    select(ConversationSlotRow.slot_value_number).where(
                        ConversationSlotRow.session_id == UUID(SESSION_ID),
                        ConversationSlotRow.slot_name == SlotName.BUDGET_MAX_VND.value,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert rows == [800_000_000]
    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {SlotName.BUDGET_MAX_VND: 800_000_000}


@pytest.mark.asyncio
async def test_restart_advisory_clears_slots_pending_input_and_task_focus(
    conversation_service: ConversationServiceImpl,
) -> None:
    await conversation_service.save_turn(
        SESSION_ID,
        "customer-1",
        {
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
        },
    )
    await conversation_service.save_pending_slot(SESSION_ID, {"missing_slot": "passenger_count"})
    await conversation_service.save_active_task(
        SESSION_ID,
        {
            "schema_version": 1,
            "task_type": "ADVISORY",
            "status": "COMPLETED",
            "form": {"seen_recommendation_ids": []},
            "revision": 1,
            "updated_at": NOW.isoformat(),
        },
    )

    await conversation_service.restart_advisory(SESSION_ID)

    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {}
    assert await conversation_service.load_pending_slot(SESSION_ID) is None
    assert await conversation_service.load_active_task(SESSION_ID) is None


@pytest.mark.asyncio
async def test_other_customer_cannot_update_existing_session(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.PURPOSE: "family"})

    with pytest.raises(SessionOwnershipError):
        await conversation_service.save_turn(SESSION_ID, "customer-2", {SlotName.PURPOSE: "delivery"})

    async with migrated_engine.connect() as connection:
        customer_id = await connection.scalar(
            select(ConversationSessionRow.customer_id).where(ConversationSessionRow.session_id == UUID(SESSION_ID))
        )

    assert customer_id == "customer-1"
    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {SlotName.PURPOSE: "family"}


@pytest.mark.asyncio
async def test_omitted_vehicle_type_preserves_existing_hint(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.VEHICLE_TYPE: "CAR"})
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.PURPOSE: "family"})

    async with migrated_engine.connect() as connection:
        hint = await connection.scalar(
            select(ConversationSessionRow.vehicle_type_hint).where(
                ConversationSessionRow.session_id == UUID(SESSION_ID)
            )
        )

    assert hint == "CAR"


@pytest.mark.asyncio
async def test_list_slot_round_trips_and_cross_customer_read_is_rejected(
    conversation_service: ConversationServiceImpl,
) -> None:
    tags = ["home_charging", "family"]
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.HABIT_NEED_TAGS: tags})

    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {SlotName.HABIT_NEED_TAGS: tags}
    with pytest.raises(SessionOwnershipError):
        await conversation_service.load_slots(SESSION_ID, "customer-2")


@pytest.mark.asyncio
@pytest.mark.parametrize("home_charging", [True, False])
async def test_home_charging_round_trips_as_boolean(
    conversation_service: ConversationServiceImpl, home_charging: bool
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {SlotName.HOME_CHARGING: home_charging})

    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {SlotName.HOME_CHARGING: home_charging}


@pytest.mark.asyncio
async def test_float_and_none_slot_values_round_trip(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(
        SESSION_ID,
        "customer-1",
        {SlotName.REQUIRED_RANGE_KM: 123.5, SlotName.PURPOSE: None},
    )

    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {
        SlotName.REQUIRED_RANGE_KM: 123.5,
        SlotName.PURPOSE: None,
    }
    async with migrated_engine.connect() as connection:
        encoded_none = await connection.scalar(
            select(ConversationSlotRow.slot_value_text).where(
                ConversationSlotRow.session_id == UUID(SESSION_ID),
                ConversationSlotRow.slot_name == SlotName.PURPOSE.value,
            )
        )

    assert encoded_none is None


@pytest.mark.asyncio
async def test_string_null_and_none_remain_distinct_slot_values(conversation_service: ConversationServiceImpl) -> None:
    await conversation_service.save_turn(
        SESSION_ID,
        "customer-1",
        {SlotName.PURPOSE: "null", SlotName.MAX_LOAD_KG: None},
    )

    assert await conversation_service.load_slots(SESSION_ID, "customer-1") == {
        SlotName.PURPOSE: "null",
        SlotName.MAX_LOAD_KG: None,
    }


@pytest.mark.asyncio
async def test_pending_mentions_consume_preserves_applied_history(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {})
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with factory.begin() as session:
        repository = SqlAlchemyPendingFeatureMentionRepository(session, FixedClock())
        await repository.record(SESSION_ID, "customer-1", ["VF 8", "VF 8"])
        assert await repository.consume(SESSION_ID, "customer-1") == ["VF 8"]
        with pytest.raises(SessionOwnershipError):
            await repository.consume(SESSION_ID, "customer-2")

    async with migrated_engine.connect() as connection:
        applied_at = await connection.scalar(select(PendingFeatureMentionRow.applied_at))

    assert applied_at == NOW


@pytest.mark.asyncio
async def test_pending_mentions_dedupe_and_consume_concurrently(
    conversation_service: ConversationServiceImpl, migrated_engine: AsyncEngine
) -> None:
    await conversation_service.save_turn(SESSION_ID, "customer-1", {})
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    async def record() -> None:
        async with factory.begin() as session:
            await SqlAlchemyPendingFeatureMentionRepository(session, FixedClock()).record(
                SESSION_ID, "customer-1", ["VF 8"]
            )

    await asyncio.gather(record(), record())
    async with migrated_engine.connect() as connection:
        pending_count = await connection.scalar(
            select(func.count())
            .select_from(PendingFeatureMentionRow)
            .where(PendingFeatureMentionRow.applied_at.is_(None))
        )
    assert pending_count == 1

    async def consume() -> list[str]:
        async with factory.begin() as session:
            return await SqlAlchemyPendingFeatureMentionRepository(session, FixedClock()).consume(
                SESSION_ID, "customer-1"
            )

    consumed = await asyncio.gather(consume(), consume())
    assert sorted(consumed) == [[], ["VF 8"]]
    async with migrated_engine.connect() as connection:
        applied_count = await connection.scalar(
            select(func.count())
            .select_from(PendingFeatureMentionRow)
            .where(PendingFeatureMentionRow.applied_at.is_not(None))
        )
    assert applied_count == 1
