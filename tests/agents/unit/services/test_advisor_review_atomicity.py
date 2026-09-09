"""Mục hàng duyệt và outcome của lượt phải cùng sống hoặc cùng chết.

Trước đây `EnqueueHitlNode` ghi mục duyệt bằng transaction RIÊNG ngay trong graph,
còn outcome của lượt được chốt ở một transaction khác sau khi graph trả về. Bước
sau hỏng thì bước trước đã commit: còn lại một mục duyệt **mồ côi** — tư vấn viên
thấy một việc phải làm, khách không có lượt nào ứng với nó, và lần gửi lại sinh
thêm mục thứ hai cho cùng một câu.

Bộ test này khoá hình dạng mới: node chỉ dựng nội dung, và `finalize_turn` ghi mục
duyệt bên trong chính transaction chốt outcome.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.domain.conversation_memory import TurnOutcome
from src.agents.services.conversation_memory import (
    AdvisorReviewRequest,
    ConversationMemoryService,
)

RUN_ID = UUID("10000000-0000-0000-0000-0000000000aa")


class ForcedFailureError(Exception):
    """Lỗi hạ tầng xảy ra SAU khi mục duyệt đã được ghi trong transaction."""


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
    fail_on_finalize: bool = False


    async def assert_core_turn_lease(self, lease: object) -> None:
        """Hàng rào lease của `commit_core_turn`; fake mặc định coi là còn hợp lệ."""

        self.lease_checked = getattr(self, "lease_checked", 0) + 1
    async def get(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome | None:
        del conversation_id, customer_id
        return next(
            (outcome for outcome in self.staged if outcome.client_turn_id == client_turn_id),
            None,
        )

    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        if self.fail_on_finalize:
            raise ForcedFailureError("ghi outcome hỏng")
        self.staged.append(outcome)
        return outcome


class Sessions:
    async def upsert_slot(self, session_id: str, slot_name: str, value: object) -> None:
        del session_id, slot_name, value


@dataclass
class AppendedMessage:
    message_id: UUID
    turn_index: int


class Memory:
    """Lượt hoàn tất có ghi transcript; lượt vào hàng duyệt thì không."""

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


class BottleneckSignals:
    async def insert(self, signal: object) -> None:  # pragma: no cover
        del signal


@dataclass
class Transaction:
    review_queue: ReviewQueue
    outcomes: Outcomes
    sessions: Sessions
    memory: Memory
    bottleneck_signals: BottleneckSignals


class Uow:
    """Transaction thật sự nguyên tử: thoát sạch mới chuyển staged sang committed."""

    def __init__(self, *, fail_on_finalize: bool = False) -> None:
        self.review_queue = ReviewQueue()
        self.outcomes = Outcomes(fail_on_finalize=fail_on_finalize)
        self.memory = Memory()
        self.transaction_value = Transaction(
            self.review_queue, self.outcomes, Sessions(), self.memory, BottleneckSignals()
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        try:
            yield self.transaction_value
        except Exception:
            self.review_queue.staged.clear()
            self.outcomes.staged.clear()
            raise
        self.review_queue.committed.extend(self.review_queue.staged)
        self.review_queue.staged.clear()
        self.outcomes.committed.extend(self.outcomes.staged)
        self.outcomes.staged.clear()


class Summarizer:
    model_name = "fake"

    async def summarize(self, **kwargs: object) -> str:  # pragma: no cover
        return ""


def _handoff_result(session_id: str) -> TurnResult:
    return TurnResult(
        session_id=session_id,
        answer="Em xin Quý khách đợi em xác nhận lại thông tin này ạ.",
        pending_question=None,
        awaiting_review=True,
        turn_status="WAITING_REVIEW",
    )


@pytest.mark.asyncio
async def test_review_row_and_outcome_commit_together() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())

    finalized = await service.finalize_turn(
        session_id=session_id,
        customer_id="khach-1",
        client_turn_id=uuid4(),
        user_message="giảm giá được không",
        result=_handoff_result(session_id),
        slots={},
        advisor_review=AdvisorReviewRequest(run_id=RUN_ID, content="Bản nháp cho tư vấn viên."),
    )

    assert len(uow.review_queue.committed) == 1, "đúng MỘT mục duyệt cho một lượt"
    assert uow.review_queue.committed[0][0] == RUN_ID
    assert uow.memory.appended == [], "bản nháp chưa duyệt không được vào transcript khách"
    assert len(uow.outcomes.committed) == 1
    # `review_id` sinh trong transaction phải đi thẳng vào outcome — khách tra cứu
    # lượt của mình là thấy đúng mục duyệt đang chờ người xử lý.
    assert uow.outcomes.committed[0].review_id is not None
    assert finalized.review_id == uow.outcomes.committed[0].review_id


@pytest.mark.asyncio
async def test_a_failure_after_enqueue_leaves_no_orphan_review() -> None:
    """Đây chính là con bug mà hai transaction rời để lại."""

    uow = Uow(fail_on_finalize=True)
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())

    with pytest.raises(ForcedFailureError):
        await service.finalize_turn(
            session_id=session_id,
            customer_id="khach-1",
            client_turn_id=uuid4(),
            user_message="giảm giá được không",
            result=_handoff_result(session_id),
            slots={},
            advisor_review=AdvisorReviewRequest(run_id=RUN_ID, content="Bản nháp cho tư vấn viên."),
        )

    assert uow.review_queue.committed == [], "không được để lại mục duyệt mồ côi"
    assert uow.outcomes.committed == []


@pytest.mark.asyncio
async def test_a_turn_without_handoff_writes_no_review_row() -> None:
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())
    session_id = str(uuid4())

    await service.finalize_turn(
        session_id=session_id,
        customer_id="khach-1",
        client_turn_id=uuid4(),
        user_message="VF 8 giá bao nhiêu",
        result=TurnResult(
            session_id=session_id,
            answer=None,
            pending_question="Quý khách đi bao nhiêu km mỗi ngày ạ?",
        ),
        slots={},
    )

    assert uow.review_queue.committed == []
