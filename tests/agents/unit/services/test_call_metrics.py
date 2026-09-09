"""Tách QUOTA khỏi METRIC — hai vai khác nhau, không được trộn.

- **Quota** là CHÍNH SÁCH: đếm theo THAO TÁC ở tầng điều phối. Một lần trích slot
  là một slot; một lượt thử synthesis là một slot cho cả cụm fan-out.
- **Metric** là QUAN SÁT: đếm số lần CHẠM provider thật, để đối chiếu chi phí.

Trộn hai vai vào một chỗ thì một thao tác tuỳ chọn nội bộ gọi provider hai lần sẽ
âm thầm tiêu hai slot, còn ta thì mất hẳn con số "thật sự gọi bao nhiêu lần".
"""

from __future__ import annotations

import pytest

from src.agents.adapters.budgeted_llm import MeteredWriter
from src.agents.services.call_budget import (
    CallKind,
    TurnCallBudget,
    current_call_budget,
    use_call_budget,
)


class _Writer:
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        return "van ban"


@pytest.mark.asyncio
async def test_a_provider_wrapper_records_a_metric_without_spending_quota() -> None:
    """Đây là điều khoản chính: wrapper QUAN SÁT, không TIÊU."""

    writer = _Writer()
    wrapped = MeteredWriter(writer)
    with use_call_budget(TurnCallBudget()) as budget:
        await wrapped.synthesize(prompt="x")
        assert budget.remaining(CallKind.OPTIONAL) == 1, "wrapper khong duoc tieu quota"
        assert budget.provider_calls == 1, "nhung phai ghi nhan mot lan cham provider"


@pytest.mark.asyncio
async def test_one_operation_costs_one_slot_however_many_provider_calls_it_makes() -> None:
    """Một thao tác fan-out ba lần chạm provider vẫn chỉ tiêu MỘT slot."""

    writer = _Writer()
    wrapped = MeteredWriter(writer)
    with use_call_budget(TurnCallBudget()) as budget:
        budget.claim(CallKind.OPTIONAL)  # tầng điều phối xin slot cho THAO TÁC
        for _ in range(3):
            await wrapped.synthesize(prompt="x")
        assert budget.remaining(CallKind.OPTIONAL) == 0
        assert budget.provider_calls == 3


@pytest.mark.asyncio
async def test_the_metric_counts_every_touch_across_kinds() -> None:
    required = MeteredWriter(_Writer())
    optional = MeteredWriter(_Writer())
    with use_call_budget(TurnCallBudget()) as budget:
        await required.synthesize(prompt="a")
        await optional.synthesize(prompt="b")
        assert budget.provider_calls == 2


@pytest.mark.asyncio
async def test_the_metric_starts_at_zero_for_each_turn() -> None:
    with use_call_budget(TurnCallBudget()) as first:
        assert first.provider_calls == 0
    with use_call_budget(TurnCallBudget()) as second:
        assert second.provider_calls == 0


@pytest.mark.asyncio
async def test_without_a_budget_a_wrapper_still_forwards_and_records_nothing() -> None:
    writer = _Writer()
    await MeteredWriter(writer).synthesize(prompt="x")
    assert writer.calls == 1
    assert current_call_budget() is None
