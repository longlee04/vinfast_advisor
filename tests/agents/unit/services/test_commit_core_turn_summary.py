"""Lượt lõi v2 cũng phải cập nhật tóm tắt hội thoại — như `finalize_turn` vẫn làm.

Món nợ I5 của bước 3: `commit_core_turn` ghi slot + outcome + core_state + vệt,
nhưng KHÔNG đụng `conversation_summaries`. Hỏng này chỉ lộ ở phiên DÀI:
`start_turn` dựng ngữ cảnh từ `summary` + N tin nhắn gần nhất, nên một phiên lõi
v2 quá N lượt là quên sạch phần đầu, im lặng.

Hai điều được khoá ở đây: tóm tắt CÓ chạy sau khi lượt đã chốt, và tóm tắt hỏng
KHÔNG được kéo theo lượt đã ghi xong.
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
from src.agents.services.conversation_memory import ConversationMemoryService


@dataclass
class Outcomes:
    committed: list[TurnOutcome] = field(default_factory=list)


    async def assert_core_turn_lease(self, lease: object) -> None:
        """Hàng rào lease của `commit_core_turn`; fake mặc định coi là còn hợp lệ."""

        self.lease_checked = getattr(self, "lease_checked", 0) + 1
    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        self.committed.append(outcome)
        return outcome


class Sessions:
    async def upsert_slot(self, session_id: str, slot_name: str, value: object) -> None:
        return None


@dataclass
class AppendedMessage:
    message_id: UUID
    turn_index: int


class Memory:
    def __init__(self) -> None:
        self.appended: list[str] = []
        self.saved_summaries: list[object] = []
        self.load_recent_calls = 0

    async def append(
        self, session_id: str, customer_id: str, role: str, content: str, client_turn_id: UUID | None
    ) -> AppendedMessage:
        del session_id, customer_id, role, client_turn_id
        self.appended.append(content)
        return AppendedMessage(message_id=uuid4(), turn_index=len(self.appended))

    async def load_recent(self, *args: object, **kwargs: object) -> tuple[None, tuple]:
        self.load_recent_calls += 1
        return None, ()

    async def save_summary(self, session_id: str, customer_id: str, summary: object) -> None:
        del session_id, customer_id
        self.saved_summaries.append(summary)


class CoreStateRepo:
    async def save(self, state: object) -> None:
        return None


class TurnTraces:
    async def record(self, trace: TurnTrace) -> None:
        return None


@dataclass
class Transaction:
    outcomes: Outcomes
    sessions: Sessions
    memory: Memory
    core_state: CoreStateRepo
    turn_traces: TurnTraces


class Uow:
    def __init__(self) -> None:
        self.memory = Memory()
        self.transaction_value = Transaction(Outcomes(), Sessions(), self.memory, CoreStateRepo(), TurnTraces())
        self.open_transactions = 0
        self.max_open = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        self.open_transactions += 1
        self.max_open = max(self.max_open, self.open_transactions)
        try:
            yield self.transaction_value
        finally:
            self.open_transactions -= 1


class Summarizer:
    model_name = "fake-summarizer"

    def __init__(self, text: str | Exception) -> None:
        self._text = text
        self.calls: list[dict[str, object]] = []

    async def summarize(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        if isinstance(self._text, Exception):
            raise self._text
        return self._text


def _trace(session_id: str, client_turn_id: UUID) -> TurnTrace:
    return TurnTrace(
        session_id=session_id,
        client_turn_id=str(client_turn_id),
        user_message="em muốn xe chạy xa",
        intent_hint="ADVISORY",
        confidence=0.9,
        tier="core_v2",
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


async def _commit(
    summarizer: Summarizer, *, answer: str = "Dạ em gợi ý mẫu chạy xa ạ.", terminal_reason: str | None = None
) -> tuple[Uow, TurnResult]:
    uow = Uow()
    service = ConversationMemoryService(uow, summarizer)
    session_id = str(uuid4())
    client_turn_id = uuid4()
    result = await service.commit_core_turn(
        lease=_lease(session_id, client_turn_id),
        customer_id="khach-1",
        user_message="em muốn xe chạy xa",
        result=TurnResult(session_id=session_id, answer=answer, pending_question=None, terminal_reason=terminal_reason),
        core_state=CoreState(session_id=session_id),
        trace=_trace(session_id, client_turn_id),
    )
    return uow, result


@pytest.mark.asyncio
async def test_luot_loi_v2_co_cap_nhat_tom_tat() -> None:
    summarizer = Summarizer("Khách cần xe chạy xa.")

    uow, result = await _commit(summarizer)

    assert len(summarizer.calls) == 1
    assert summarizer.calls[0]["user_message"] == "em muốn xe chạy xa"
    assert summarizer.calls[0]["assistant_response"] == "Dạ em gợi ý mẫu chạy xa ạ."
    assert len(uow.memory.saved_summaries) == 1
    assert result.answer == "Dạ em gợi ý mẫu chạy xa ạ."


@pytest.mark.asyncio
async def test_tom_tat_chay_ngoai_transaction_cua_luot() -> None:
    """Tóm tắt gọi LLM; giữ transaction mở suốt lần gọi mạng là cách cạn pool."""

    uow, _ = await _commit(Summarizer("Khách cần xe chạy xa."))

    assert uow.max_open == 1, "không được lồng transaction tóm tắt vào trong transaction lượt"
    assert uow.open_transactions == 0


@pytest.mark.asyncio
async def test_tom_tat_hong_khong_lam_hong_luot_da_ghi() -> None:
    summarizer = Summarizer(RuntimeError("summarizer 500"))

    uow, result = await _commit(summarizer)

    assert result.answer == "Dạ em gợi ý mẫu chạy xa ạ."
    assert uow.memory.saved_summaries == []


@pytest.mark.asyncio
async def test_loi_la_cua_summarizer_cung_khong_nem_ra_ngoai() -> None:
    """`_update_summary` chỉ bắt Timeout/Runtime/Value — lượt đã chốt không được chết vì phần dư."""

    uow, result = await _commit(Summarizer(KeyError("khoa la")))

    assert result.answer == "Dạ em gợi ý mẫu chạy xa ạ."
    assert uow.memory.saved_summaries == []


@pytest.mark.asyncio
async def test_luot_khong_co_chu_tra_khach_thi_khong_tom_tat() -> None:
    summarizer = Summarizer("không được gọi")

    uow, _ = await _commit(summarizer, answer="", terminal_reason="CONTENT_BLOCKED")

    assert summarizer.calls == []
    assert uow.memory.load_recent_calls == 0
