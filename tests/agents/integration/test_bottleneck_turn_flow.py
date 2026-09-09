from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.chain import run_turn
from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionStatus,
)
from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import (
    ConversationMessageRow,
    ConversationSlotRow,
    ConversationTurnBottleneckRow,
    ConversationTurnOutcomeRow,
)
from src.agents.ports import ClockPort
from src.agents.services.conversation import ConversationServiceImpl
from src.agents.services.conversation_memory import ConversationMemoryService
from src.agents.services.registry import AgentServices


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 8, 23, tzinfo=UTC)


class Summarizer:
    model_name = "integration-summary"

    async def summarize(self, *, previous_summary: str, user_message: str, assistant_response: str) -> str:
        del previous_summary
        return f"{user_message} {assistant_response}"


@dataclass
class CountingDetector:
    calls: int = 0

    async def detect(self) -> BottleneckDetected:
        self.calls += 1
        return BottleneckDetected(
            status=BottleneckDetectionStatus.DETECTED,
            label=Bottleneck.PRICE,
            evidence_quote="Giá hơi cao",
        )


class FailingSignalRepository(SqlAlchemyBottleneckSignalRepository):
    async def insert(self, signal):
        await super().insert(signal)
        raise RuntimeError("signal persistence failed")


class DetectorGraph:
    def __init__(self, detector: CountingDetector, anchor: UUID, answer: str = "Em hiểu băn khoăn về giá.") -> None:
        self._detector = detector
        self._anchor = anchor
        self._answer = answer
        self.calls = 0

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        del state
        self.calls += 1
        detection = await self._detector.detect()
        return {
            "answer": self._answer,
            "slots": {"vehicle_type": "CAR"},
            "bottleneck_detection": detection,
            "bottleneck_anchor_client_turn_id": self._anchor,
        }


def _services(
    engine: AsyncEngine, *, fail_signal_insert: bool = False
) -> tuple[AgentServices, CountingDetector, AgentUnitOfWork]:
    clock = FixedClock()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def transaction_factory(session: AsyncSession):
        transaction = build_agent_transaction(session, clock=clock)
        if fail_signal_insert:
            return replace(
                transaction,
                bottleneck_signals=FailingSignalRepository(session, clock),
            )
        return transaction

    unit_of_work = AgentUnitOfWork(factory, transaction_factory)
    detector = CountingDetector()
    return (
        AgentServices(
            conversation=ConversationServiceImpl(unit_of_work),
            memory=ConversationMemoryService(unit_of_work, Summarizer()),
        ),
        detector,
        unit_of_work,
    )


async def _seed_recommendation_anchor(unit_of_work: AgentUnitOfWork, conversation_id: UUID, customer_id: str) -> UUID:
    anchor = uuid4()
    async with unit_of_work.transaction() as transaction:
        await transaction.conversations.create(customer_id, conversation_id=conversation_id)
        await transaction.outcomes.claim(conversation_id, customer_id, anchor)
        await transaction.outcomes.finalize(
            TurnOutcome(
                conversation_id=conversation_id,
                client_turn_id=anchor,
                turn_number=1,
                status=TurnOutcomeStatus.COMPLETED,
                answer="VF 8 phù hợp.",
                recommendations=({"vehicle_id": str(uuid4())},),
            )
        )
    return anchor


async def _counts(engine: AsyncEngine) -> tuple[int, int, int]:
    async with engine.connect() as connection:
        messages = await connection.scalar(select(func.count()).select_from(ConversationMessageRow))
        slots = await connection.scalar(select(func.count()).select_from(ConversationSlotRow))
        signals = await connection.scalar(select(func.count()).select_from(ConversationTurnBottleneckRow))
    return int(messages or 0), int(slots or 0), int(signals or 0)


@pytest.mark.asyncio
async def test_turn_commits_response_slot_outcome_and_signal_atomically_without_detection_leak(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    services, detector, unit_of_work = _services(migrated_engine)
    conversation_id = uuid4()
    session_id = str(conversation_id)
    client_turn_id = uuid4()
    anchor = await _seed_recommendation_anchor(unit_of_work, conversation_id, "customer-1")
    graph = DetectorGraph(detector, anchor)

    # When
    result = await run_turn(
        graph,
        services,
        session_id=session_id,
        customer_id="customer-1",
        user_message="Giá hơi cao",
        client_turn_id=client_turn_id,
    )

    # Then
    assert result.answer == "Em hiểu băn khoăn về giá."
    assert result.bottleneck_detection is None
    assert await _counts(migrated_engine) == (2, 1, 1)
    async with migrated_engine.connect() as connection:
        status = await connection.scalar(
            select(ConversationTurnOutcomeRow.status).where(ConversationTurnOutcomeRow.client_turn_id == client_turn_id)
        )
    assert status == TurnOutcomeStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_finalize_failure_rolls_back_response_slot_outcome_and_signal(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given
    services, detector, unit_of_work = _services(migrated_engine, fail_signal_insert=True)
    conversation_id = uuid4()
    session_id = str(conversation_id)
    client_turn_id = uuid4()
    anchor = await _seed_recommendation_anchor(unit_of_work, conversation_id, "customer-1")
    graph = DetectorGraph(detector, anchor)

    # When
    with pytest.raises(RuntimeError, match="signal persistence failed"):
        await run_turn(
            graph,
            services,
            session_id=session_id,
            customer_id="customer-1",
            user_message="Giá hơi cao",
            client_turn_id=client_turn_id,
        )

    # Then: initial claim/user message remain; finalize transaction writes all roll back.
    assert await _counts(migrated_engine) == (1, 0, 0)
    async with migrated_engine.connect() as connection:
        status = await connection.scalar(
            select(ConversationTurnOutcomeRow.status).where(ConversationTurnOutcomeRow.client_turn_id == client_turn_id)
        )
    assert status == TurnOutcomeStatus.FAILED.value


@pytest.mark.asyncio
async def test_response_loss_replay_skips_graph_and_detector_and_returns_exact_result(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given: first response committed but caller behaves as if transport lost it.
    services, detector, unit_of_work = _services(migrated_engine)
    conversation_id = uuid4()
    session_id = str(conversation_id)
    client_turn_id = uuid4()
    anchor = await _seed_recommendation_anchor(unit_of_work, conversation_id, "customer-1")
    graph = DetectorGraph(detector, anchor)
    first = await run_turn(
        graph,
        services,
        session_id=session_id,
        customer_id="customer-1",
        user_message="Giá hơi cao",
        client_turn_id=client_turn_id,
    )

    # When
    replay = await run_turn(
        graph,
        services,
        session_id=session_id,
        customer_id="customer-1",
        user_message="payload retry khác",
        client_turn_id=client_turn_id,
    )

    # Then
    assert replay == first
    assert graph.calls == 1
    assert detector.calls == 1
    assert replay.bottleneck_detection is None
    assert await _counts(migrated_engine) == (2, 1, 1)


@pytest.mark.asyncio
async def test_live_and_replay_agree_on_projected_customer_content(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """[Todo 9] Nội dung khách nhận (live) == nội dung replay, và sạch marker.

    Mapper chạy trước khi persist (safe-before-persistence) và lại ở biên công
    khai; replay đọc outcome đã project. Hai đường phải trả về y hệt nhau.
    """

    services, detector, unit_of_work = _services(migrated_engine)
    conversation_id = uuid4()
    session_id = str(conversation_id)
    client_turn_id = uuid4()
    anchor = await _seed_recommendation_anchor(unit_of_work, conversation_id, "customer-1")
    raw_uuid = "550e8400-e29b-41d4-a716-446655440000"
    graph = DetectorGraph(
        detector,
        anchor,
        answer=f"Em muốn mua VF 8 giá 1090000000 đồng [evidence_id:{raw_uuid}].",
    )

    first = await run_turn(
        graph,
        services,
        session_id=session_id,
        customer_id="customer-1",
        user_message="Giá hơi cao",
        client_turn_id=client_turn_id,
    )
    replay = await run_turn(
        graph,
        services,
        session_id=session_id,
        customer_id="customer-1",
        user_message="payload retry khác",
        client_turn_id=client_turn_id,
    )

    assert first.answer == "Quý khách muốn mua VF 8 giá 1.090.000.000 đồng."
    assert raw_uuid not in first.answer
    assert replay == first
    assert graph.calls == 1
