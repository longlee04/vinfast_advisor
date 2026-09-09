"""T2.5: Turn number phải đi theo LEASE, không được hard-code ở bất kỳ đường nào.

Lõi v2 chốt lượt qua `commit_core_turn(*, lease, ...)`: `turn_number` đến từ
`lease.turn_number` (repo cấp theo `max(turn_number)+1`). Đây là nguồn duy nhất
được phép. Nếu tương lai ai đó hard-code `turn_number=1` (hoặc hằng số) trong
`conversation_memory.py`/`turn_handoff.py`, mọi lượt sau lượt 1 sẽ ghi đè chính
nó — phiên dài vỡ nát.

Hai lớp test:
1. Behavior: commit qua lease dùng đúng `lease.turn_number` (turn 2, 3, ...).
2. Source guard: quét source, fail nếu còn hard-code `turn_number = 1` ở ba đường
   ghi outcome (legacy finalize, core commit, handoff).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.core.state import CoreState
from src.agents.domain.conversation_memory import CoreTurnLease, TurnOutcome
from src.agents.domain.turn_trace import TurnTrace
from src.agents.services.conversation_memory import ConversationMemoryService

REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class AppendedMessage:
    message_id: UUID
    turn_index: int


class Memory:
    def __init__(self) -> None:
        self.appended: list[str] = []
        self.finalized: list[TurnOutcome] = []

    async def append(
        self, session_id: str, customer_id: str, role: str, content: str, client_turn_id: UUID | None
    ) -> AppendedMessage:
        del session_id, customer_id, role, client_turn_id
        self.appended.append(content)
        return AppendedMessage(message_id=uuid4(), turn_index=len(self.appended))

    async def load_recent(self, *args: object, **kwargs: object) -> tuple[None, tuple]:
        return None, ()


class Sessions:
    def __init__(self) -> None:
        self.upserted: list[tuple[str, str, object]] = []

    async def upsert_slot(self, session_id: str, slot_name: str, value: object) -> None:
        self.upserted.append((session_id, slot_name, value))


class ReviewQueue:
    def __init__(self) -> None:
        self.committed: list[tuple[UUID, UUID, str]] = []

    async def enqueue(self, run_id: UUID, session_id: UUID, content: str, *, snapshot: object | None = None) -> UUID:
        del snapshot
        self.committed.append((run_id, session_id, content))
        return uuid4()


class CoreStateRepo:
    def __init__(self) -> None:
        self.committed: list[object] = []

    async def save(self, state: object) -> None:
        self.committed.append(state)


class TurnTraces:
    def __init__(self) -> None:
        self.committed: list[TurnTrace] = []

    async def record(self, trace: TurnTrace) -> None:
        self.committed.append(trace)


class Outcomes:
    def __init__(self) -> None:
        self.committed: list[TurnOutcome] = []
        self.staged: list[TurnOutcome] = []


    async def assert_core_turn_lease(self, lease: object) -> None:
        """Hàng rào lease của `commit_core_turn`; fake mặc định coi là còn hợp lệ."""

        self.lease_checked = getattr(self, "lease_checked", 0) + 1
    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        self.staged.append(outcome)
        return outcome


@dataclass
class Transaction:
    memory: Memory
    sessions: Sessions
    review_queue: ReviewQueue
    core_state: CoreStateRepo
    turn_traces: TurnTraces
    outcomes: Outcomes


class Uow:
    """Transaction nguyên tử: thoát sạch mới chốt staged sang committed."""

    def __init__(self) -> None:
        self.memory = Memory()
        self.sessions = Sessions()
        self.review_queue = ReviewQueue()
        self.core_state = CoreStateRepo()
        self.turn_traces = TurnTraces()
        self.outcomes = Outcomes()
        self.transaction_value = Transaction(
            self.memory,
            self.sessions,
            self.review_queue,
            self.core_state,
            self.turn_traces,
            self.outcomes,
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        try:
            yield self.transaction_value
        except Exception:
            self.outcomes.staged.clear()
            raise
        self.outcomes.committed.extend(self.outcomes.staged)
        self.outcomes.staged.clear()


class Summarizer:
    model_name = "fake"

    async def summarize(self, **kwargs: object) -> str:  # pragma: no cover
        return ""


def _lease(session_id: UUID, client_turn_id: UUID, turn_number: int) -> CoreTurnLease:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=session_id,
        client_turn_id=client_turn_id,
        turn_number=turn_number,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


def _result(session_id: str) -> TurnResult:
    return TurnResult(session_id=session_id, answer="Dạ VF 8 giá niêm yết như sau ạ.", pending_question=None)


def _trace(session_id: UUID, client_turn_id: UUID) -> TurnTrace:
    return TurnTrace(
        session_id=str(session_id),
        client_turn_id=str(client_turn_id),
        user_message="tin nhắn mẫu",
        intent_hint="INQUIRY",
        confidence=0.9,
        tier="deterministic",
        scope_label="IN_SCOPE",
        terminal_reason=None,
        routing_enabled=True,
    )


@pytest.mark.asyncio
async def test_commit_uses_lease_turn_number_not_hardcoded_one() -> None:
    """Lease turn 2 → outcome phải ghi turn_number=2, không được 1."""
    session_id = uuid4()
    client_turn_id = uuid4()
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())

    await service.commit_core_turn(
        lease=_lease(session_id, client_turn_id, turn_number=2),
        customer_id="khach-1",
        user_message="VF 8 bản cao nhất giá bao nhiêu?",
        result=_result(str(session_id)),
        core_state=CoreState(session_id=str(session_id)),
        trace=_trace(session_id, client_turn_id),
    )

    assert len(uow.outcomes.committed) == 1
    assert uow.outcomes.committed[0].turn_number == 2


@pytest.mark.asyncio
async def test_commit_uses_lease_turn_number_three() -> None:
    """Lease turn 3 → outcome phải ghi turn_number=3."""
    session_id = uuid4()
    client_turn_id = uuid4()
    uow = Uow()
    service = ConversationMemoryService(uow, Summarizer())

    await service.commit_core_turn(
        lease=_lease(session_id, client_turn_id, turn_number=3),
        customer_id="khach-1",
        user_message="Còn màu trắng không ạ?",
        result=_result(str(session_id)),
        core_state=CoreState(session_id=str(session_id)),
        trace=_trace(session_id, client_turn_id),
    )

    assert uow.outcomes.committed[0].turn_number == 3


def test_no_hardcoded_turn_number_in_source() -> None:
    """Source guard: cấm hằng số `turn_number = 1` ở ba đường ghi outcome.

    Nếu test này fail, ai đó đã chèn hard-code. Chữa đúng cách: đọc turn_number
    từ outcome đã claim (legacy) hoặc từ lease (core v2), KHÔNG gán 1.
    """
    src = REPO_ROOT / "src" / "agents"
    pattern = re.compile(r"turn_number\s*=\s*1\b")
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        if "site-packages" in str(path) or ".venv" in str(path):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "turn_number bị hard-code:\n" + "\n".join(offenders)
