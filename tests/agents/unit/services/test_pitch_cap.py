"""Tách LIỆT KÊ khỏi THUYẾT PHỤC: liệt kê không tốn một lần gọi LLM nào.

Bối cảnh: `MAX_RECOMMENDATIONS` được nới 3 → 20 ở `baa31ab` để vá một bug thật —
khách hỏi "xe từ 200–900 triệu" có sáu mẫu thoả mà chỉ ba mẫu được trả, nên hai
câu hỏi khác nhau ra cùng một đáp án. Bản vá đúng ở tầng danh sách, nhưng
`synthesize` gọi LLM MỘT LẦN CHO MỖI XE trong danh sách đó, nên nó vô tình nới
luôn chi phí: hai mươi xe × ba lượt thử = sáu mươi lần gọi cho một lượt chat.

Chốt (Sếp 2026-08-24): giữ đủ danh sách, chỉ giới hạn số đoạn văn thuyết phục.
Giá và tên xe đọc từ snapshot nên thẻ xe không có pitch vẫn dựng được đầy đủ.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.agents.adapters.budgeted_llm import MeteredWriter
from src.agents.contracts import Recommendation
from src.agents.domain.scoring import MAX_PITCHED_RECOMMENDATIONS
from src.agents.services.call_budget import TurnCallBudget, use_call_budget
from src.agents.services.synthesis import DefaultSynthesisService, SynthesisFact


class _CountingLlm:
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        return "Mẫu này đáng để Quý khách cân nhắc."


class _PricedSource:
    """Snapshot có giá cho MỌI xe — giá là dữ liệu catalog, không do LLM sinh."""

    def __init__(self, vehicle_ids: tuple[UUID, ...]) -> None:
        self._vehicle_ids = vehicle_ids

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple:
        return tuple(
            SynthesisFact(
                vehicle_id=vehicle_id,
                fact_code="STARTING_PRICE_VND",
                value_text="499000000",
                unit="VND",
                evidence_id=uuid4(),
                source_record="catalog",
            )
            for vehicle_id in vehicle_ids
        )

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple:
        return ()


def _recommendations(count: int) -> list[Recommendation]:
    return [
        Recommendation(
            vehicle_id=uuid4(),
            rank=index + 1,
            reasons=["[slot=budget_max_vnd] trong ngân sách"],
            display_name=f"VF {index}",
        )
        for index in range(count)
    ]


def _service(llm: _CountingLlm, recommendations: list[Recommendation]) -> DefaultSynthesisService:
    ids = tuple(item.vehicle_id for item in recommendations)
    # Bọc lớp ĐO như production: metric phải đếm được lần chạm thật.
    return DefaultSynthesisService(llm=MeteredWriter(llm), fallback_llm=None, source=_PricedSource(ids))


@pytest.mark.asyncio
async def test_twenty_matches_still_cost_only_three_llm_calls() -> None:
    """Đây là toàn bộ mục đích của thay đổi: chi phí không theo số xe thoả."""

    recommendations = _recommendations(20)
    llm = _CountingLlm()
    await _service(llm, recommendations).synthesize(run_id=uuid4(), recommendations=recommendations, tco=None)
    assert llm.calls == MAX_PITCHED_RECOMMENDATIONS


@pytest.mark.asyncio
async def test_every_matching_vehicle_still_comes_back_as_a_card() -> None:
    """Bug của `baa31ab` KHÔNG được quay lại: không xe nào biến mất."""

    recommendations = _recommendations(20)
    pitches = await _service(_CountingLlm(), recommendations).synthesize(
        run_id=uuid4(), recommendations=recommendations, tco=None
    )
    assert len(pitches) == 20
    assert [item.rank for item in pitches] == list(range(1, 21))


@pytest.mark.asyncio
async def test_unpitched_cards_still_carry_name_and_price_from_the_snapshot() -> None:
    """Giá đọc từ snapshot nên thẻ xe thứ tư trở đi vẫn đầy đủ để dựng card."""

    recommendations = _recommendations(6)
    pitches = await _service(_CountingLlm(), recommendations).synthesize(
        run_id=uuid4(), recommendations=recommendations, tco=None
    )
    tail = pitches[MAX_PITCHED_RECOMMENDATIONS:]
    assert tail, "phai con xe o phan duoi danh sach"
    for item in tail:
        assert item.pitch == "", "xe ngoai top khong co doan thuyet phuc"
        assert item.display_name, "van phai co ten"
        assert item.starting_price_vnd == "499000000", "van phai co gia"


@pytest.mark.asyncio
async def test_the_top_ranked_vehicles_are_the_ones_that_get_prose() -> None:
    recommendations = _recommendations(6)
    pitches = await _service(_CountingLlm(), recommendations).synthesize(
        run_id=uuid4(), recommendations=recommendations, tco=None
    )
    pitched = [item for item in pitches if item.pitch]
    assert [item.rank for item in pitched] == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_short_list_is_unchanged() -> None:
    """Ba xe trở xuống thì mọi xe vẫn có đoạn thuyết phục, y như trước."""

    recommendations = _recommendations(3)
    llm = _CountingLlm()
    pitches = await _service(llm, recommendations).synthesize(run_id=uuid4(), recommendations=recommendations, tco=None)
    assert llm.calls == 3
    assert all(item.pitch for item in pitches)


@pytest.mark.asyncio
async def test_unpitched_cards_never_carry_citations() -> None:
    """Không gọi LLM thì không có dẫn chứng nào để trích — không được bịa."""

    recommendations = _recommendations(6)
    pitches = await _service(_CountingLlm(), recommendations).synthesize(
        run_id=uuid4(), recommendations=recommendations, tco=None
    )
    for item in pitches[MAX_PITCHED_RECOMMENDATIONS:]:
        assert item.citations == ()


@pytest.mark.asyncio
async def test_the_provider_metric_equals_pitched_count_not_match_count() -> None:
    """Điều kiện nghiệm thu của plan: metric mỗi lượt thử = `pitched_count` ≤ 3.

    Quota nói "được làm thêm một lượt thử nữa không"; metric nói "lượt thử đó
    tốn bao nhiêu lần gọi". Thiếu metric thì con số thứ hai vô hình, và chi phí
    thật có thể trôi đi mà quota vẫn báo xanh.
    """

    recommendations = _recommendations(20)
    with use_call_budget(TurnCallBudget()) as budget:
        await _service(_CountingLlm(), recommendations).synthesize(
            run_id=uuid4(), recommendations=recommendations, tco=None
        )
        assert budget.provider_calls == MAX_PITCHED_RECOMMENDATIONS
        assert budget.provider_calls <= MAX_PITCHED_RECOMMENDATIONS
