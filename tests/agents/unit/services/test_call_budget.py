"""`TurnCallBudget`: slot AGENT riêng, không cướp REQUIRED/OPTIONAL (plan Bước 5)."""

from __future__ import annotations

import pytest

from src.agents.services.call_budget import (
    AGENT_CALLS_PER_TURN,
    OPTIONAL_CALLS_PER_TURN,
    REQUIRED_CALLS_PER_TURN,
    CallBudgetExhaustedError,
    CallKind,
    TurnCallBudget,
    current_call_budget,
    use_call_budget,
)


def test_agent_slot_khong_cuop_required() -> None:
    budget = TurnCallBudget()
    for _ in range(AGENT_CALLS_PER_TURN):
        assert budget.take(CallKind.AGENT) is True
    assert budget.take(CallKind.AGENT) is False  # cạn slot agent
    # REQUIRED / OPTIONAL còn nguyên.
    assert budget.remaining(CallKind.REQUIRED) == REQUIRED_CALLS_PER_TURN
    assert budget.remaining(CallKind.OPTIONAL) == OPTIONAL_CALLS_PER_TURN
    for _ in range(REQUIRED_CALLS_PER_TURN):
        budget.claim(CallKind.REQUIRED)
    with pytest.raises(CallBudgetExhaustedError):
        budget.claim(CallKind.REQUIRED)


def test_hai_han_muc_cu_giu_nguyen_4_va_1() -> None:
    assert REQUIRED_CALLS_PER_TURN == 4
    assert OPTIONAL_CALLS_PER_TURN == 1
    assert AGENT_CALLS_PER_TURN == 4


def test_required_can_khong_anh_huong_agent() -> None:
    budget = TurnCallBudget(required=0)
    with pytest.raises(CallBudgetExhaustedError):
        budget.claim(CallKind.REQUIRED)
    assert budget.take(CallKind.AGENT) is True


def test_use_call_budget_gan_va_tra_lai() -> None:
    assert current_call_budget() is None
    with use_call_budget(TurnCallBudget(agent=1)) as budget:
        assert current_call_budget() is budget
        assert budget.take(CallKind.AGENT) is True
        assert budget.take(CallKind.AGENT) is False
    assert current_call_budget() is None
