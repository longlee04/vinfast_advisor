from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.agents.domain.conversation_memory import ConversationMessage, TurnOutcomeStatus
from src.agents.services.operations.review import ReviewItem, ReviewOperations
from src.agents.services.operations.turn_events import TurnEvent

HEX_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class Queue:
    def __init__(self, item: ReviewItem) -> None:
        self.item = item

    async def find(self, queue_id: UUID) -> ReviewItem | None:
        return self.item if queue_id == self.item.review_id else None

    async def resolve(self, queue_id: UUID, advisor_id: str, status: str, edited_content: str | None) -> None:
        del queue_id, advisor_id
        self.item = ReviewItem(
            review_id=self.item.review_id,
            session_id=self.item.session_id,
            run_id=self.item.run_id,
            status=status,
            content=self.item.content,
            edited_content=edited_content,
        )


class Memory:
    def __init__(self) -> None:
        self.messages: list[ConversationMessage] = []

    async def append_delivery(self, session_id: UUID, content: str, delivery_id: UUID) -> ConversationMessage:
        existing = next((message for message in self.messages if message.review_id == delivery_id), None)
        if existing is not None:
            return existing
        message = ConversationMessage(
            role="ASSISTANT",
            content=content,
            turn_index=1,
            message_id=uuid4(),
            conversation_id=session_id,
            review_id=delivery_id,
            created_at=datetime(2026, 8, 15, tzinfo=UTC),
        )
        self.messages.append(message)
        return message


class Outcomes:
    def __init__(self, client_turn_id: UUID) -> None:
        self.client_turn_id = client_turn_id
        self.calls: list[tuple[UUID, TurnOutcomeStatus, UUID | None, str | None]] = []


    async def assert_core_turn_lease(self, lease: object) -> None:
        """Hàng rào lease của `commit_core_turn`; fake mặc định coi là còn hợp lệ."""

        self.lease_checked = getattr(self, "lease_checked", 0) + 1
    async def set_review_terminal(
        self,
        review_id: UUID,
        *,
        status: TurnOutcomeStatus,
        message_id: UUID | None = None,
        delivered_content: str | None = None,
    ):
        self.calls.append((review_id, status, message_id, delivered_content))
        return type("Outcome", (), {"client_turn_id": self.client_turn_id})()


@dataclass
class Transaction:
    review_queue: Queue
    memory: Memory
    outcomes: Outcomes


class Uow:
    def __init__(self, transaction: Transaction) -> None:
        self.value = transaction
        self.committed = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        yield self.value
        self.committed = True


class Broker:
    def __init__(self, uow: Uow) -> None:
        self.uow = uow
        self.events: list[TurnEvent] = []

    async def publish(self, event: TurnEvent) -> None:
        assert self.uow.committed is True
        self.events.append(event)


@pytest.mark.asyncio
async def test_approve_commits_final_message_and_outcome_before_publish() -> None:
    review_id = uuid4()
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", "Final draft", None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    uow = Uow(transaction)
    broker = Broker(uow)
    operations = ReviewOperations(uow, broker=broker)

    await operations.approve(review_id, advisor_id="advisor-1")

    assert [message.content for message in transaction.memory.messages] == ["Final draft"]
    assert transaction.outcomes.calls[0][1] is TurnOutcomeStatus.COMPLETED
    assert broker.events[0].message_id == transaction.memory.messages[0].message_id

    await operations.deliverable_for_customer(review_id)
    assert len(transaction.memory.messages) == 1


@pytest.mark.asyncio
async def test_approved_delivery_carries_no_internal_evidence_identifiers() -> None:
    """[C1] Nội dung tư vấn viên duyệt rồi giao khách KHÔNG được chứa UUID/tên bảng nội bộ.

    `review_queue.content` đã là bản footnote (EnqueueHitlNode làm sạch ở thượng
    nguồn); `approve` giao nguyên văn nên bản giao phải sạch y hệt. Đây là khóa
    hồi quy cho lỗi nghiêm trọng nhất: lộ `evidence_id`/`cars:<uuid>` ra khách.
    """

    review_id = uuid4()
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", "Xe Một đi 399 km [1].", None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    uow = Uow(transaction)
    broker = Broker(uow)
    operations = ReviewOperations(uow, broker=broker)

    await operations.approve(review_id, advisor_id="advisor-1")

    delivered = transaction.memory.messages[0].content
    assert delivered == "Xe Một đi 399 km [1]."
    assert "evidence_id" not in delivered
    assert HEX_UUID.search(delivered) is None
    assert "cars:" not in delivered
    assert "vehicle_documents:" not in delivered


@pytest.mark.asyncio
async def test_approved_edited_delivery_carries_no_internal_evidence_identifiers() -> None:
    """[C1] Tư vấn viên sửa rồi giao cũng không được lộ UUID nội bộ."""

    review_id = uuid4()
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", "Xe Một đi 399 km [1].", None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    uow = Uow(transaction)
    broker = Broker(uow)
    operations = ReviewOperations(uow, broker=broker)

    await operations.approve(review_id, advisor_id="advisor-1", edited_content="Xe Một chạy 399 km [1].")

    delivered = transaction.memory.messages[0].content
    assert "evidence_id" not in delivered
    assert HEX_UUID.search(delivered) is None
    assert "cars:" not in delivered


@pytest.mark.asyncio
async def test_approve_keeps_internal_evidence_in_queue_but_not_customer_memory() -> None:
    review_id = uuid4()
    internal = "Giá đã kiểm chứng [evidence_id:30000000-0000-0000-0000-000000000101]."
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", internal, None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    operations = ReviewOperations(Uow(transaction))

    await operations.approve(review_id, advisor_id="advisor-1")

    assert transaction.review_queue.item.content == internal
    assert transaction.memory.messages[0].content == "Giá đã kiểm chứng."
    approved = await operations.deliverable_for_customer(review_id)
    assert approved.deliverable_content == "Giá đã kiểm chứng."


@pytest.mark.asyncio
async def test_reject_persists_terminal_state_and_publishes_recovery_event() -> None:
    review_id = uuid4()
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", "Draft", None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    uow = Uow(transaction)
    broker = Broker(uow)
    operations = ReviewOperations(uow, broker=broker)

    await operations.reject(review_id, advisor_id="advisor-1")

    assert transaction.outcomes.calls[0][1] is TurnOutcomeStatus.REJECTED
    assert transaction.memory.messages == []
    assert broker.events[0].kind == "rejected"


@pytest.mark.asyncio
async def test_expire_persists_terminal_state_without_customer_message() -> None:
    review_id = uuid4()
    item = ReviewItem(review_id, uuid4(), uuid4(), "PENDING", "Draft", None)
    transaction = Transaction(Queue(item), Memory(), Outcomes(uuid4()))
    uow = Uow(transaction)
    broker = Broker(uow)
    operations = ReviewOperations(uow, broker=broker)

    await operations.expire(review_id)

    assert transaction.review_queue.item.status == "EXPIRED"
    assert transaction.outcomes.calls[0][1] is TurnOutcomeStatus.EXPIRED
    assert transaction.memory.messages == []
    assert broker.events[0].kind == "expired"
