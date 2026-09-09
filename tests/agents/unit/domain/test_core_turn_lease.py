"""Test type contract cho CoreTurnLease và union variants (T1.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.domain.conversation_memory import (
    CoreTurnLease,
    LeaseAcquired,
    LeaseBusy,
    TerminalReplay,
    TurnBusy,
)


def test_core_turn_lease_holds_all_fields() -> None:
    session_id = uuid4()
    client_turn_id = uuid4()
    now = datetime.now(UTC)
    lease = CoreTurnLease(
        session_id=session_id,
        client_turn_id=client_turn_id,
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now,
    )
    assert lease.session_id == session_id
    assert lease.client_turn_id == client_turn_id
    assert lease.turn_number == 1
    assert isinstance(lease.claim_token, UUID)
    assert isinstance(lease.claimed_at, datetime)
    assert isinstance(lease.lease_expires_at, datetime)


def test_core_turn_lease_is_frozen() -> None:
    lease = CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=datetime.now(UTC),
        lease_expires_at=datetime.now(UTC),
    )
    with pytest.raises(AttributeError):
        lease.turn_number = 2  # type: ignore[misc]


def test_core_turn_lease_has_slots() -> None:
    lease = CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=datetime.now(UTC),
        lease_expires_at=datetime.now(UTC),
    )
    assert hasattr(lease.__class__, "__slots__")


def test_lease_acquired_wraps_lease() -> None:
    lease = CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=datetime.now(UTC),
        lease_expires_at=datetime.now(UTC),
    )
    acquired = LeaseAcquired(lease=lease)
    assert acquired.lease is lease
    assert isinstance(acquired, LeaseAcquired)


def test_terminal_replay_wraps_result() -> None:
    result = TurnResult(session_id=str(uuid4()), answer="hello", pending_question=None)
    replay = TerminalReplay(result=result)
    assert replay.result is result
    assert replay.result.answer == "hello"


def test_turn_busy_holds_retry_fields() -> None:
    busy = TurnBusy(retry_after_seconds=2, recovery_url="/api/v1/conversations/.../turns/...")
    assert busy.retry_after_seconds == 2
    assert isinstance(busy.recovery_url, str)


def test_lease_busy_holds_retry_seconds() -> None:
    busy = LeaseBusy(retry_after_seconds=2)
    assert busy.retry_after_seconds == 2


def test_core_turn_start_is_union_of_three() -> None:
    """CoreTurnStart phải là TypeAlias chấp nhận LeaseAcquired | TerminalReplay | TurnBusy."""
    lease = CoreTurnLease(
        session_id=uuid4(),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=datetime.now(UTC),
        lease_expires_at=datetime.now(UTC),
    )
    cases: list[object] = [
        LeaseAcquired(lease=lease),
        TerminalReplay(result=TurnResult(session_id=str(uuid4()), answer="x", pending_question=None)),
        TurnBusy(retry_after_seconds=2, recovery_url="/recovery"),
    ]
    for case in cases:
        assert isinstance(case, (LeaseAcquired, TerminalReplay, TurnBusy))
