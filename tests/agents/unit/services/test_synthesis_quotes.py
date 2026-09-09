"""A5-6 mo rong: LLM chi duoc chen placeholder, khong viet lai loi brochure."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.agents.contracts import Recommendation
from src.agents.services.synthesis import (
    DefaultSynthesisService,
    SynthesisFact,
    SynthesisQuote,
)

VEHICLE_ID = uuid4()
EVIDENCE_ID = uuid4()
QUOTE = "Cửa sổ trời toàn cảnh chống tia UV"


class _Source:
    async def load_vehicle_name(self, *, run_id, vehicle_id):
        return "VinFast VF 5"

    async def load_facts(self, *, run_id, vehicle_ids):
        return ()

    async def load_quotes(self, *, run_id, vehicle_ids):
        return (
            SynthesisQuote(
                text=QUOTE,
                evidence_id=EVIDENCE_ID,
                vehicle_id=VEHICLE_ID,
                source_record="vehicle_documents:doc-1",
            ),
        )


class _FactSource(_Source):
    """Nguồn có đủ 3 facts fallback hay dùng: giá / chỗ / tầm hoạt động."""

    async def load_facts(self, *, run_id, vehicle_ids):
        return (
            SynthesisFact(
                vehicle_id=VEHICLE_ID,
                fact_code="STARTING_PRICE_VND",
                value_text="496000000",
                unit="VND",
                evidence_id=uuid4(),
                source_record="run_snapshots:price",
            ),
            SynthesisFact(
                vehicle_id=VEHICLE_ID,
                fact_code="CAR_SEAT_COUNT",
                value_text="5",
                unit="chỗ ngồi",
                evidence_id=uuid4(),
                source_record="run_snapshots:seats",
            ),
            SynthesisFact(
                vehicle_id=VEHICLE_ID,
                fact_code="CAR_RANGE_KM",
                value_text="326",
                unit="km",
                evidence_id=uuid4(),
                source_record="run_snapshots:range",
            ),
        )


class _Llm:
    def __init__(self, draft: str) -> None:
        self._draft = draft
        self.prompt: str | None = None

    async def synthesize(self, *, prompt: str) -> str:
        self.prompt = prompt
        return self._draft


def _recommendation() -> Recommendation:
    return Recommendation(
        vehicle_id=VEHICLE_ID,
        rank=1,
        reasons=[
            "[slot=vehicle_type] dung loai xe",
            "[slot=budget_max_vnd] trong ngan sach",
        ],
    )


@pytest.mark.asyncio
async def test_quote_placeholder_is_replaced_by_the_exact_excerpt() -> None:
    llm = _Llm("Mẫu này {CLAIM_VEHICLE_TYPE}. Tài liệu mô tả: {QUOTE_1}")
    service = DefaultSynthesisService(llm=llm, source=_Source())

    pitches = await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)
    answer = "\n\n".join(pitch.pitch for pitch in pitches)

    assert f'"{QUOTE}" [1]' in answer
    assert "{QUOTE_1}" not in answer
    assert "evidence_id" not in answer


@pytest.mark.asyncio
async def test_prompt_offers_quote_placeholder_and_evidence_text() -> None:
    llm = _Llm("Mẫu này {CLAIM_VEHICLE_TYPE}. Tài liệu mô tả: {QUOTE_1}")
    service = DefaultSynthesisService(llm=llm, source=_Source())

    await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)

    assert llm.prompt is not None
    assert "QUOTE_1" in llm.prompt
    assert QUOTE in llm.prompt


@pytest.mark.asyncio
async def test_available_quote_must_be_used_in_the_draft() -> None:
    """Bỏ quên trích dẫn bắt buộc thì bản của LLM bị loại — bản dựng tay thay chỗ.

    Bản dựng tay LUÔN kèm trích dẫn đầu tiên, nên ràng buộc "trích dẫn phải được
    dùng" vẫn đúng ở bản gửi khách; chỉ có điều nó không còn phải trả giá bằng
    việc đánh rơi cả chiếc xe.
    """

    service = DefaultSynthesisService(llm=_Llm("Mẫu này {CLAIM_VEHICLE_TYPE}."), source=_Source())

    pitches = await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)

    assert len(pitches) == 1
    assert f'"{QUOTE}" [1]' in pitches[0].pitch


@pytest.mark.asyncio
async def test_deterministic_fallback_keeps_required_evidence_quote() -> None:
    service = DefaultSynthesisService(
        llm=_Llm("Mẫu này phù hợp với nhu cầu của bạn."),
        fallback_llm=_Llm("Mẫu này rất lý tưởng cho gia đình."),
        source=_Source(),
    )

    pitches = await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)
    answer = pitches[0].pitch

    assert f'"{QUOTE}" [1]' in answer
    assert pitches[0].citations[0].evidence_id == EVIDENCE_ID
    assert "ngân sách" in answer
    assert "{" not in answer and "}" not in answer


@pytest.mark.asyncio
async def test_deterministic_fallback_reads_like_a_pitch_not_a_data_sheet() -> None:
    """Fallback khi LLM hỏng vẫn phải ra ĐÚNG bố cục Markdown chung
    (`domain/reply_format`), không phải bảng ghi "được ghi nhận là": câu mở đầu
    rồi mỗi thông số một dòng `* **Nhãn**: giá trị`."""

    service = DefaultSynthesisService(
        llm=_Llm("Mẫu này phù hợp với nhu cầu của bạn."),
        fallback_llm=_Llm("Mẫu này rất lý tưởng cho gia đình."),
        source=_FactSource(),
    )

    pitches = await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)
    answer = pitches[0].pitch

    assert "được ghi nhận" not in answer
    assert "ngân sách" in answer
    assert "* " not in answer
    assert "**:" not in answer
    assert '"Cửa sổ trời toàn cảnh chống tia UV" [1]' in answer


@pytest.mark.asyncio
async def test_unknown_quote_placeholder_is_rejected() -> None:
    llm = _Llm("Tài liệu mô tả: {QUOTE_9}")
    service = DefaultSynthesisService(llm=llm, source=_Source())

    pitches = await service.synthesize(run_id=uuid4(), recommendations=[_recommendation()], tco=None)

    assert len(pitches) == 1
    assert "QUOTE_9" not in pitches[0].pitch
