"""Contract tests for A5-6 placeholder-only answer synthesis."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import Recommendation, TcoResult
from src.agents.domain.claim_policy import PlannedClaim
from src.agents.prompts.synthesis_prompts import build_synthesis_prompt
from src.agents.services.synthesis import (
    DefaultSynthesisService,
    SynthesisFact,
    SynthesisQuote,
    _mask_vehicle_name,
    _reject_digits_outside_placeholders,
    _render_all,
    _validate_draft,
    client_pitch_text,
)

RUN_ID = UUID("10000000-0000-0000-0000-000000000101")
VEHICLE_ID = UUID("20000000-0000-0000-0000-000000000101")
RANGE_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000101")
PRICE_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000102")
TCO_EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000103")
VEHICLE_2 = UUID("20000000-0000-0000-0000-000000000102")
VEHICLE_3 = UUID("20000000-0000-0000-0000-000000000103")
RANGE_EVIDENCE_2 = UUID("30000000-0000-0000-0000-000000000201")
RANGE_EVIDENCE_3 = UUID("30000000-0000-0000-0000-000000000301")


class FakeLlm:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def synthesize(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


class FakeSynthesisSource:
    def __init__(
        self,
        facts: tuple[SynthesisFact, ...],
        *,
        vehicle_name: str = "VinFast VF 5",
    ) -> None:
        self.facts = facts
        self.vehicle_name = vehicle_name
        self.calls: list[tuple[UUID, tuple[UUID, ...]]] = []

    async def load_vehicle_name(self, *, run_id: UUID, vehicle_id: UUID) -> str | None:
        return self.vehicle_name

    async def load_facts(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple[SynthesisFact, ...]:
        self.calls.append((run_id, vehicle_ids))
        return self.facts

    async def load_quotes(self, *, run_id: UUID, vehicle_ids: tuple[UUID, ...]) -> tuple[SynthesisQuote, ...]:
        return ()


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=[
                "[slot=required_range_km] Tầm hoạt động đáp ứng quãng đường đã nêu",
                "[slot=budget_max_vnd] Giá nằm trong ngân sách đã xác nhận",
            ],
        )
    ]


def _facts() -> tuple[SynthesisFact, ...]:
    return (
        SynthesisFact(
            vehicle_id=VEHICLE_ID,
            fact_code="CAR_RANGE_KM",
            value_text="399",
            unit="km",
            evidence_id=RANGE_EVIDENCE_ID,
            source_record="cars:car-range-row",
        ),
        SynthesisFact(
            vehicle_id=VEHICLE_ID,
            fact_code="STARTING_PRICE_VND",
            value_text="690000000",
            unit="VND",
            evidence_id=PRICE_EVIDENCE_ID,
            source_record="vehicle_prices:price-row",
        ),
    )


class FakeMultiVehicleSource:
    """Trả facts/quotes của mọi xe được hỏi, đếm số lần bị gọi."""

    def __init__(
        self,
        facts: tuple[SynthesisFact, ...],
        quotes: tuple[SynthesisQuote, ...] = (),
    ) -> None:
        self.facts = facts
        self.quotes = quotes
        self.fact_calls: list[tuple[UUID, ...]] = []
        self.quote_calls: list[tuple[UUID, ...]] = []

    async def load_facts(self, *, run_id, vehicle_ids):
        self.fact_calls.append(vehicle_ids)
        return tuple(fact for fact in self.facts if fact.vehicle_id in vehicle_ids)

    async def load_quotes(self, *, run_id, vehicle_ids):
        self.quote_calls.append(vehicle_ids)
        return tuple(quote for quote in self.quotes if quote.vehicle_id in vehicle_ids)


class NameEchoLlm:
    """Trả một câu khác nhau cho mỗi xe, lấy tên xe ra khỏi chính prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def synthesize(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        name = prompt.split("Mẫu xe đang giới thiệu: ")[1].split("\n")[0]
        return f"{name} đi được {{CAR_RANGE_KM}}."


def _range_fact(vehicle_id: UUID, evidence_id: UUID, value: str) -> SynthesisFact:
    return SynthesisFact(
        vehicle_id=vehicle_id,
        fact_code="CAR_RANGE_KM",
        value_text=value,
        unit="km",
        evidence_id=evidence_id,
        source_record=f"cars:{vehicle_id}",
    )


def _three_recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=["[slot=budget_max_vnd] trong ngân sách"],
            display_name="Xe Một",
        ),
        Recommendation(
            vehicle_id=VEHICLE_2,
            rank=2,
            reasons=["[slot=required_range_km] đủ quãng đường"],
            display_name="Xe Hai",
        ),
        Recommendation(
            vehicle_id=VEHICLE_3,
            rank=3,
            reasons=["[slot=purpose] hợp mục đích"],
            display_name="Xe Ba",
        ),
    ]


@pytest.mark.asyncio
async def test_each_vehicle_gets_its_own_pitch_with_its_own_citations() -> None:
    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
            _range_fact(VEHICLE_2, RANGE_EVIDENCE_2, "450"),
            _range_fact(VEHICLE_3, RANGE_EVIDENCE_3, "201"),
        )
    )
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations(), tco=None)

    assert [pitch.rank for pitch in pitches] == [1, 2, 3]
    assert [pitch.display_name for pitch in pitches] == ["Xe Một", "Xe Hai", "Xe Ba"]
    assert "Xe Một" in pitches[0].pitch
    assert "399 km [1]" in pitches[0].pitch
    assert "đi được xa nhất" in pitches[1].pitch
    assert "450" not in pitches[1].pitch
    assert [citation.evidence_id for citation in pitches[0].citations] == [RANGE_EVIDENCE_ID]
    assert pitches[1].citations == ()
    # Ba pitch là ba luận điệu riêng, không phải một câu lặp ba lần.
    assert len({pitch.pitch for pitch in pitches}) == 3


@pytest.mark.asyncio
async def test_facts_and_quotes_are_loaded_once_for_the_whole_group() -> None:
    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
            _range_fact(VEHICLE_2, RANGE_EVIDENCE_2, "450"),
            _range_fact(VEHICLE_3, RANGE_EVIDENCE_3, "201"),
        )
    )
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations(), tco=None)

    assert source.fact_calls == [(VEHICLE_ID, VEHICLE_2, VEHICLE_3)]
    assert source.quote_calls == [(VEHICLE_ID, VEHICLE_2, VEHICLE_3)]


class OneVehicleFailsLlm:
    """Xe Hai làm LLM nổ; hai xe kia trả bình thường."""

    async def synthesize(self, *, prompt: str) -> str:
        name = prompt.split("Mẫu xe đang giới thiệu: ")[1].split("\n")[0]
        if name == "Xe Hai":
            raise RuntimeError("llm timeout")
        return f"{name} đi được {{CAR_RANGE_KM}}."


class AllVehiclesFailLlm:
    async def synthesize(self, *, prompt: str) -> str:
        raise RuntimeError("llm down")


@pytest.mark.asyncio
async def test_a_transport_failure_keeps_the_vehicle_with_a_deterministic_pitch() -> None:
    """LLM timeout KHÔNG được làm biến mất một chiếc xe.

    Bản trước cố ý thả lỗi transport lên `asyncio.gather(return_exceptions=True)`
    "để lỗi hạ tầng lan nhanh". Cái lan nhanh thật ra là một chiếc xe rơi khỏi
    bản đề xuất trong im lặng: khách hỏi ba xe, nhận về hai, và không dòng log
    nào nói xe thứ ba đi đâu. Lượt chỉ có MỘT xe hợp ngân sách thì bản đề xuất
    rỗng và guardrail báo lỗi cấu hình — khách nhận câu "đã chuyển tư vấn viên"
    giả.

    Bản dựng tay không cần LLM và luôn qua được `_validate_draft` (nó chỉ ghép
    placeholder từ chính snapshot), nên xe mất chỗ thuyết phục chứ không mất
    khỏi câu trả lời — và không có số nào bị bịa.
    """

    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
            _range_fact(VEHICLE_2, RANGE_EVIDENCE_2, "450"),
            _range_fact(VEHICLE_3, RANGE_EVIDENCE_3, "201"),
        )
    )
    service = DefaultSynthesisService(llm=OneVehicleFailsLlm(), source=source)

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations(), tco=None)

    assert [pitch.display_name for pitch in pitches] == ["Xe Một", "Xe Hai", "Xe Ba"]
    hai = next(pitch for pitch in pitches if pitch.display_name == "Xe Hai")
    assert hai.pitch.strip()
    # Bản dựng tay ghép từ claim đã duyệt nên KHÔNG có số nào tự viết ra. Số duy
    # nhất được phép xuất hiện là số render từ chính snapshot ("450"); ngoài nó
    # ra, mọi chữ số đều là số bịa.
    assert all(ch.isdigit() is False for ch in hai.pitch.replace("450", ""))


@pytest.mark.asyncio
async def test_every_writer_down_still_returns_every_vehicle() -> None:
    """Nhà cung cấp chết hoàn toàn: mất lời tư vấn, KHÔNG mất bản đề xuất."""

    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
            _range_fact(VEHICLE_2, RANGE_EVIDENCE_2, "450"),
            _range_fact(VEHICLE_3, RANGE_EVIDENCE_3, "201"),
        )
    )
    service = DefaultSynthesisService(llm=AllVehiclesFailLlm(), source=source)

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations(), tco=None)

    assert [pitch.display_name for pitch in pitches] == ["Xe Một", "Xe Hai", "Xe Ba"]


@pytest.mark.asyncio
async def test_one_failing_vehicle_is_logged_with_its_vehicle_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cứu được lượt KHÔNG có nghĩa là im lặng.

    Giờ xe không còn biến mất, nên nguy cơ đổi hình dạng: nhà cung cấp có thể
    chết cả ngày mà mọi lượt vẫn "thành công", chỉ nhạt đi — hỏng theo kiểu
    không ai nhìn thấy. Dòng log phải nêu ĐÚNG xe nào và ĐÚNG lỗi gì.
    """

    source = FakeMultiVehicleSource(
        (
            _range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),
            _range_fact(VEHICLE_2, RANGE_EVIDENCE_2, "450"),
            _range_fact(VEHICLE_3, RANGE_EVIDENCE_3, "201"),
        )
    )
    service = DefaultSynthesisService(llm=OneVehicleFailsLlm(), source=source)

    with caplog.at_level("WARNING", logger="src.agents.services.synthesis"):
        pitches = await service.synthesize(run_id=RUN_ID, recommendations=_three_recommendations(), tco=None)

    assert [pitch.display_name for pitch in pitches] == ["Xe Một", "Xe Hai", "Xe Ba"]
    noted = [r for r in caplog.records if str(VEHICLE_2) in r.getMessage()]
    assert len(noted) == 1
    assert "llm timeout" in noted[0].getMessage()
    assert "RuntimeError" in noted[0].getMessage()


@pytest.mark.asyncio
async def test_single_recommendation_returns_exactly_one_pitch() -> None:
    source = FakeMultiVehicleSource((_range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),))
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=[_three_recommendations()[0]],
        tco=None,
    )

    assert len(pitches) == 1
    assert pitches[0].vehicle_id == VEHICLE_ID


@pytest.mark.asyncio
async def test_vehicle_without_documents_gets_a_pitch_without_quote_footnotes() -> None:
    source = FakeMultiVehicleSource((_range_fact(VEHICLE_ID, RANGE_EVIDENCE_ID, "399"),), quotes=())
    service = DefaultSynthesisService(llm=NameEchoLlm(), source=source)

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=[_three_recommendations()[0]],
        tco=None,
    )

    assert len(pitches) == 1
    assert '"' not in pitches[0].pitch


def test_render_all_numbers_facts_and_quotes_in_one_sequence() -> None:
    fact = SynthesisFact(
        vehicle_id=VEHICLE_ID,
        fact_code="CAR_RANGE_KM",
        value_text="399",
        unit="km",
        evidence_id=RANGE_EVIDENCE_ID,
        source_record="cars:car-range-row",
    )
    quote = SynthesisQuote(
        text="Cửa sổ trời toàn cảnh",
        evidence_id=PRICE_EVIDENCE_ID,
        vehicle_id=VEHICLE_ID,
        source_record="vehicle_documents:doc-1",
    )

    rendered, citations = _render_all(
        "Đi được {CAR_RANGE_KM}. Tài liệu ghi: {QUOTE_1}",
        {"CAR_RANGE_KM": fact},
        {"QUOTE_1": quote},
    )

    assert rendered == 'Đi được 399 km [1]. Tài liệu ghi: "Cửa sổ trời toàn cảnh" [2]'
    assert "evidence_id" not in rendered
    assert [(item.index, item.evidence_id) for item in citations] == [
        (1, RANGE_EVIDENCE_ID),
        (2, PRICE_EVIDENCE_ID),
    ]
    assert citations[0].source_record == "cars:car-range-row"
    assert citations[1].source_record == "vehicle_documents:doc-1"


def test_render_all_reuses_one_number_for_a_repeated_evidence() -> None:
    fact = SynthesisFact(
        vehicle_id=VEHICLE_ID,
        fact_code="CAR_RANGE_KM",
        value_text="399",
        unit="km",
        evidence_id=RANGE_EVIDENCE_ID,
        source_record="cars:car-range-row",
    )

    rendered, citations = _render_all("{CAR_RANGE_KM} và vẫn là {CAR_RANGE_KM}", {"CAR_RANGE_KM": fact}, {})

    assert rendered == "399 km [1] và vẫn là 399 km [1]"
    assert len(citations) == 1


def test_client_pitch_text_strips_footnotes_and_dedupes_units() -> None:
    assert client_pitch_text("Xe có 5 chỗ ngồi [1] chỗ ngồi.") == "Xe có 5 chỗ ngồi."
    assert client_pitch_text("Đi 399 km [1]. Giá 690000000 VND [2].") == ("Đi 399 km. Giá 690000000 VND.")


@pytest.mark.asyncio
async def test_llm_prompt_and_answer_have_no_digits_outside_placeholders() -> None:
    llm = FakeLlm(
        "Mẫu {CLAIM_REQUIRED_RANGE_KM}, có tầm hoạt động {CAR_RANGE_KM} và giá khởi điểm {STARTING_PRICE_VND}."
    )
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)

    prompt_without_placeholders = re.sub(r"\{[A-Z][A-Z0-9_]*\}", "", llm.prompts[0])
    answer_without_placeholders = re.sub(r"\{[A-Z][A-Z0-9_]*\}", "", llm.answer)
    assert not re.search(r"\d", prompt_without_placeholders)
    assert not re.search(r"\d", answer_without_placeholders)
    assert "required_range_km" not in llm.prompts[0]
    assert "slot=" not in llm.prompts[0]


@pytest.mark.asyncio
async def test_each_placeholder_renders_exact_snapshot_value_unit_and_evidence() -> None:
    source = FakeSynthesisSource(_facts())
    llm = FakeLlm("Tầm hoạt động {CAR_RANGE_KM}; giá khởi điểm {STARTING_PRICE_VND}.")
    service = DefaultSynthesisService(llm=llm, source=source)

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)
    answer = "\n\n".join(pitch.pitch for pitch in pitches)

    assert source.calls == [(RUN_ID, (VEHICLE_ID,))]
    assert "399 km [1]" in answer
    assert "690000000 VND [2]" in answer
    assert "evidence_id" not in answer
    assert "{" not in answer and "}" not in answer


@pytest.mark.asyncio
async def test_tco_placeholder_is_backed_by_matching_tco_source_fact() -> None:
    tco_fact = SynthesisFact(
        vehicle_id=VEHICLE_ID,
        fact_code="TCO_TOTAL_VND",
        value_text="735000000",
        unit="VND",
        evidence_id=TCO_EVIDENCE_ID,
        source_record="tco_results:tco-row",
    )
    tco = TcoResult(
        vehicle_id=VEHICLE_ID,
        total_vnd=Decimal("735000000"),
        components_vnd={},
        assumptions_id=UUID("40000000-0000-0000-0000-000000000101"),
        computed_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    service = DefaultSynthesisService(
        llm=FakeLlm("Tổng chi phí dự kiến {TCO_TOTAL_VND}."),
        source=FakeSynthesisSource((*_facts(), tco_fact)),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=tco)
    answer = "\n\n".join(pitch.pitch for pitch in pitches)

    assert "735000000 VND [1]" in answer
    assert "evidence_id" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm_answer, forbidden",
    [
        ("Quãng đường 400 km.", "400"),
        ("Quãng đường {DAILY_DISTANCE_KM}.", "DAILY_DISTANCE_KM"),
        ("Quãng đường {FAST_CHARGE_TIME_MINUTES}.", "FAST_CHARGE_TIME_MINUTES"),
        ("Phù hợp vì required_range_km >= nhu cầu.", "required_range_km"),
        ("Tính năng PANORAMIC_ROOF phù hợp.", "PANORAMIC_ROOF"),
    ],
)
async def test_rejects_unsafe_llm_output_before_render(llm_answer: str, forbidden: str) -> None:
    """Bản nháp không an toàn KHÔNG ra tới khách — nhưng xe không vì thế mà mất.

    Kiểm đúng cam kết của A6-1: chữ mô hình tự viết không rời hệ thống. Bản trước
    khẳng định `pitches == []`, mạnh hơn cam kết đó một bậc và chính chỗ mạnh thừa
    ấy làm chết lượt trên prod khi chỉ có một xe thoả điều kiện.
    """

    service = DefaultSynthesisService(llm=FakeLlm(llm_answer), source=FakeSynthesisSource(_facts()))

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)

    assert len(pitches) == 1
    assert forbidden not in pitches[0].pitch


class FirstAttemptViolatesLlm:
    """Lần đầu LLM viết chữ số ngoài placeholder, các lần sau tuân thủ."""

    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, *, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "Xe này chạy được 400 km."
        return "Xe này chạy được {CAR_RANGE_KM}."


@pytest.mark.asyncio
async def test_retries_a_llm_answer_that_violates_the_digit_constraint() -> None:
    source = FakeSynthesisSource(_facts())
    llm = FirstAttemptViolatesLlm()
    service = DefaultSynthesisService(llm=llm, source=source)

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)

    assert llm.calls == 2
    assert len(pitches) == 1
    assert "399 km [1]" in pitches[0].pitch


@pytest.mark.asyncio
async def test_rejects_source_value_that_does_not_match_tco_result() -> None:
    tco_fact = SynthesisFact(
        vehicle_id=VEHICLE_ID,
        fact_code="TCO_TOTAL_VND",
        value_text="1",
        unit="VND",
        evidence_id=TCO_EVIDENCE_ID,
        source_record="tco_results:tco-row",
    )
    tco = TcoResult(
        vehicle_id=VEHICLE_ID,
        total_vnd=Decimal("2"),
        components_vnd={},
        assumptions_id=None,
        computed_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    service = DefaultSynthesisService(
        llm=FakeLlm("Tổng chi phí {TCO_TOTAL_VND}."),
        source=FakeSynthesisSource((*_facts(), tco_fact)),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=tco)

    assert list(pitches) == []


def test_prompt_names_the_vehicle_and_forbids_writing_units() -> None:
    prompt = build_synthesis_prompt(
        vehicle_name="VF 6",
        available_claims=(("CLAIM_BUDGET_MAX_VND", "có giá nằm trong ngân sách đã xác nhận"),),
        available_placeholders=("CAR_RANGE_KM",),
    )

    assert "VF 6" in prompt
    assert "đơn vị" in prompt


def test_prompt_carries_customer_words_but_removes_their_digits() -> None:
    prompt = build_synthesis_prompt(
        vehicle_name="mẫu xe này",
        available_claims=(("CLAIM_VEHICLE_TYPE", "đúng loại phương tiện đang tìm"),),
        available_placeholders=("STARTING_PRICE_VND",),
        customer_wording=("chở gia đình về quê 80 km",),
    )

    assert "chở gia đình về quê" in prompt
    _reject_digits_outside_placeholders(prompt)


@pytest.mark.asyncio
async def test_vehicle_name_with_digits_does_not_trip_the_digit_guard() -> None:
    llm = FakeLlm("Mẫu VF tám đi được {CAR_RANGE_KM}.")
    source = FakeSynthesisSource(_facts())
    service = DefaultSynthesisService(llm=llm, source=source)

    rendered = await service.synthesize(
        run_id=RUN_ID,
        recommendations=[
            Recommendation(
                vehicle_id=VEHICLE_ID,
                rank=1,
                reasons=["[slot=budget_max_vnd] trong ngân sách"],
                display_name="VF 8",
            )
        ],
        tco=None,
    )

    assert rendered


@pytest.mark.asyncio
async def test_llm_writing_the_vehicle_name_with_its_digits_keeps_the_pitch() -> None:
    llm = FakeLlm("VinFast VF 3 All New đi được {CAR_RANGE_KM}.")
    source = FakeSynthesisSource(_facts())
    service = DefaultSynthesisService(llm=llm, source=source)

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=[
            Recommendation(
                vehicle_id=VEHICLE_ID,
                rank=1,
                reasons=["[slot=budget_max_vnd] trong ngân sách"],
                display_name="VinFast VF 3 All New",
            )
        ],
        tco=None,
    )

    assert len(pitches) == 1
    assert "399 km [1]" in pitches[0].pitch


@pytest.mark.asyncio
async def test_service_forwards_customer_wording_into_the_prompt() -> None:
    llm = FakeLlm("Xe này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    await service.synthesize(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        tco=None,
        customer_wording=("chở gia đình về quê",),
    )

    assert "chở gia đình về quê" in llm.prompts[0]


@pytest.mark.asyncio
async def test_feature_wording_is_dropped_when_the_vehicle_has_no_matching_claim() -> None:
    """Bug thật 2026-08-21 (Sếp báo): khách nêu tính năng KHÔNG có claim hợp lệ
    (vd catalog chưa duyệt) mà vẫn lọt vào ngữ cảnh LLM → LLM cố nhắc tới, bị
    `reject_unstructured_claims` chặn liên tục, hết retry thì handoff. Xe
    không có claim `CLAIM_ANTI_THEFT` thì "khoá chống trộm" không được vào
    prompt của XE ĐÓ."""

    llm = FakeLlm("Xe này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    await service.synthesize(
        run_id=RUN_ID,
        recommendations=_recommendations(),  # không có reason nào về ANTI_THEFT
        tco=None,
        feature_mention_codes=("ANTI_THEFT",),
    )

    assert "khoá chống trộm" not in llm.prompts[0]


def test_required_claims_are_deduplicated_and_bounded_deterministically() -> None:
    prompt = build_synthesis_prompt(
        vehicle_name="Xe Một",
        available_claims=tuple((f"CLAIM_{index}", f"claim {index}") for index in range(5)),
        available_placeholders=(),
        required_claims=("CLAIM_3", "CLAIM_1", "CLAIM_3", "CLAIM_4"),
    )

    required_section = prompt.split("BẮT BUỘC nêu các claim sau: ", maxsplit=1)[1]
    assert required_section.startswith("{CLAIM_3} {CLAIM_1} {CLAIM_4}.")
    assert "{CLAIM_0}" not in required_section.split(". ", maxsplit=1)[0]


def test_approved_feature_claim_is_required_in_prompt() -> None:
    prompt = build_synthesis_prompt(
        vehicle_name="Xe Một",
        available_claims=(("CLAIM_ANTI_THEFT", "được trang bị khoá chống trộm"),),
        available_placeholders=(),
        required_claims=("CLAIM_ANTI_THEFT",),
    )

    assert "CLAIM_ANTI_THEFT" in prompt
    assert "không được bỏ qua claim nào" in prompt


@pytest.mark.asyncio
async def test_omitted_approved_feature_claim_is_rejected_and_retry_preserves_requirement() -> None:
    class RetryLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def synthesize(self, *, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "Xe này {CLAIM_REQUIRED_RANGE_KM}."
            return "Xe này {CLAIM_ANTI_THEFT} và {CLAIM_REQUIRED_RANGE_KM}."

    llm = RetryLlm()
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))
    recommendations = [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=[
                "[slot=required_range_km] Tầm hoạt động đáp ứng quãng đường đã nêu",
                "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; evidence=e1] "
                "Xe được trang bị khoá chống trộm theo dữ liệu đã duyệt",
            ],
        )
    ]

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=recommendations,
        tco=None,
        feature_mention_codes=("ANTI_THEFT",),
    )

    assert len(pitches) == 1
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_omitted_approved_feature_claim_is_rejected_by_validator() -> None:
    claim = PlannedClaim("CLAIM_ANTI_THEFT", "habit_need_tags", "được trang bị khoá chống trộm")

    with pytest.raises(ValueError, match="mandatory claim"):
        _validate_draft(
            "Xe này {CLAIM_REQUIRED_RANGE_KM}.",
            {fact.fact_code: fact for fact in _facts()},
            {
                "CLAIM_REQUIRED_RANGE_KM": PlannedClaim(
                    "CLAIM_REQUIRED_RANGE_KM", "required_range_km", "có tầm vận hành"
                ),
                claim.placeholder: claim,
            },
            "VinFast VF 5",
            ("CLAIM_ANTI_THEFT",),
        )


@pytest.mark.asyncio
async def test_feature_wording_appears_when_the_vehicle_has_a_matching_claim() -> None:
    llm = FakeLlm("Xe này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))
    recommendations = [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=[
                "[slot=required_range_km] Tầm hoạt động đáp ứng quãng đường đã nêu",
                "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; "
                "evidence=e1] Có tính năng khoá chống trộm mà khách vừa xác nhận "
                "quan tâm",
            ],
        )
    ]

    await service.synthesize(
        run_id=RUN_ID,
        recommendations=recommendations,
        tco=None,
        feature_mention_codes=("ANTI_THEFT",),
    )

    assert "khoá chống trộm" in llm.prompts[0]


def test_mask_vehicle_name_removes_only_the_full_name_phrase() -> None:
    """[C2] "VF 8" che đúng tên xe, không che số bịa "8 người" đứng riêng."""

    masked = _mask_vehicle_name("VinFast VF 8 All New phù hợp cho 8 người.", "VF 8")

    assert "8 người" in masked
    assert "VF 8" not in masked


@pytest.mark.asyncio
async def test_fabricated_seat_count_is_rejected_despite_digits_in_vehicle_name() -> None:
    """[C2] Số bịa "8 người" không được ra tới khách, dù tên xe chứa "8".

    Trước 2026-08-26 bài này khẳng định `pitches == ()` — tức XE BIẾN MẤT. Đó là
    nguyên nhân gốc của `GUARDRAIL_CONFIGURATION_ERROR` đo được trên prod: lượt
    chỉ có một xe thoả ngân sách thì bản nháp rỗng và khách nhận câu "đã chuyển
    tư vấn viên" giả. Điều CẦN bảo đảm là chữ bịa không rời hệ thống, không phải
    là chiếc xe phải biến mất — nên giờ xe ở lại với bản dựng tay từ snapshot.
    """

    llm = FakeLlm("VinFast VF 8 All New phù hợp cho 8 người và đi {CAR_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=[
            Recommendation(
                vehicle_id=VEHICLE_ID,
                rank=1,
                reasons=["[slot=budget_max_vnd] trong ngân sách"],
                display_name="VinFast VF 8 All New",
            )
        ],
        tco=None,
    )

    assert len(pitches) == 1
    assert "8 người" not in pitches[0].pitch


@pytest.mark.asyncio
async def test_unstructured_suitability_claim_is_rejected() -> None:
    """Cụm tiếp thị mơ hồ bị loại khỏi câu chữ, nhưng xe vẫn được đề xuất."""

    llm = FakeLlm("Mẫu này rất lý tưởng cho những chuyến đi xa với {CAR_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    pitches = await service.synthesize(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        tco=None,
        customer_wording=("thường xuyên về quê",),
    )

    assert len(pitches) == 1
    assert "lý tưởng" not in pitches[0].pitch


@pytest.mark.asyncio
async def test_supported_claim_placeholder_is_rendered_deterministically() -> None:
    llm = FakeLlm("Mẫu này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)
    answer = pitches[0].pitch

    assert "tầm vận hành thoải mái cho quãng đường" in answer.casefold()
    assert "CLAIM_REQUIRED_RANGE_KM" not in answer


@pytest.mark.asyncio
async def test_over_budget_reason_renders_a_negative_budget_claim() -> None:
    recommendations = [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=["[slot=budget_max_vnd] Vượt ngân sách 526.667%"],
        )
    ]
    service = DefaultSynthesisService(
        llm=FakeLlm("Mẫu này {CLAIM_BUDGET_MAX_VND}."),
        source=FakeSynthesisSource(_facts()),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=recommendations, tco=None)
    answer = pitches[0].pitch

    assert "cao hơn ngân sách" in answer
    assert "nằm trong ngân sách" not in answer


@pytest.mark.asyncio
async def test_invalid_primary_draft_is_regenerated_by_fallback_model() -> None:
    primary = FakeLlm("Mẫu này rất lý tưởng cho những chuyến đi xa.")
    fallback = FakeLlm("Mẫu này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(
        llm=primary,
        fallback_llm=fallback,
        source=FakeSynthesisSource(_facts()),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)
    answer = pitches[0].pitch

    assert len(primary.prompts) == 1
    assert len(fallback.prompts) == 1
    assert "tầm vận hành thoải mái cho quãng đường" in answer.casefold()


@pytest.mark.asyncio
async def test_invalid_primary_and_fallback_use_deterministic_approved_claims() -> None:
    primary = FakeLlm("Mẫu này rất lý tưởng cho những chuyến đi xa.")
    fallback = FakeLlm("Mẫu này phù hợp với nhu cầu của bạn.")
    service = DefaultSynthesisService(
        llm=primary,
        fallback_llm=fallback,
        source=FakeSynthesisSource(_facts()),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=_recommendations(), tco=None)
    answer = pitches[0].pitch

    assert len(primary.prompts) == 1
    assert len(fallback.prompts) == 1
    assert "tầm vận hành thoải mái cho quãng đường" in answer.casefold()
    assert "nằm trong ngân sách" in answer.casefold()
    assert "mẫu xe này" in answer
    citation_index = {citation.evidence_id: citation.index for citation in pitches[0].citations}
    assert "tầm vận hành thoải mái" in answer
    assert "399" not in answer
    # GIÁ cố ý KHÔNG nằm trong đoạn mô tả: thẻ xe đã có dòng giá riêng, đã format
    # dấu phân nghìn. Nhắc lại nó ở đây vừa lặp, vừa in ra con số thô "690000000".
    assert "690000000" not in answer
    assert PRICE_EVIDENCE_ID not in citation_index
    assert pitches[0].starting_price_vnd == "690000000"
    assert "{" not in answer and "}" not in answer


@pytest.mark.asyncio
async def test_lower_ranked_vehicle_cannot_authorize_claim_for_top_vehicle() -> None:
    recommendations = [
        Recommendation(
            vehicle_id=VEHICLE_ID,
            rank=1,
            reasons=["[slot=budget_max_vnd] Giá nằm trong ngân sách"],
        ),
        Recommendation(
            vehicle_id=UUID("20000000-0000-0000-0000-000000000102"),
            rank=2,
            reasons=["[slot=passenger_count] Đủ chỗ ngồi"],
        ),
    ]
    service = DefaultSynthesisService(
        llm=FakeLlm("Mẫu này {CLAIM_PASSENGER_COUNT}."),
        source=FakeSynthesisSource(_facts()),
    )

    pitches = await service.synthesize(run_id=RUN_ID, recommendations=recommendations, tco=None)
    by_vehicle = {pitch.vehicle_id: pitch.pitch for pitch in pitches}

    # Xe hạng 1 vẫn có mặt, nhưng KHÔNG được mượn lý do "đủ chỗ ngồi" của xe hạng 2.
    assert set(by_vehicle) == {recommendations[0].vehicle_id, recommendations[1].vehicle_id}
    assert "chỗ ngồi" not in by_vehicle[recommendations[0].vehicle_id]


@pytest.mark.asyncio
async def test_the_distinguishing_claim_is_required_not_merely_offered() -> None:
    """Bỏ qua câu phân biệt thì bản nháp bị loại và phải viết lại.

    Sếp 2026-08-27: văn các thẻ xe giống hệt nhau. Nguyên nhân đo được trên prod:
    mọi claim đều nằm dưới nhãn "được phép dùng", nên mô hình nhặt mấy câu chung
    (đúng dòng xe, đủ chỗ ngồi) — vốn giống nhau ở mọi xe cùng thoả một bộ lý do
    — rồi thôi. Thêm một claim phân biệt vào danh sách TUỲ CHỌN không đổi được
    gì; nó phải được ĐÒI.
    """

    llm = FakeLlm("Mẫu này {CLAIM_REQUIRED_RANGE_KM}.")
    service = DefaultSynthesisService(llm=llm, source=FakeSynthesisSource(_facts()))
    standout = PlannedClaim(
        placeholder="CLAIM_STANDOUT",
        slot="standout",
        text="đi được xa nhất trong nhóm em vừa chọn",
    )

    with pytest.raises(ValueError, match="mandatory claims"):
        _validate_draft(
            "Mẫu này {CLAIM_REQUIRED_RANGE_KM}.",
            {},
            {"CLAIM_REQUIRED_RANGE_KM": standout, "CLAIM_STANDOUT": standout},
            "VF 8",
            ("CLAIM_STANDOUT",),
        )
    del service, llm


@pytest.mark.asyncio
async def test_a_draft_using_the_distinguishing_claim_passes() -> None:
    standout = PlannedClaim(
        placeholder="CLAIM_STANDOUT",
        slot="standout",
        text="đi được xa nhất trong nhóm em vừa chọn",
    )

    placeholders = _validate_draft(
        "Mẫu này {CLAIM_STANDOUT}.",
        {},
        {"CLAIM_STANDOUT": standout},
        "VF 8",
        ("CLAIM_STANDOUT",),
    )

    assert "CLAIM_STANDOUT" in placeholders
