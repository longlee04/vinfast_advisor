"""Chốt tất định chạy TRƯỚC mọi lần gọi mô hình, và không đụng tới graph.

Đây là điều khoản đắt nhất của QĐ-02: khách kêu cứu thì lượt phải sang tay người
mà không tốn một lần gọi provider nào, cũng không chạy qua bất kỳ node nào.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.agents.chain import run_turn
from src.agents.services.call_budget import CallKind, TurnCallBudget, current_call_budget
from src.agents.services.registry import AgentServices
from src.agents.services.turn_handoff import HANDOFF_MESSAGE, HandoffResult

SESSION = "11111111-1111-1111-1111-111111111111"
REVIEW = UUID("44444444-4444-4444-4444-444444444444")


class _Handoff:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def handoff(self, **kwargs) -> HandoffResult:
        self.calls.append(kwargs)
        return HandoffResult(review_id=REVIEW, answer=HANDOFF_MESSAGE)


class _Graph:
    """Graph KHÔNG được chạy ở những ca này."""

    def __init__(self) -> None:
        self.invocations = 0

    async def ainvoke(self, state: dict) -> dict:
        self.invocations += 1
        return {"answer": "khong duoc den day", "slots": {}, "lookup_facts": []}


def _services(handoff: _Handoff) -> AgentServices:
    return AgentServices(turn_handoff=handoff)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ["cho tôi gặp tư vấn viên", "xe của tôi đang bốc khói"],
)
async def test_an_escalating_turn_never_reaches_the_graph(message: str) -> None:
    graph, handoff = _Graph(), _Handoff()

    result = await run_turn(
        graph,
        _services(handoff),
        session_id=SESSION,
        customer_id="khach",
        user_message=message,
        client_turn_id=uuid4(),
    )

    assert graph.invocations == 0, "chot phai chan TRUOC graph"
    assert len(handoff.calls) == 1
    assert result.awaiting_review is True
    assert result.review_id == REVIEW
    assert result.terminal_reason is None, "chuyen nguoi khong phai ket thuc vi loi"


@pytest.mark.asyncio
async def test_an_escalating_turn_spends_no_provider_budget() -> None:
    """0 lần gọi — đo bằng chính bộ đếm của lượt, không phải bằng spy rời."""

    observed: dict[str, int] = {}

    class _Watching(_Handoff):
        async def handoff(self, **kwargs):
            budget = current_call_budget()
            assert budget is not None, "run_turn phai mo ngan sach cho luot"
            observed["required_left"] = budget.remaining(CallKind.REQUIRED)
            observed["provider_calls"] = budget.provider_calls
            return await super().handoff(**kwargs)

    await run_turn(
        _Graph(),
        _services(_Watching()),
        session_id=SESSION,
        customer_id="khach",
        user_message="cho tôi gặp tư vấn viên",
        client_turn_id=uuid4(),
    )

    assert observed["required_left"] == TurnCallBudget().remaining(CallKind.REQUIRED)
    assert observed["provider_calls"] == 0


@pytest.mark.asyncio
async def test_a_generic_safety_question_still_runs_the_normal_turn() -> None:
    """Hỏi kiến thức an toàn KHÔNG được đánh thức tư vấn viên."""

    graph, handoff = _Graph(), _Handoff()

    await run_turn(
        graph,
        _services(handoff),
        session_id=SESSION,
        customer_id="khach",
        user_message="xe điện có bốc cháy không ạ",
        client_turn_id=uuid4(),
    )

    assert handoff.calls == []
    assert graph.invocations == 1


@pytest.mark.asyncio
async def test_the_customer_never_sees_the_advisor_content() -> None:
    handoff = _Handoff()

    result = await run_turn(
        _Graph(),
        _services(handoff),
        session_id=SESSION,
        customer_id="khach",
        user_message="xe của tôi đang bốc khói",
        client_turn_id=uuid4(),
    )

    advisor_content = handoff.calls[0]["advisor_content"]
    assert "xe của tôi đang bốc khói" in advisor_content, "tu van vien can nguyen van"
    assert result.answer == HANDOFF_MESSAGE
    assert advisor_content not in (result.answer or "")


@pytest.mark.asyncio
async def test_without_the_service_the_turn_degrades_instead_of_crashing() -> None:
    """Chưa nối service thì lượt chạy như trước, không phải nổ."""

    graph = _Graph()

    await run_turn(
        graph,
        AgentServices(),
        session_id=SESSION,
        customer_id="khach",
        user_message="cho tôi gặp tư vấn viên",
        client_turn_id=uuid4(),
    )

    assert graph.invocations == 1
