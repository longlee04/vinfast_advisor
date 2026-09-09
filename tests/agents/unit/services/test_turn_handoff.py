"""Chuyển lượt sang tư vấn viên phải là MỘT giao dịch, không phải ba lần ghi rời.

Hiện `tạo run` · `đẩy hàng đợi` · `chốt outcome` nằm ở ba chỗ khác nhau. Hỏng
giữa chừng là để lại một mục duyệt mồ côi: tư vấn viên thấy việc cần làm, còn
khách thì không có lượt nào ứng với nó.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from src.agents.domain.conversation_memory import (
    TurnClaim,
    TurnOutcome,
    TurnOutcomeStatus,
)
from src.agents.domain.values import HitlReason
from src.agents.services.turn_handoff import TurnHandoffService

SESSION = UUID("11111111-1111-1111-1111-111111111111")
CLIENT_TURN = UUID("22222222-2222-2222-2222-222222222222")
RUN = UUID("33333333-3333-3333-3333-333333333333")
REVIEW = UUID("44444444-4444-4444-4444-444444444444")


class _Outcomes:
    def __init__(self, existing: TurnOutcome | None = None) -> None:
        self.existing = existing
        self.finalized: list[TurnOutcome] = []
        self.failures: list[str] = []

    async def claim(self, conversation_id, customer_id, client_turn_id) -> TurnClaim:
        if self.existing is not None:
            return TurnClaim(outcome=self.existing, claimed=False)
        pending = TurnOutcome(
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=1,
            status=TurnOutcomeStatus.IN_PROGRESS,
        )
        return TurnClaim(outcome=pending, claimed=True)

    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        self.finalized.append(outcome)
        return outcome

    async def fail(self, conversation_id, client_turn_id, *, error_category) -> None:
        self.failures.append(error_category)


class _Runs:
    def __init__(self) -> None:
        self.created = 0

    async def create_run(self, session_id: str) -> UUID:
        self.created += 1
        return RUN


class _Queue:
    def __init__(self, *, explode: bool = False) -> None:
        self.enqueued: list[str] = []
        self._explode = explode

    async def enqueue(self, run_id, session_id, content, *, snapshot=None) -> UUID:
        self.enqueued.append(content)
        if self._explode:
            raise RuntimeError("mat ket noi ngay sau khi flush")
        return REVIEW


class _Transaction:
    def __init__(self, outcomes: _Outcomes, runs: _Runs, queue: _Queue) -> None:
        self.outcomes = outcomes
        self.runs = runs
        self.review_queue = queue


class _UnitOfWork:
    """Ghi lại việc transaction đã commit hay rollback."""

    def __init__(self, transaction: _Transaction) -> None:
        self._transaction = transaction
        self.committed = False
        self.rolled_back = False

    def transaction(self):
        outer = self

        class _Ctx:
            async def __aenter__(self):
                return outer._transaction

            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    outer.committed = True
                else:
                    outer.rolled_back = True
                return False

        return _Ctx()


def _service(
    *, existing: TurnOutcome | None = None, explode: bool = False
) -> tuple[TurnHandoffService, _UnitOfWork, _Outcomes, _Runs, _Queue]:
    outcomes, runs, queue = _Outcomes(existing), _Runs(), _Queue(explode=explode)
    unit = _UnitOfWork(_Transaction(outcomes, runs, queue))
    return TurnHandoffService(unit), unit, outcomes, runs, queue


@pytest.mark.asyncio
async def test_one_transaction_creates_the_run_queues_and_finalizes() -> None:
    service, unit, outcomes, runs, queue = _service()

    result = await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=CLIENT_TURN,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="CUSTOMER_REQUESTED_HUMAN | cho tôi gặp tư vấn viên",
    )

    assert unit.committed is True
    assert runs.created == 1
    assert len(queue.enqueued) == 1
    assert len(outcomes.finalized) == 1
    assert result.review_id == REVIEW
    assert result.awaiting_review is True
    assert result.terminal_reason is None


@pytest.mark.asyncio
async def test_a_failure_after_the_queue_flush_rolls_everything_back() -> None:
    """Ca QA của plan: hỏng sau khi flush hàng đợi, trước khi chốt outcome."""

    service, unit, outcomes, _runs, queue = _service(explode=True)

    with pytest.raises(RuntimeError):
        await service.handoff(
            session_id=str(SESSION),
            customer_id="khach",
            client_turn_id=CLIENT_TURN,
            reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
            customer_message="cho tôi gặp tư vấn viên",
            advisor_content="noi dung",
        )

    assert unit.rolled_back is True
    assert unit.committed is False
    assert outcomes.finalized == [], "khong duoc chot outcome khi hang doi hong"


@pytest.mark.asyncio
async def test_a_replayed_turn_returns_the_same_review_and_writes_nothing() -> None:
    """Khách bấm gửi lại: phải trả đúng `review_id` cũ, không tạo mục thứ hai."""

    existing = TurnOutcome(
        conversation_id=SESSION,
        client_turn_id=CLIENT_TURN,
        turn_number=1,
        status=TurnOutcomeStatus.WAITING_REVIEW,
        answer="Phần này anh tư vấn viên hỗ trợ tốt hơn ạ.",
        review_id=REVIEW,
    )
    service, _unit, outcomes, runs, queue = _service(existing=existing)

    result = await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=CLIENT_TURN,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="noi dung",
    )

    assert result.review_id == REVIEW
    assert runs.created == 0, "khong duoc tao run thu hai"
    assert queue.enqueued == [], "khong duoc day hang doi lan hai"
    assert outcomes.finalized == []


@pytest.mark.asyncio
async def test_advisor_content_never_reaches_the_customer_answer() -> None:
    """Nội dung cho tư vấn viên và câu khách đọc là HAI thứ khác nhau."""

    service, _unit, _outcomes, _runs, queue = _service()

    result = await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=CLIENT_TURN,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="xe của tôi đang bốc khói",
        advisor_content="NOI DUNG NOI BO CHUA KIEM CHUNG",
    )

    assert queue.enqueued == ["NOI DUNG NOI BO CHUA KIEM CHUNG"]
    assert "NOI DUNG NOI BO" not in (result.answer or "")
    assert result.answer, "khach van phai nhan mot cau tra loi"


@pytest.mark.asyncio
async def test_a_turn_without_a_client_key_still_hands_off() -> None:
    """Không có khoá khử trùng lặp thì vẫn phải chuyển người, chỉ là best-effort."""

    service, unit, _outcomes, runs, queue = _service()

    result = await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=None,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="noi dung",
    )

    assert unit.committed is True
    assert runs.created == 1
    assert len(queue.enqueued) == 1
    assert result.review_id == REVIEW


@pytest.mark.asyncio
async def test_an_existing_run_is_reused_instead_of_creating_another() -> None:
    """Guardrail cạn lượt đã có `run_id` — không được tạo run thứ hai."""

    service, _unit, _outcomes, runs, _queue = _service()

    await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=CLIENT_TURN,
        reason=HitlReason.LOW_CONFIDENCE,
        customer_message="cau hoi",
        advisor_content="ban nhap",
        run_id=RUN,
    )

    assert runs.created == 0


@pytest.mark.asyncio
async def test_the_finalized_outcome_carries_the_review_id_and_waiting_status() -> None:
    service, _unit, outcomes, _runs, _queue = _service()

    await service.handoff(
        session_id=str(SESSION),
        customer_id="khach",
        client_turn_id=CLIENT_TURN,
        reason=HitlReason.CUSTOMER_REQUESTED_HUMAN,
        customer_message="cho tôi gặp tư vấn viên",
        advisor_content="noi dung",
    )

    stored = outcomes.finalized[0]
    assert stored.status is TurnOutcomeStatus.WAITING_REVIEW
    assert stored.review_id == REVIEW
    assert stored.terminal_reason is None
    assert replace(stored, answer=None).answer is None  # dataclass bất biến
