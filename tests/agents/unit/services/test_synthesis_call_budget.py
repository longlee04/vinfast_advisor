"""Synthesis tiêu MỘT slot cho cả lượt thử, dù cụm có bao nhiêu xe.

Quyết định A (Sếp chốt 2026-08-24). Fan-out theo từng xe là chủ ý — mỗi call chỉ
thấy dữ kiện của đúng xe đó — nên đếm theo lần chạm provider sẽ ép phải gộp lô,
tức đánh đổi cách ly dữ kiện và khả năng chịu lỗi từng phần lấy tiền. Thứ cần
chặn là số LƯỢT THỬ.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.agents.contracts import Recommendation
from src.agents.services.call_budget import (
    CallBudgetExhaustedError,
    CallKind,
    TurnCallBudget,
    use_call_budget,
)
from src.agents.services.synthesis import DefaultSynthesisService


class _CountingLlm:
    """Đếm số lần chạm provider thật — KHÔNG bọc ngân sách, đúng như production."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        # Không placeholder, không chữ số, không từ bị `reject_unstructured_claims`
        # cấm — bản nháp qua được `_validate_draft` nên không sinh retry nội bộ
        # làm nhiễu phép đếm.
        return "Mẫu này đáng để Quý khách cân nhắc."


class _EmptySource:
    """Không có facts/quotes: pitch rơi về bản tất định, đủ để đếm lần gọi."""

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple:
        return ()

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple:
        return ()


def _service(llm: _CountingLlm) -> DefaultSynthesisService:
    return DefaultSynthesisService(llm=llm, fallback_llm=None, source=_EmptySource())


def _recommendations(count: int) -> list[Recommendation]:
    return [
        Recommendation(
            vehicle_id=uuid4(),
            rank=index + 1,
            reasons=["[slot=budget_max_vnd] trong ngân sách"],
            display_name=f"Xe {index}",
        )
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_twenty_vehicles_still_cost_one_budget_slot() -> None:
    """`MAX_RECOMMENDATIONS` là 20 — trần phải độc lập với số xe."""

    llm = _CountingLlm()
    with use_call_budget(TurnCallBudget()) as budget:
        await _service(llm).synthesize(run_id=uuid4(), recommendations=_recommendations(20), tco=None)
        assert budget.remaining(CallKind.REQUIRED) == 3, "chi duoc tieu dung mot slot"


@pytest.mark.asyncio
async def test_per_vehicle_fan_out_survives_the_budget_change() -> None:
    """Cách ly dữ kiện theo xe là tính chất an toàn — không được gộp lô mất nó."""

    llm = _CountingLlm()
    with use_call_budget(TurnCallBudget()):
        await _service(llm).synthesize(run_id=uuid4(), recommendations=_recommendations(3), tco=None)
    assert llm.calls == 3, "moi xe van phai co mot prompt rieng"
    assert len(set(llm.prompts)) == 3, "ba prompt phai khac nhau, khong gop lo"


@pytest.mark.asyncio
async def test_one_extraction_plus_three_attempts_exactly_fills_the_pool() -> None:
    """A6-1 giữ nguyên hai lượt retry: 1 trích slot + 3 lượt thử = 4."""

    llm = _CountingLlm()
    service = _service(llm)
    with use_call_budget(TurnCallBudget()) as budget:
        budget.claim(CallKind.REQUIRED)  # trích slot
        for _ in range(3):  # lần đầu + hai lượt retry
            await service.synthesize(run_id=uuid4(), recommendations=_recommendations(2), tco=None)
        assert budget.remaining(CallKind.REQUIRED) == 0


@pytest.mark.asyncio
async def test_a_fourth_attempt_is_refused_with_a_typed_error() -> None:
    llm = _CountingLlm()
    service = _service(llm)
    with use_call_budget(TurnCallBudget()) as budget:
        budget.claim(CallKind.REQUIRED)
        for _ in range(3):
            await service.synthesize(run_id=uuid4(), recommendations=_recommendations(1), tco=None)
        calls_before = llm.calls
        with pytest.raises(CallBudgetExhaustedError):
            await service.synthesize(run_id=uuid4(), recommendations=_recommendations(1), tco=None)
    assert llm.calls == calls_before, "bi tu choi thi khong duoc cham provider"


@pytest.mark.asyncio
async def test_optional_work_never_shortens_the_synthesis_attempts() -> None:
    """Điều khoản chính của quyết định B, kiểm ở đường synthesis thật."""

    llm = _CountingLlm()
    service = _service(llm)
    with use_call_budget(TurnCallBudget()) as budget:
        budget.take(CallKind.OPTIONAL)  # ví dụ: phát hiện nút thắt
        budget.claim(CallKind.REQUIRED)  # trích slot
        for _ in range(3):
            await service.synthesize(run_id=uuid4(), recommendations=_recommendations(1), tco=None)
        assert budget.remaining(CallKind.REQUIRED) == 0


@pytest.mark.asyncio
async def test_without_a_budget_synthesis_is_unbounded() -> None:
    """Script và eval offline không được bị chặn."""

    llm = _CountingLlm()
    service = _service(llm)
    for _ in range(6):
        await service.synthesize(run_id=uuid4(), recommendations=_recommendations(1), tco=None)
    assert llm.calls == 6
