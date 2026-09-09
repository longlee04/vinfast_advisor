"""T1.7/T1.8: `begin_core_turn` wait policy — tổng 5s, tối đa 3 lần, backoff+jitter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.domain.conversation_memory import (
    CoreTurnLease,
    LeaseAcquired,
    LeaseBusy,
    TerminalReplay,
    TurnBusy,
)
from src.agents.errors import ConversationNotFoundError
from src.agents.services.conversation_memory import ConversationMemoryService


class Summarizer:
    model_name = "fake"

    async def summarize(self, **kwargs: object) -> str:  # pragma: no cover
        return ""


class OutcomeFake:
    """Trả LeaseBusy theo lịch định sẵn, rồi lease/replay."""

    def __init__(self, *, sequence: list[object], raise_error: type[Exception] | None = None) -> None:
        self.sequence = list(sequence)
        self.raise_error = raise_error
        self.calls = 0

    async def acquire_core_turn_lease(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        if not self.sequence:
            raise AssertionError("không còn kết quả lập lịch cho acquire")
        return self.sequence.pop(0)


class TransactionFake:
    def __init__(self, outcomes: OutcomeFake) -> None:
        self.outcomes = outcomes


class UowFake:
    def __init__(self, outcomes: OutcomeFake) -> None:
        self._outcomes = outcomes

    async def __aenter__(self) -> TransactionFake:
        return TransactionFake(self._outcomes)

    async def __aexit__(self, *exc: object) -> None:
        return None

    def transaction(self) -> UowFake:
        return self


@dataclass
class FakeClock:
    now_value: datetime = field(default_factory=lambda: datetime(2026, 9, 1, tzinfo=UTC))

    def now(self) -> datetime:
        return self.now_value


@dataclass
class FakeSleep:
    """Ghi lại tổng thời gian đã chờ; không sleep thật."""

    total: float = 0.0
    delays: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.total += seconds
        self.delays.append(seconds)


def _lease() -> CoreTurnLease:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


@pytest.mark.asyncio
async def test_acquired_returns_lease_acquired_without_wait() -> None:
    lease = _lease()
    uow = UowFake(OutcomeFake(sequence=[lease]))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    result = await service.begin_core_turn(
        session_id=str(lease.session_id), customer_id="customer-1", client_turn_id=lease.client_turn_id
    )

    assert isinstance(result, LeaseAcquired)
    assert result.lease is lease
    assert sleep.total == 0.0


@pytest.mark.asyncio
async def test_terminal_replay_returns_without_wait() -> None:
    replay = TerminalReplay(result=TurnResult(session_id=str(uuid4()), answer="câu trả lời cũ", pending_question=None))
    uow = UowFake(OutcomeFake(sequence=[replay]))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    result = await service.begin_core_turn(session_id=str(uuid4()), customer_id="customer-1", client_turn_id=uuid4())

    assert isinstance(result, TerminalReplay)
    assert sleep.total == 0.0


@pytest.mark.asyncio
async def test_busy_retries_at_most_three_attempts() -> None:
    lease = _lease()
    outcomes = OutcomeFake(sequence=[LeaseBusy(retry_after_seconds=2), LeaseBusy(retry_after_seconds=2), lease])
    uow = UowFake(outcomes)
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    result = await service.begin_core_turn(
        session_id=str(lease.session_id), customer_id="customer-1", client_turn_id=lease.client_turn_id
    )

    assert isinstance(result, LeaseAcquired)
    assert outcomes.calls == 3
    assert len(sleep.delays) == 2


@pytest.mark.asyncio
async def test_busy_after_three_attempts_returns_turn_busy() -> None:
    uow = UowFake(OutcomeFake(sequence=[LeaseBusy(retry_after_seconds=2)] * 3))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    result = await service.begin_core_turn(
        session_id=str(uuid4()), customer_id="customer-1", client_turn_id=uuid4(), wait_timeout_seconds=5.0
    )

    assert isinstance(result, TurnBusy)
    assert result.retry_after_seconds == 2
    assert "/turns/" in result.recovery_url


@pytest.mark.asyncio
async def test_backoff_increases_with_jitter() -> None:
    lease = _lease()
    uow = UowFake(OutcomeFake(sequence=[LeaseBusy(retry_after_seconds=2), LeaseBusy(retry_after_seconds=2), lease]))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    await service.begin_core_turn(
        session_id=str(lease.session_id), customer_id="customer-1", client_turn_id=lease.client_turn_id
    )

    assert len(sleep.delays) == 2
    assert sleep.delays[1] > sleep.delays[0]
    assert sleep.total < 5.0


@pytest.mark.asyncio
async def test_db_failure_returns_immediately() -> None:
    """DB/connectivity failure trả ngay, không tiêu hết 5s."""
    uow = UowFake(OutcomeFake(sequence=[], raise_error=ConnectionError("database down")))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    with pytest.raises(ConnectionError):
        await service.begin_core_turn(
            session_id=str(uuid4()), customer_id="customer-1", client_turn_id=uuid4(), wait_timeout_seconds=5.0
        )

    assert sleep.total == 0.0


@pytest.mark.asyncio
async def test_conversation_not_found_propagates_immediately() -> None:
    uow = UowFake(OutcomeFake(sequence=[], raise_error=ConversationNotFoundError("missing")))
    sleep = FakeSleep()
    service = ConversationMemoryService(uow, Summarizer(), sleep=sleep)

    with pytest.raises(ConversationNotFoundError):
        await service.begin_core_turn(session_id=str(uuid4()), customer_id="customer-1", client_turn_id=uuid4())

    assert sleep.total == 0.0
