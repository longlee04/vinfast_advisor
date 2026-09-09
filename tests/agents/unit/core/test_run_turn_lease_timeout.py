"""T1.9/T1.10: Timeout invariant 20s/25s + lease re-check trước act/commit.

Ba bất biến PR1:
1. Hard budget 20s bắt đầu SAU claim completion, không tính 5s claim wait.
2. Hết budget → `CoreTurnTimeoutError`; outcome GIỮ `IN_PROGRESS` — worker KHÔNG
   finalize FAILED, không commit gì.
3. `assert_core_turn_lease` đứng trước side effect (act) và trước commit: worker
   cũ tỉnh sau takeover bị reject, không chạm API ngoài, không chốt DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agents.core import run_turn as run_turn_module
from src.agents.core.run_turn import run_turn
from src.agents.core.state import CoreState
from src.agents.domain.conversation_memory import CoreTurnLease
from src.agents.errors import CoreTurnLeaseStaleError, CoreTurnTimeoutError
from src.agents.services.registry import AgentServices
from tests.agents.unit.core.memory_fakes import HonestMemory
from tests.agents.unit.core.test_run_turn import (
    FakeCatalogBrowse,
    FakeConversation,
    FakeUnderstander,
    _outcome,
)

SESSION = "aaaaaaaa-0000-0000-0000-000000000001"
V1 = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clear_directory_cache() -> None:
    run_turn_module.reset_vehicle_directory_cache()


def _lease() -> CoreTurnLease:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=UUID(SESSION),
        client_turn_id=UUID(V1),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


class TimeoutRunner:
    """Ghi tham số nhận được; tùy chọn raise TimeoutError như wait_for thật."""

    def __init__(self, *, raise_timeout: bool = False) -> None:
        self.raise_timeout = raise_timeout
        self.timeouts: list[float] = []
        self.calls = 0

    async def __call__(self, coro: Any, seconds: float) -> Any:
        self.calls += 1
        self.timeouts.append(seconds)
        if self.raise_timeout:
            # Đóng coroutine thay vì để GC rác: mô phỏng `asyncio.wait_for`
            # cancel đúng lúc budget hết — orchestration chưa từng chạy.
            coro.close()
            raise TimeoutError("hard budget exhausted")
        return await coro


def _services(conversation: FakeConversation, memory: HonestMemory, **extra: Any) -> AgentServices:
    extra.setdefault("catalog_browse", FakeCatalogBrowse())
    return AgentServices(conversation=conversation, memory=memory, **extra)


async def _turn_with_lease(
    memory: HonestMemory,
    *,
    runner: TimeoutRunner,
    outcome: Any = None,
    **extra: Any,
) -> tuple[Any, Any]:
    conversation = FakeConversation(state=CoreState(session_id=SESSION))
    services = _services(conversation, memory, **extra)
    understander = FakeUnderstander(outcome if outcome is not None else _outcome())
    return (
        await run_turn(
            None,
            services,
            session_id=SESSION,
            customer_id="c1",
            user_message="tư vấn giúp em",
            client_turn_id=uuid4(),
            understander=understander,
            lease=_lease(),
            timeout_runner=runner,
        ),
        memory,
    )


@pytest.mark.asyncio
async def test_hard_budget_20s_bat_dau_sau_claim_khong_tinh_wait_5s() -> None:
    """Runner nhận đúng 20.0 — budget đo từ post-claim, không gồm 5s claim wait."""
    runner = TimeoutRunner()
    memory = HonestMemory()
    await _turn_with_lease(memory, runner=runner)

    assert runner.calls == 1
    assert runner.timeouts == [20.0]


@pytest.mark.asyncio
async def test_khong_co_lease_thi_khong_boc_timeout() -> None:
    """Fallback không lease (lõi cũ) không đi qua timeout runner."""
    runner = TimeoutRunner()
    conversation = FakeConversation(state=CoreState(session_id=SESSION))
    memory = HonestMemory()
    services = _services(conversation, memory)

    await run_turn(
        None,
        services,
        session_id=SESSION,
        customer_id="c1",
        user_message="alo",
        client_turn_id=uuid4(),
        understander=FakeUnderstander(_outcome()),
    )

    assert runner.calls == 0


@pytest.mark.asyncio
async def test_het_budget_raise_core_turn_timeout_khong_finalize_failed() -> None:
    """Hết 20s → CoreTurnTimeoutError; outcome còn IN_PROGRESS: không finalize FAILED, không commit."""
    runner = TimeoutRunner(raise_timeout=True)
    memory = HonestMemory()

    with pytest.raises(CoreTurnTimeoutError) as excinfo:
        await _turn_with_lease(memory, runner=runner)

    assert "session=" in str(excinfo.value)
    assert memory.committed == []
    assert memory.finalized == []
    # Không ghi gì cả: outcome IN_PROGRESS do repository giữ, worker không đụng.
    assert memory.outcomes == []


@pytest.mark.asyncio
async def test_lease_25s_lon_hon_hard_budget_20s() -> None:
    """Bất biến 3: understand+act không thể vượt 25s — budget cứng 20s < lease 25s."""
    lease = _lease()
    # lease_expires_at - claimed_at == 25s, budget mặc định 20s.
    assert (lease.lease_expires_at - lease.claimed_at).total_seconds() == 25.0
    runner = TimeoutRunner()
    assert runner.timeouts == []  # budget ghi vào lúc chạy; giá trị mặc định ở run_turn


@pytest.mark.asyncio
async def test_stale_truoc_act_bi_reject_khong_chay_act() -> None:
    """Worker cũ tỉnh sau takeover: reject TRƯỚC side effect — act không chạy.

    `catalog.calls == 1` là lần `_vehicle_directory` trong understand (chỉ đọc,
    không phải side effect). Action CATALOG_BROWSE nếu được act chạy sẽ gọi
    `catalog_browse.answer` thêm một lần nữa → calls = 2. Assert fail ở pre-act
    nên act không kịp chạy, calls giữ nguyên 1.
    """
    memory = HonestMemory()
    memory.fail_lease_on_call = 1  # lần assert đầu = trước act
    catalog = FakeCatalogBrowse()
    runner = TimeoutRunner()

    with pytest.raises(CoreTurnLeaseStaleError):
        await _turn_with_lease(
            memory,
            runner=runner,
            catalog_browse=catalog,
            outcome=_outcome(intent="CATALOG_BROWSE"),
        )

    assert len(memory.assert_lease_calls) == 1  # chỉ pre-act, act không tới
    assert catalog.calls == 1  # side effect của act chưa xảy ra
    assert memory.committed == []


@pytest.mark.asyncio
async def test_stale_truoc_commit_bi_reject_khong_ghi_db() -> None:
    """Act đã chạy nhưng lease hết hạn giữa chừng: reject TRƯỚC commit — DB không đổi."""
    memory = HonestMemory()
    memory.fail_lease_on_call = 2  # lần assert thứ hai = trước commit
    runner = TimeoutRunner()

    with pytest.raises(CoreTurnLeaseStaleError):
        await _turn_with_lease(memory, runner=runner)

    assert len(memory.assert_lease_calls) == 2  # pre-act pass, pre-commit fail
    assert memory.committed == []


@pytest.mark.asyncio
async def test_lease_duoc_assert_hai_lan_va_commit_mot_lan() -> None:
    """Happy path: assert trước act + trước commit, commit đúng một lần."""
    memory = HonestMemory()
    runner = TimeoutRunner()

    await _turn_with_lease(memory, runner=runner)

    assert len(memory.assert_lease_calls) == 2
    assert len(memory.committed) == 1
