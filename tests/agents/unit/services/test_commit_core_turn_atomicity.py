"""`commit_core_turn` phải ghi core_state + outcome + HITL + trace trong MỘT transaction.

Đây là đường ghi duy nhất của lõi v2 (Task 3, `luong-hoi-thoai-v2-buoc-3`). Khác
`finalize_turn`, nó còn ghi thêm `conversation_core_state` và `turn_traces` — và cả
hai đó nằm TRONG cùng transaction với `outcomes.finalize`/`review_queue.enqueue`.
Hỏng bất cứ bước nào (kể cả bước quan sát `turn_traces.record`) phải cuốn theo
TẤT CẢ, không để lại trạng thái mồ côi — cùng lý do `test_advisor_review_atomicity.py`
khoá hình dạng cho `finalize_turn`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.core.state import CoreState
from src.agents.domain.conversation_memory import CoreTurnLease, TurnOutcome
from src.agents.domain.turn_trace import TurnTrace
from src.agents.errors import CoreTurnLeaseStaleError
from src.agents.services.conversation_memory import (
    AdvisorReviewRequest,
    ConversationMemoryService,
)

RUN_ID = UUID("20000000-0000-0000-0000-0000000000bb")


class ForcedFailureError(Exception):
    """Lỗi hạ tầng xảy ra Ở BƯỚC CUỐI của transaction (ghi vệt quan sát)."""


@dataclass
class ReviewQueue:
    committed: list[tuple[UUID, UUID, str]] = field(default_factory=list)
    staged: list[tuple[UUID, UUID, str]] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, session_id: UUID, content: str, *, snapshot: object | None = None) -> UUID:
        del snapshot
        self.staged.append((run_id, session_id, content))
        return uuid4()


@dataclass
class Outcomes:
    committed: list[TurnOutcome] = field(default_factory=list)
    staged: list[TurnOutcome] = field(default_factory=list)


    async def assert_core_turn_lease(self, lease: object) -> None:
        """Hàng rào lease của `commit_core_turn`; fake mặc định coi là còn hợp lệ."""

        self.lease_checked = getattr(self, "lease_checked", 0) + 1
    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        self.staged.append(outcome)
        return outcome


class Sessions:
    def __init__(self) -> None:
        self.upserted: list[tuple[str, str, object]] = []

    async def upsert_slot(self, session_id: str, slot_name: str, value: object) -> None:
        self.upserted.append((session_id, slot_name, value))


@dataclass
class AppendedMessage:
    message_id: UUID
    turn_index: int


class Memory:
    def __init__(self) -> None:
        self.appended: list[str] = []

    async def append(
        self, session_id: str, customer_id: str, role: str, content: str, client_turn_id: UUID | None
    ) -> AppendedMessage:
        del session_id, customer_id, role, client_turn_id
        self.appended.append(content)
        return AppendedMessage(message_id=uuid4(), turn_index=len(self.appended))

    async def load_recent(self, *args: object, **kwargs: object) -> tuple[None, tuple]:
        return None, ()


@dataclass
class CoreStateRepo:
    committed: list[object] = field(default_factory=list)
    staged: list[object] = field(default_factory=list)

    async def save(self, state: object) -> None:
        self.staged.append(state)

    async def load(self, session_id: str) -> object | None:
        del session_id
        return None

    async def exists(self, session_id: str) -> bool:
        del session_id
        return False


@dataclass
class TurnTraces:
    committed: list[TurnTrace] = field(default_factory=list)
    staged: list[TurnTrace] = field(default_factory=list)
    fail_on_record: bool = False

    async def record(self, trace: TurnTrace) -> None:
        if self.fail_on_record:
            raise ForcedFailureError("ghi vệt hỏng")
        self.staged.append(trace)


@dataclass
class Transaction:
    review_queue: ReviewQueue
    outcomes: Outcomes
    sessions: Sessions
    memory: Memory
    core_state: CoreStateRepo
    turn_traces: TurnTraces


class Uow:
    """Transaction thật sự nguyên tử: thoát sạch mới chuyển staged sang committed."""

    def __init__(self, *, fail_on_record_trace: bool = False) -> None:
        self.review_queue = ReviewQueue()
        self.outcomes = Outcomes()
        self.sessions = Sessions()
        self.memory = Memory()
        self.core_state = CoreStateRepo()
        self.turn_traces = TurnTraces(fail_on_record=fail_on_record_trace)
        self.transaction_value = Transaction(
            self.review_queue, self.outcomes, self.sessions, self.memory, self.core_state, self.turn_traces
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        try:
            yield self.transaction_value
        except Exception:
            self.review_queue.staged.clear()
            self.outcomes.staged.clear()
            self.core_state.staged.clear()
            self.turn_traces.staged.clear()
            raise
        self.review_queue.committed.extend(self.review_queue.staged)
        self.review_queue.staged.clear()
        self.outcomes.committed.extend(self.outcomes.staged)
        self.outcomes.staged.clear()
        self.core_state.committed.extend(self.core_state.staged)
        self.core_state.staged.clear()
        self.turn_traces.committed.extend(self.turn_traces.staged)
        self.turn_traces.staged.clear()


class Summarizer:
    model_name = "fake"

    async def summarize(self, **kwargs: object) -> str:  # pragma: no cover
        return ""


def _handoff_result(session_id: str) -> TurnResult:
    return TurnResult(
        session_id=session_id,
        answer="Dạ em đã chuyển thông tin này cho tư vấn viên hỗ trợ anh/chị ạ.",
        pending_question=None,
        awaiting_review=True,
        turn_status="WAITING_REVIEW",
    )


def _fake_trace(session_id: str, client_turn_id: UUID) -> TurnTrace:
    return TurnTrace(
        session_id=session_id,
        client_turn_id=str(client_turn_id),
        user_message="giảm giá được không",
        intent_hint="NEGOTIATE",
        confidence=0.9,
        tier="deterministic",
        scope_label="IN_SCOPE",
        terminal_reason=None,
        routing_enabled=True,
    )


def _lease(session_id: str, client_turn_id: UUID) -> CoreTurnLease:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=UUID(session_id),
        client_turn_id=client_turn_id,
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


@pytest.mark.asyncio
async def test_all_six_writes_commit_together() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())
    client_turn_id = uuid4()
    core_state = CoreState(session_id=session_id)

    result = await service.commit_core_turn(
        lease=_lease(session_id, client_turn_id),
        customer_id="khach-1",
        user_message="giảm giá được không",
        result=_handoff_result(session_id),
        core_state=core_state,
        trace=_fake_trace(session_id, client_turn_id),
        advisor_review=AdvisorReviewRequest(run_id=RUN_ID, content="Bản nháp cho tư vấn viên."),
    )

    assert len(uow.review_queue.committed) == 1
    assert uow.review_queue.committed[0][0] == RUN_ID
    assert len(uow.outcomes.committed) == 1
    assert uow.core_state.committed == [core_state]
    assert len(uow.turn_traces.committed) == 1
    # Câu "đã chuyển tư vấn viên" của lõi v2 PHẢI vào transcript dù đang chờ
    # duyệt — khác `finalize_turn`, đây là điểm khác biệt cố ý (mục 8 chỉ số 5).
    assert uow.memory.appended == ["giảm giá được không", result.answer]
    assert result.review_id == uow.outcomes.committed[0].review_id
    assert result.awaiting_review is True


@pytest.mark.asyncio
async def test_turn_traces_failure_rolls_back_everything() -> None:
    """Đây chính là con bug: ghi state được mà mất vệt thì đọc lại một lỗ đen."""

    uow = Uow(fail_on_record_trace=True)
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())
    client_turn_id = uuid4()

    with pytest.raises(ForcedFailureError):
        await service.commit_core_turn(
            lease=_lease(session_id, client_turn_id),
            customer_id="khach-1",
            user_message="giảm giá được không",
            result=_handoff_result(session_id),
            core_state=CoreState(session_id=session_id),
            trace=_fake_trace(session_id, client_turn_id),
            advisor_review=AdvisorReviewRequest(run_id=RUN_ID, content="Bản nháp cho tư vấn viên."),
        )

    assert uow.review_queue.committed == [], "không để lại mục duyệt mồ côi"
    assert uow.outcomes.committed == [], "outcome không được chốt nếu vệt hỏng"
    assert uow.core_state.committed == [], "core_state không được chốt nếu vệt hỏng"
    assert uow.turn_traces.committed == []


@pytest.mark.asyncio
async def test_no_advisor_review_writes_no_review_row() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())
    client_turn_id = uuid4()

    result = await service.commit_core_turn(
        lease=_lease(session_id, client_turn_id),
        customer_id="khach-1",
        user_message="VF 8 giá bao nhiêu",
        result=TurnResult(
            session_id=session_id,
            answer="Dạ VF 8 giá niêm yết như sau ạ.",
            pending_question=None,
        ),
        core_state=CoreState(session_id=session_id),
        trace=_fake_trace(session_id, client_turn_id),
    )

    assert uow.review_queue.committed == []
    assert len(uow.core_state.committed) == 1
    assert len(uow.turn_traces.committed) == 1
    assert result.review_id is None
    assert result.awaiting_review is False


@pytest.mark.asyncio
async def test_stale_lease_writes_nothing_at_all() -> None:
    """Thợ cũ bị giành mất lượt thì KHÔNG được ghi một dòng nào.

    Kiểm lease ở ngoài transaction chỉ chặn sớm: giữa lúc kiểm xong và lúc ghi,
    lease có thể hết hạn rồi bị lượt khác chiếm. Hàng rào phải nằm TRONG chính
    transaction ghi, trước dòng chữ đầu tiên — hỏng là cả khối cùng quay đầu.
    """

    uow = Uow()

    async def _stale(_lease: object) -> None:
        raise CoreTurnLeaseStaleError(
            session_id="s", client_turn_id="c", reason="token_mismatch"
        )

    uow.outcomes.assert_core_turn_lease = _stale  # type: ignore[method-assign]
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())
    client_turn_id = uuid4()

    with pytest.raises(CoreTurnLeaseStaleError):
        await service.commit_core_turn(
            lease=_lease(session_id, client_turn_id),
            customer_id="khach-1",
            user_message="VF 8 giá bao nhiêu",
            result=TurnResult(session_id=session_id, answer="Dạ.", pending_question=None),
            core_state=CoreState(session_id=session_id),
            trace=_fake_trace(session_id, client_turn_id),
        )

    assert uow.memory.appended == []
    assert uow.outcomes.committed == []
    assert uow.core_state.committed == []
    assert uow.turn_traces.committed == []
    assert uow.review_queue.committed == []
