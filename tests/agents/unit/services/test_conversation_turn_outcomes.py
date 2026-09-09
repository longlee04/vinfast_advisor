from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import (
    Citation,
    RecommendedVehicleView,
    TurnResult,
    VehicleFacts,
)
from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionStatus,
    ConfirmedBottleneckEvidence,
    SignalInsert,
)
from src.agents.domain.conversation_memory import (
    ConversationMessage,
    ConversationSummary,
    TurnClaim,
    TurnOutcome,
    TurnOutcomeStatus,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.domain.values import SlotName, VehicleType
from src.agents.errors import TurnFailedError, TurnInProgressError
from src.agents.services.conversation_memory import ConversationMemoryService


class MemoryRepository:
    def __init__(self) -> None:
        self.messages: list[ConversationMessage] = []
        self.summary: ConversationSummary | None = None

    async def find_by_client_turn(
        self, session_id: str, customer_id: str, client_turn_id: UUID
    ) -> tuple[ConversationMessage, ...]:
        del session_id, customer_id
        return tuple(message for message in self.messages if message.client_turn_id == client_turn_id)

    async def append(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        client_turn_id: UUID | None,
    ) -> ConversationMessage:
        del customer_id
        existing = next(
            (message for message in self.messages if message.client_turn_id == client_turn_id and message.role == role),
            None,
        )
        if existing is not None:
            return existing
        message = ConversationMessage(
            role=role,
            content=content,
            turn_index=len(self.messages) + 1,
            message_id=uuid4(),
            conversation_id=UUID(session_id),
            client_turn_id=client_turn_id,
            created_at=datetime(2026, 8, 15, tzinfo=UTC),
        )
        self.messages.append(message)
        return message

    async def load_recent(
        self, session_id: str, customer_id: str, limit: int
    ) -> tuple[ConversationSummary | None, tuple[ConversationMessage, ...]]:
        del session_id, customer_id
        through = self.summary.summarized_through_turn if self.summary else 0
        return self.summary, tuple(message for message in self.messages[-limit:] if message.turn_index > through)

    async def save_summary(self, session_id: str, customer_id: str, summary: ConversationSummary) -> None:
        del session_id, customer_id
        self.summary = summary


class OutcomeRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, TurnOutcome] = {}

    async def claim(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnClaim:
        del customer_id
        existing = self.values.get(client_turn_id)
        if existing is not None:
            return TurnClaim(existing, False)
        outcome = TurnOutcome(
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=len(self.values) + 1,
            status=TurnOutcomeStatus.IN_PROGRESS,
        )
        self.values[client_turn_id] = outcome
        return TurnClaim(outcome, True)

    async def latest(self, conversation_id: UUID, customer_id: str) -> TurnOutcome | None:
        del customer_id
        candidates = [outcome for outcome in self.values.values() if outcome.conversation_id == conversation_id]
        if not candidates:
            return None
        return max(candidates, key=lambda outcome: outcome.turn_number)

    async def get(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome | None:
        del conversation_id, customer_id
        return self.values.get(client_turn_id)

    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        existing = self.values[outcome.client_turn_id]
        finalized = replace(outcome, turn_number=existing.turn_number)
        self.values[outcome.client_turn_id] = finalized
        return finalized

    async def fail(
        self,
        conversation_id: UUID,
        client_turn_id: UUID,
        *,
        error_category: str,
    ) -> TurnOutcome:
        existing = self.values[client_turn_id]
        failed = TurnOutcome(
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=existing.turn_number,
            status=TurnOutcomeStatus.FAILED,
            error_category=error_category,
        )
        self.values[client_turn_id] = failed
        return failed


class BottleneckSignals:
    def __init__(self) -> None:
        self.anchor: UUID | None = None
        self.evidence: tuple[ConfirmedBottleneckEvidence, ...] = ()
        self.inserted: list[SignalInsert] = []

    async def latest_recommendation_anchor(self, session_id: UUID, current_client_turn_id: UUID) -> UUID | None:
        del session_id, current_client_turn_id
        return self.anchor

    async def confirmed_evidence(
        self, session_id: UUID, anchor_client_turn_id: UUID
    ) -> tuple[ConfirmedBottleneckEvidence, ...]:
        del session_id, anchor_client_turn_id
        return self.evidence

    async def insert(self, signal: SignalInsert) -> None:
        self.inserted.append(signal)


class Sessions:
    def __init__(self) -> None:
        self.slots: dict[SlotName, object] = {}

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: object) -> None:
        del session_id
        self.slots[slot_name] = value


@dataclass
class Transaction:
    memory: MemoryRepository
    outcomes: OutcomeRepository
    sessions: Sessions
    bottleneck_signals: BottleneckSignals


class Uow:
    def __init__(self) -> None:
        self.transaction_value = Transaction(MemoryRepository(), OutcomeRepository(), Sessions(), BottleneckSignals())

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        yield self.transaction_value


class Summarizer:
    model_name = "fake-summary"

    async def summarize(self, *, previous_summary: str, user_message: str, assistant_response: str) -> str:
        del previous_summary
        return f"{user_message} {assistant_response}"


@pytest.mark.asyncio
async def test_completed_key_replays_exact_result_without_second_user_append() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="VF 7 giá bao nhiêu?",
        slots={},
    )
    fact = VehicleFacts(
        vehicle_id=uuid4(),
        display_name="VF 7",
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=Decimal("799000000"),
        specs={"seats": 5},
    )

    finalized = await service.finalize_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="VF 7 giá bao nhiêu?",
        result=TurnResult(
            session_id=str(conversation_id),
            answer=None,
            pending_question=None,
            terminal_reason="CATALOG_LOOKUP",
            lookup_facts=[fact],
        ),
        slots={"vehicle_type": "CAR"},
    )
    replay = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="retry payload khác",
        slots={},
    )

    assert finalized.lookup_facts == [fact]
    assert replay.replayed_result is not None
    assert replay.replayed_result.lookup_facts == [fact]
    assert [message.role for message in uow.transaction_value.memory.messages] == [
        "USER",
        "ASSISTANT",
    ]
    assert uow.transaction_value.sessions.slots[SlotName.VEHICLE_TYPE] == "CAR"


@pytest.mark.asyncio
async def test_in_progress_and_failed_keys_never_run_as_new_claims() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    kwargs = {
        "session_id": str(conversation_id),
        "customer_id": "customer-1",
        "client_turn_id": client_turn_id,
        "user_message": "Tôi cần xe gia đình.",
        "slots": {},
    }
    await service.start_turn(**kwargs)

    with pytest.raises(TurnInProgressError):
        await service.start_turn(**kwargs)

    await service.fail_turn(
        session_id=str(conversation_id),
        client_turn_id=client_turn_id,
        error_category="GRAPH_FAILURE",
    )
    with pytest.raises(TurnFailedError) as raised:
        await service.start_turn(**kwargs)
    assert raised.value.category == "GRAPH_FAILURE"


@pytest.mark.asyncio
async def test_waiting_review_persists_no_assistant_draft() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    review_id = uuid4()
    await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Hãy đề xuất xe.",
        slots={},
    )

    result = await service.finalize_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Hãy đề xuất xe.",
        result=TurnResult(
            session_id=str(conversation_id),
            answer="Đang chờ tư vấn viên duyệt.",
            pending_question=None,
            review_id=review_id,
            turn_status="WAITING_REVIEW",
        ),
        slots={},
    )

    assert result.turn_status == "WAITING_REVIEW"
    assert result.awaiting_review is True
    assert result.review_id == review_id
    assert [message.role for message in uow.transaction_value.memory.messages] == ["USER"]

    replayed = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Hãy đề xuất xe.",
        slots={},
    )
    assert replayed.replayed_result is not None
    assert replayed.replayed_result.awaiting_review is True
    assert replayed.replayed_result.review_id == review_id


VEHICLE_ID = UUID("20000000-0000-0000-0000-000000000101")
EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000101")


def _recommendation() -> RecommendedVehicleView:
    return RecommendedVehicleView(
        vehicle_id=VEHICLE_ID,
        rank=1,
        display_name="VF 8",
        image_url="https://cdn/vf8.png",
        starting_price_vnd="1090000000",
        pitch="VF 8 đi 399 km [1].",
        citations=(Citation(index=1, evidence_id=EVIDENCE_ID, source_record="cars:row"),),
    )


@pytest.mark.asyncio
async def test_completed_replay_returns_full_recommendations() -> None:
    """[C3] Lượt COMPLETED phải replay đủ card: pitch + citations nguyên vẹn."""

    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Đề xuất xe.",
        slots={},
    )

    finalized = await service.finalize_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Đề xuất xe.",
        result=TurnResult(
            session_id=str(conversation_id),
            answer="VF 8 đi 399 km [1].",
            pending_question=None,
            recommendations=[_recommendation()],
        ),
        slots={},
    )
    replay = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="retry",
        slots={},
    )

    assert finalized.recommendations == [_recommendation()]
    assert replay.replayed_result is not None
    assert replay.replayed_result.recommendations == [_recommendation()]


@pytest.mark.asyncio
async def test_waiting_review_replay_hides_pitch_but_keeps_card_data() -> None:
    """[C3+C1] Replay lượt WAITING_REVIEW giữ dữ liệu card nhưng che pitch/citations."""

    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    review_id = uuid4()
    await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Đề xuất xe.",
        slots={},
    )

    finalized = await service.finalize_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Đề xuất xe.",
        result=TurnResult(
            session_id=str(conversation_id),
            answer="Đang chờ tư vấn viên duyệt.",
            pending_question=None,
            review_id=review_id,
            turn_status="WAITING_REVIEW",
            recommendations=[_recommendation()],
        ),
        slots={},
    )
    replay = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="retry",
        slots={},
    )

    assert finalized.recommendations[0].pitch == ""
    assert finalized.recommendations[0].citations == ()
    assert finalized.recommendations[0].vehicle_id == VEHICLE_ID
    assert finalized.recommendations[0].display_name == "VF 8"
    assert finalized.recommendations[0].image_url == "https://cdn/vf8.png"
    assert finalized.recommendations[0].starting_price_vnd == "1090000000"

    assert replay.replayed_result is not None
    assert replay.replayed_result.recommendations[0].pitch == ""
    assert replay.replayed_result.recommendations[0].citations == ()
    assert replay.replayed_result.recommendations[0].vehicle_id == VEHICLE_ID

    # Bài chưa duyệt không được NẰM SẴN trong payload đã lưu: che ở chỗ đọc là
    # chưa đủ, vì mọi đường đọc mới (recovery HTTP, HITL refresh) đều phải nhớ
    # gọi lại phép chiếu. Soi thẳng dữ liệu thô mới khoá được điều đó.
    stored = uow.transaction_value.outcomes.values[client_turn_id]
    raw = json.dumps(stored.result_payload or {}, ensure_ascii=False)
    assert "VF 8 đi 399 km" not in raw
    assert "https://cdn/vf8.png" in raw


@pytest.mark.asyncio
async def test_replay_projects_legacy_raw_outcome() -> None:
    """[Todo 9] Outcome persist TRƯỚC mapper (raw) phải được project khi replay.

    Outcome cũ chứa marker nội bộ + số thô; `_turn_result` project ở biên replay
    để khách nhận bản sạch, đọc được — không cần migrate dữ liệu cũ.
    """

    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    raw_uuid = "550e8400-e29b-41d4-a716-446655440000"
    uow.transaction_value.outcomes.values[client_turn_id] = TurnOutcome(
        conversation_id=conversation_id,
        client_turn_id=client_turn_id,
        turn_number=1,
        status=TurnOutcomeStatus.COMPLETED,
        answer=f"Giá 1090000000 đồng [evidence_id:{raw_uuid}].",
        pending_question=None,
    )

    started = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="retry",
        slots={},
    )

    assert started.replayed_result is not None
    assert started.replayed_result.answer == "Giá 1.090.000.000 đồng."
    assert raw_uuid not in started.replayed_result.answer


@pytest.mark.asyncio
async def test_claim_returns_identity_anchor_and_confirmed_evidence() -> None:
    # Given
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    anchor_id = uuid4()
    evidence = ConfirmedBottleneckEvidence(
        signal_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=2,
        label=Bottleneck.PRICE,
        evidence_quote="Giá cao",
    )
    uow.transaction_value.bottleneck_signals.anchor = anchor_id
    uow.transaction_value.bottleneck_signals.evidence = (evidence,)

    # When
    started = await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Tôi còn ngại giá",
        slots={},
    )

    # Then
    assert started.outcome is not None
    assert started.outcome.client_turn_id == client_turn_id
    assert started.anchor_client_turn_id == anchor_id
    assert started.confirmed_evidence == (evidence,)


@pytest.mark.asyncio
async def test_finalize_inserts_detected_signal_with_outcome() -> None:
    # Given
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    conversation_id = uuid4()
    client_turn_id = uuid4()
    anchor_id = uuid4()
    await service.start_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Giá hơi cao",
        slots={},
    )
    detected = BottleneckDetected(
        status=BottleneckDetectionStatus.DETECTED,
        label=Bottleneck.PRICE,
        evidence_quote="Giá hơi cao",
    )

    # When
    await service.finalize_turn(
        session_id=str(conversation_id),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Giá hơi cao",
        result=TurnResult(
            session_id=str(conversation_id),
            answer="Em hiểu.",
            pending_question=None,
            bottleneck_detection=detected,
            bottleneck_anchor_client_turn_id=anchor_id,
        ),
        slots={},
    )

    # Then
    inserted = uow.transaction_value.bottleneck_signals.inserted
    assert len(inserted) == 1
    assert inserted[0].client_turn_id == client_turn_id
    assert inserted[0].anchor_client_turn_id == anchor_id
    assert inserted[0].label is Bottleneck.PRICE
