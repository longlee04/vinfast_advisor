"""Ngân sách gọi provider của MỘT lượt — hai hạn mức tách rời.

Quyết định B (Sếp chốt 2026-08-24): việc BẮT BUỘC được giữ chỗ 4 slot
(1 trích slot + 1 synthesis + 2 lượt retry A6-1); việc TUỲ CHỌN có hạn mức
RIÊNG là 1, nằm ngoài 4 slot kia. Nhờ vậy không cần đoán "ca xấu nhất" và
việc tuỳ chọn không bao giờ cướp được slot retry.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agents.services.call_budget import (
    CallBudgetExhaustedError,
    CallKind,
    TurnCallBudget,
    current_call_budget,
    use_call_budget,
)


def test_required_pool_allows_extraction_plus_synthesis_and_two_retries() -> None:
    """Đúng bốn slot bắt buộc: A6-1 giữ nguyên hai lượt retry."""

    budget = TurnCallBudget()
    assert budget.take(CallKind.REQUIRED) is True  # trích slot
    assert budget.take(CallKind.REQUIRED) is True  # synthesis lần đầu
    assert budget.take(CallKind.REQUIRED) is True  # retry 1
    assert budget.take(CallKind.REQUIRED) is True  # retry 2
    assert budget.remaining(CallKind.REQUIRED) == 0


def test_a_fifth_required_call_is_refused_before_the_adapter_runs() -> None:
    budget = TurnCallBudget()
    for _ in range(4):
        budget.take(CallKind.REQUIRED)
    assert budget.take(CallKind.REQUIRED) is False


def test_optional_work_cannot_touch_the_required_pool() -> None:
    """Đây là điều khoản chính của quyết định B."""

    budget = TurnCallBudget()
    budget.take(CallKind.OPTIONAL)
    assert budget.remaining(CallKind.REQUIRED) == 4


def test_a_saturated_required_pool_still_leaves_the_optional_quota() -> None:
    budget = TurnCallBudget()
    for _ in range(4):
        budget.take(CallKind.REQUIRED)
    assert budget.take(CallKind.OPTIONAL) is True


def test_only_one_optional_call_per_turn() -> None:
    """Hạn mức tuỳ chọn là 1 — việc thứ hai phải rơi về bản tất định."""

    budget = TurnCallBudget()
    assert budget.take(CallKind.OPTIONAL) is True
    assert budget.take(CallKind.OPTIONAL) is False


def test_required_exhaustion_raises_a_typed_error_never_a_bare_exception() -> None:
    """Bắt buộc mà cạn thì phải là lỗi CÓ KIỂU để đường trên rẽ HITL, không 500."""

    budget = TurnCallBudget()
    for _ in range(4):
        budget.take(CallKind.REQUIRED)
    with pytest.raises(CallBudgetExhaustedError) as caught:
        budget.claim(CallKind.REQUIRED)
    assert caught.value.kind is CallKind.REQUIRED


def test_the_error_never_carries_prompt_or_draft_text() -> None:
    budget = TurnCallBudget()
    for _ in range(4):
        budget.take(CallKind.REQUIRED)
    try:
        budget.claim(CallKind.REQUIRED)
    except CallBudgetExhaustedError as error:
        assert "prompt" not in str(error).casefold()
        assert len(str(error)) < 200


def test_no_active_budget_means_no_limit() -> None:
    """Ngoài một lượt (script, test cũ) thì không có ngân sách nào áp đặt."""

    assert current_call_budget() is None


@pytest.mark.asyncio
async def test_two_concurrent_turns_keep_isolated_counters() -> None:
    """`ContextVar` phải tách theo task, không dùng chung một bộ đếm toàn cục."""

    observed: dict[str, int] = {}

    async def one_turn(name: str, takes: int) -> None:
        with use_call_budget(TurnCallBudget()) as budget:
            for _ in range(takes):
                budget.take(CallKind.REQUIRED)
                await asyncio.sleep(0)  # nhường lượt để hai task đan xen thật
            observed[name] = budget.remaining(CallKind.REQUIRED)

    await asyncio.gather(one_turn("a", 1), one_turn("b", 3))

    assert observed == {"a": 3, "b": 1}


@pytest.mark.asyncio
async def test_the_budget_is_cleared_when_the_turn_ends() -> None:
    with use_call_budget(TurnCallBudget()):
        assert current_call_budget() is not None
    assert current_call_budget() is None
