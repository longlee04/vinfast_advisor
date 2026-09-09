from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from src.agents.domain.conversation_memory import ConversationMessage, ConversationSummary
from src.agents.services.conversation_memory import ConversationMemoryService


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.messages: list[ConversationMessage] = []
        self.summary: ConversationSummary | None = None
        self.client_ids: dict[tuple[UUID, str], ConversationMessage] = {}

    async def find_by_client_turn(
        self, session_id: str, customer_id: str, client_turn_id: UUID
    ) -> tuple[ConversationMessage, ...]:
        del session_id, customer_id
        return tuple(message for (stored_id, _), message in self.client_ids.items() if stored_id == client_turn_id)

    async def append(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        client_turn_id: UUID | None,
    ) -> ConversationMessage:
        del session_id, customer_id
        message = ConversationMessage(role=role, content=content, turn_index=len(self.messages) + 1)
        self.messages.append(message)
        if client_turn_id is not None:
            self.client_ids[(client_turn_id, role)] = message
        return message

    async def load_recent(
        self, session_id: str, customer_id: str, limit: int
    ) -> tuple[ConversationSummary | None, tuple[ConversationMessage, ...]]:
        del session_id, customer_id
        through = self.summary.summarized_through_turn if self.summary else 0
        unsummarized = [message for message in self.messages if message.turn_index > through]
        return self.summary, tuple(unsummarized[-limit:])

    async def save_summary(self, session_id: str, customer_id: str, summary: ConversationSummary) -> None:
        del session_id, customer_id
        self.summary = summary


@dataclass
class Transaction:
    memory: FakeMemoryRepository


class Uow:
    def __init__(self, repository: FakeMemoryRepository) -> None:
        self.repository = repository

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        yield Transaction(memory=self.repository)


class FakeSummarizer:
    def __init__(self, result: str = "Khách đang cân nhắc VF 7.") -> None:
        self.result = result
        self.calls: list[tuple[str, str, str]] = []

    async def summarize(self, *, previous_summary: str, user_message: str, assistant_response: str) -> str:
        self.calls.append((previous_summary, user_message, assistant_response))
        return self.result


@pytest.mark.asyncio
async def test_start_turn_persists_user_and_projects_memory_without_duplicate_current() -> None:
    repository = FakeMemoryRepository()
    repository.summary = ConversationSummary("Đã loại VF 5, còn VF 7.", 2)
    repository.messages.extend(
        [
            ConversationMessage("USER", "VF 7 đi được bao xa?", 3),
            ConversationMessage("ASSISTANT", "Thông tin quãng đường VF 7.", 4),
        ]
    )
    service = ConversationMemoryService(Uow(repository), FakeSummarizer())

    started = await service.start_turn(
        session_id=str(uuid4()),
        customer_id="customer-1",
        client_turn_id=uuid4(),
        user_message="Mẫu còn lại giá bao nhiêu?",
        slots={"vehicle_type": "CAR"},
    )

    assert started.replayed_assistant is None
    assert repository.messages[-1].content == "Mẫu còn lại giá bao nhiêu?"
    assert started.context.count("Mẫu còn lại giá bao nhiêu?") == 1
    assert "Đã loại VF 5, còn VF 7." in started.context
    assert '"vehicle_type": "CAR"' in started.context


@pytest.mark.asyncio
async def test_retry_completed_client_turn_returns_delivered_response_without_append() -> None:
    repository = FakeMemoryRepository()
    client_turn_id = uuid4()
    repository.messages.extend(
        [
            ConversationMessage("USER", "VF 7 giá bao nhiêu?", 1),
            ConversationMessage("ASSISTANT", "VF 7 có giá niêm yết ...", 2),
        ]
    )
    repository.client_ids[(client_turn_id, "USER")] = repository.messages[0]
    repository.client_ids[(client_turn_id, "ASSISTANT")] = repository.messages[1]
    service = ConversationMemoryService(Uow(repository), FakeSummarizer())

    started = await service.start_turn(
        session_id=str(uuid4()),
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="VF 7 giá bao nhiêu?",
        slots={},
    )

    assert started.replayed_assistant == "VF 7 có giá niêm yết ..."
    assert len(repository.messages) == 2


@pytest.mark.asyncio
async def test_complete_turn_summarizes_completed_pair_and_persists_summary() -> None:
    repository = FakeMemoryRepository()
    summarizer = FakeSummarizer()
    service = ConversationMemoryService(Uow(repository), summarizer)
    session_id = str(uuid4())
    client_turn_id = uuid4()
    await service.start_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Tôi loại VF 5 vì chật.",
        slots={},
    )

    await service.complete_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=client_turn_id,
        user_message="Tôi loại VF 5 vì chật.",
        delivered_assistant="Vậy mình tiếp tục xem VF 7 nhé.",
    )

    assert summarizer.calls == [("", "Tôi loại VF 5 vì chật.", "Vậy mình tiếp tục xem VF 7 nhé.")]
    assert repository.summary == ConversationSummary(
        "Khách đang cân nhắc VF 7.\nTrạng thái xe — Đã loại: VF 5; Đang xem: VF 7.",
        2,
    )


@pytest.mark.asyncio
async def test_summarizer_failure_does_not_fail_completed_chat() -> None:
    class FailingSummarizer(FakeSummarizer):
        async def summarize(self, **kwargs: str) -> str:
            raise TimeoutError("summary timeout")

    repository = FakeMemoryRepository()
    service = ConversationMemoryService(Uow(repository), FailingSummarizer())
    session_id = str(uuid4())
    await service.start_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=None,
        user_message="ô tô 500 triệu",
        slots={},
    )

    await service.complete_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=None,
        user_message="ô tô 500 triệu",
        delivered_assistant="Bạn có thể xem VF 3.",
    )

    assert [message.role for message in repository.messages] == ["USER", "ASSISTANT"]
    assert repository.summary is None


@pytest.mark.asyncio
async def test_next_successful_summary_catches_up_unsummarized_messages() -> None:
    repository = FakeMemoryRepository()
    summarizer = FakeSummarizer()
    service = ConversationMemoryService(Uow(repository), summarizer)
    session_id = str(uuid4())
    await repository.append(session_id, "customer-1", "USER", "Đã loại VF 5.", None)
    await repository.append(session_id, "customer-1", "ASSISTANT", "Tiếp tục VF 7.", None)

    await service.start_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=None,
        user_message="VF 7 giá bao nhiêu?",
        slots={},
    )
    await service.complete_turn(
        session_id=session_id,
        customer_id="customer-1",
        client_turn_id=None,
        user_message="VF 7 giá bao nhiêu?",
        delivered_assistant="Thông tin giá VF 7.",
    )

    previous = summarizer.calls[0][0]
    assert "Đã loại VF 5." in previous
    assert "Tiếp tục VF 7." in previous
