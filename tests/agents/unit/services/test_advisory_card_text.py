"""Nội dung MÔ TẢ trong thẻ xe của luồng tư vấn, và nhãn lệch ngân sách.

Bản cũ đọc như một biên bản đối chiếu dữ liệu:

    VinFast VF 2 All New đúng loại phương tiện bạn đang tìm, có giá nằm trong ngân
    sách bạn đã xác nhận. Giá khởi điểm được ghi nhận là 188000000 VND. Số chỗ được
    ghi nhận là 4 chỗ ngồi. Tầm hoạt động được ghi nhận là 210.00 km.

Ba lỗi trong một đoạn: cụm "được ghi nhận là" lặp ba lần, giá bị nhắc lại dù thẻ xe
đã có dòng giá riêng, và con số giá in ra thô ("188000000 VND") vì `_render_all` chèn
nguyên `value_text` của snapshot.

Đo ở tầng service vì đây là chỗ DUY NHẤT dựng `VehiclePitch.pitch` — đúng field mà
`chain._recommended_vehicles` đưa vào `RecommendedVehicleView.pitch` để render thẻ.
Cấu trúc thẻ (ảnh, tên xe, dòng giá) không bị test này chạm tới và không đổi.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from src.agents.contracts import Recommendation
from src.agents.services.synthesis import (
    DefaultSynthesisService,
    SynthesisFact,
    client_pitch_text,
)

RUN_ID = UUID("aa000000-0000-0000-0000-000000000001")
VF5 = UUID("bb000000-0000-0000-0000-000000000005")
VF6_ECO = UUID("bb000000-0000-0000-0000-000000000006")
VF6_PLUS = UUID("bb000000-0000-0000-0000-000000000007")

#: Ngân sách khách gõ "300-700 triệu".
BUDGET_MIN = 300_000_000.0
BUDGET_MAX = 700_000_000.0

#: Giá thật trong catalog. VF 6 Plus vượt trần ~7% → đủ gần để vẫn gợi ý, kèm nhãn.
PRICES = {VF5: "496000000", VF6_ECO: "646000000", VF6_PLUS: "749000000"}
RANGES = {VF5: "326.00", VF6_ECO: "315.00", VF6_PLUS: "310.00"}
NAMES = {
    VF5: "VinFast VF 5 All New",
    VF6_ECO: "VinFast VF 6 Eco",
    VF6_PLUS: "VinFast VF 6 Plus",
}

MACHINE_PHRASES = (
    "được ghi nhận là",
    "đúng loại phương tiện bạn đang tìm",
    "đã xác nhận",
)


class BrokenLlm:
    """Cả hai bộ viết LLM đều trả bản không hợp lệ.

    Cố ý: đoạn văn trong báo cáo bug CHÍNH LÀ bản dự phòng deterministic
    (`_deterministic_fallback_draft`), nên muốn đo đúng nó thì phải ép cả hai bộ
    viết thất bại. Bản dự phòng là đáy của chất lượng câu chữ — sửa được nó thì
    mọi nhánh phía trên chỉ có thể tốt hơn.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def synthesize(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Mẫu này rất đáng mua vì 3 lý do."  # chữ số → bị từ chối


class Source:
    def __init__(self) -> None:
        self.facts = tuple(
            fact
            for vehicle_id in PRICES
            for fact in (
                SynthesisFact(
                    vehicle_id=vehicle_id,
                    fact_code="STARTING_PRICE_VND",
                    value_text=PRICES[vehicle_id],
                    unit="VND",
                    evidence_id=UUID(int=int(str(vehicle_id)[-1] or 0) * 10 + 1),
                    source_record="vehicle_prices",
                ),
                SynthesisFact(
                    vehicle_id=vehicle_id,
                    fact_code="CAR_RANGE_KM",
                    value_text=RANGES[vehicle_id],
                    unit="km",
                    evidence_id=UUID(int=int(str(vehicle_id)[-1] or 0) * 10 + 2),
                    source_record="cars",
                ),
            )
        )

    async def load_vehicle_name(self, *, run_id: UUID, vehicle_id: UUID) -> str | None:
        return NAMES[vehicle_id]

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]):
        return self.facts

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]):
        return ()


def _recommendations() -> list[Recommendation]:
    """Lý do như `domain/scoring` thật sinh ra: xe vượt trần mang lý do vượt trần."""

    return [
        Recommendation(
            vehicle_id=vehicle_id,
            rank=rank,
            reasons=[
                "[slot=vehicle_type] Đúng loại phương tiện CAR đã chọn",
                (
                    "[slot=budget_max_vnd] Vượt ngân sách 7%"
                    if vehicle_id is VF6_PLUS
                    else "[slot=budget_max_vnd] Giá nằm trong ngân sách đã xác nhận"
                ),
            ],
            display_name=NAMES[vehicle_id],
        )
        for rank, vehicle_id in enumerate((VF5, VF6_ECO, VF6_PLUS), start=1)
    ]


async def _pitches(*, budget_min: float | None, budget_max: float | None):
    service = DefaultSynthesisService(llm=BrokenLlm(), fallback_llm=BrokenLlm(), source=Source())
    return await service.synthesize(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        tco=None,
        budget_min_vnd=budget_min,
        budget_max_vnd=budget_max,
    )


@pytest.mark.asyncio
async def test_budget_range_cards_read_naturally_and_flag_the_over_budget_model() -> None:
    """Test bắt buộc của yêu cầu: ngân sách "300-700 triệu"."""

    pitches = await _pitches(budget_min=BUDGET_MIN, budget_max=BUDGET_MAX)

    assert len(pitches) == 3
    for pitch in pitches:
        for phrase in MACHINE_PHRASES:
            assert phrase not in pitch.pitch, (pitch.display_name, phrase)
        # Giá vẫn có, nhưng ở FIELD RIÊNG của thẻ — không nhắc lại trong mô tả.
        assert pitch.starting_price_vnd == PRICES[pitch.vehicle_id]
        assert PRICES[pitch.vehicle_id] not in pitch.pitch

    by_name = {pitch.display_name: pitch.pitch for pitch in pitches}
    # VF 6 Plus (749tr) vượt trần 700tr khoảng 7% → vẫn gợi ý, nhưng nói rõ.
    assert "(nhỉnh hơn ngân sách một chút)" in by_name["VinFast VF 6 Plus"]
    # Xe vượt trần KHÔNG được đồng thời nói là nằm trong ngân sách.
    assert "nằm trong ngân sách" not in by_name["VinFast VF 6 Plus"]
    # Hai mẫu trong khoảng không được gắn nhãn nào.
    assert "nhỉnh hơn ngân sách" not in by_name["VinFast VF 5 All New"]
    assert "thấp hơn ngân sách" not in by_name["VinFast VF 5 All New"]
    assert "nhỉnh hơn ngân sách" not in by_name["VinFast VF 6 Eco"]


@pytest.mark.asyncio
async def test_fallback_pitch_uses_only_planned_claims() -> None:
    pitches = await _pitches(budget_min=BUDGET_MIN, budget_max=BUDGET_MAX)
    top = next(pitch for pitch in pitches if pitch.vehicle_id == VF5)

    assert "đi được xa nhất" in top.pitch
    assert " và " not in top.pitch.split(".")[0]
    assert "326.00" not in top.pitch
    assert top.citations == ()


@pytest.mark.asyncio
async def test_fallback_pitch_contains_no_bullet_or_spec_table() -> None:
    pitches = await _pitches(budget_min=BUDGET_MIN, budget_max=BUDGET_MAX)

    assert all("* " not in pitch.pitch and "**:" not in pitch.pitch for pitch in pitches)


@pytest.mark.asyncio
async def test_fallback_pitch_contains_no_digits_outside_vehicle_name() -> None:
    pitches = await _pitches(budget_min=BUDGET_MIN, budget_max=BUDGET_MAX)

    for pitch in pitches:
        prose = pitch.pitch.replace(pitch.display_name, "")
        assert not any(character.isdigit() for character in prose)


@pytest.mark.asyncio
async def test_fallback_pitch_is_at_most_two_prose_sentences() -> None:
    pitches = await _pitches(budget_min=BUDGET_MIN, budget_max=BUDGET_MAX)

    for pitch in pitches:
        prose = pitch.pitch.split("\n\n")[-1]
        assert "\n" not in prose
        assert 1 <= prose.count(".") <= 2


@pytest.mark.asyncio
async def test_fallback_omits_pitch_when_candidate_has_no_planned_claims() -> None:
    recommendation = Recommendation(
        vehicle_id=VF5, rank=1, reasons=["Lý do thô không được duyệt"], display_name=NAMES[VF5]
    )
    service = DefaultSynthesisService(llm=BrokenLlm(), fallback_llm=BrokenLlm(), source=Source())

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=[recommendation], tco=None)

    assert len(pitches) == 1
    assert pitches[0].pitch == ""


@pytest.mark.asyncio
async def test_fallback_motorbike_pitch_is_claim_only_prose() -> None:
    motorbike = UUID("bb000000-0000-0000-0000-000000000008")
    source = Source()
    source.facts = (
        SynthesisFact(
            vehicle_id=motorbike,
            fact_code="MOTORBIKE_RANGE_MAX_KM",
            value_text="203",
            unit="km",
            evidence_id=UUID(int=81),
            source_record="motorbikes",
        ),
    )
    source_name = NAMES[VF5]
    NAMES[motorbike] = "VinFast Evo Grand"
    recommendation = Recommendation(
        vehicle_id=motorbike,
        rank=1,
        reasons=["[slot=vehicle_type] Đúng loại phương tiện ELECTRIC_MOTORBIKE đã chọn"],
        display_name=NAMES[motorbike],
    )
    service = DefaultSynthesisService(llm=BrokenLlm(), fallback_llm=BrokenLlm(), source=source)

    pitch = (await service.synthesize(run_id=RUN_ID, recommendations=[recommendation], tco=None))[0]

    assert "thuộc đúng dòng xe" in pitch.pitch
    assert "203" not in pitch.pitch
    assert "* " not in pitch.pitch
    del NAMES[motorbike]
    assert source_name == NAMES[VF5]


@pytest.mark.asyncio
async def test_a_unit_already_in_the_label_is_not_echoed_after_the_number() -> None:
    """ "**Số chỗ ngồi**: 5 chỗ ngồi" đọc như một lỗi copy, không phải một thông số."""

    assert client_pitch_text("* **Số chỗ ngồi**: 5 chỗ ngồi [1]") == "* **Số chỗ ngồi**: 5"
    # "km" ở đây là thông tin chứ không phải tiếng vọng của nhãn — giữ nguyên.
    assert client_pitch_text("* **Quãng đường mỗi lần sạc**: 326.00 km [1]") == "* **Quãng đường mỗi lần sạc**: 326 km"


@pytest.mark.asyncio
async def test_no_budget_label_appears_when_the_customer_gave_no_range() -> None:
    """Không có ngân sách thì không có gì để lệch — thẻ không được đoán ra một nhãn."""

    pitches = await _pitches(budget_min=None, budget_max=None)

    for pitch in pitches:
        assert "ngân sách một chút" not in pitch.pitch
