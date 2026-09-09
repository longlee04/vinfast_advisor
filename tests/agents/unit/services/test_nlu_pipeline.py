from __future__ import annotations

import json

import pytest

from src.agents.domain.entity_catalog import EntityCategory, default_catalog
from src.agents.domain.nlu_confidence import NluTier
from src.agents.domain.values import Intent
from src.agents.services.nlu_pipeline import (
    NluPipelineConfig,
    NluPipelineServiceImpl,
    build_known_tokens,
)
from src.agents.services.rewrite import RewriteServiceImpl

CATALOG = default_catalog()
KNOWN_TOKENS = build_known_tokens(CATALOG)


class SpyRewriter:
    """Bộ rewrite giả, đếm số lần thật sự gọi mô hình."""

    def __init__(self, payload: object = None, fails: bool = False) -> None:
        self.calls = 0
        self._payload = payload
        self._fails = fails

    async def rewrite(self, *, prompt: str) -> str:
        self.calls += 1
        if self._fails:
            raise RuntimeError("LLM khong phan hoi")
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)


def _pipeline(rewriter: SpyRewriter | None = None, **config: object) -> NluPipelineServiceImpl:
    return NluPipelineServiceImpl(
        rewrite_service=RewriteServiceImpl(rewriter=rewriter, known_tokens=KNOWN_TOKENS),
        catalog=CATALOG,
        config=NluPipelineConfig(**config) if config else NluPipelineConfig(),
    )


# ── Ngân sách lần gọi LLM (A4-2) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_clean_message_costs_zero_extra_llm_calls() -> None:
    """A4-2 chốt "lượt hỏi slot ≤ 1 lần gọi LLM" và có test spy canh con số đó.

    Bước này nằm TRƯỚC `extract_slots`; gọi mô hình ở mọi lượt sẽ đội mọi lượt
    lên gấp đôi và phá cả ngân sách lẫn p95 ≤ 6s (PRD 8.5).
    """

    spy = SpyRewriter()

    await _pipeline(spy).recognize(user_message="VF5 giá bao nhiêu")

    assert spy.calls == 0


@pytest.mark.asyncio
async def test_a_garbled_message_spends_exactly_one_call() -> None:
    spy = SpyRewriter({"rewritten": "thông tin xe VF 5", "confidence": 0.95})

    await _pipeline(spy).recognize(user_message="tho ti x vf năm")

    assert spy.calls == 1


# ── Lớp 1 hỏng không được kéo sập ba lớp còn lại ──────────────────────────────


@pytest.mark.asyncio
async def test_a_model_outage_still_recognises_the_vehicle() -> None:
    """Alias số-đếm tiếng Việt của Lớp 2 bắt được "vf năm" mà không cần Lớp 1."""

    decision = await _pipeline(SpyRewriter(fails=True)).recognize(user_message="tho ti x vf năm")

    assert decision.rewrite.reason == "llm_unavailable"
    assert decision.classification.vehicle_names == ("VF 5",)
    assert decision.tier is NluTier.AUTO


@pytest.mark.asyncio
async def test_an_unreadable_payload_falls_back_to_the_original() -> None:
    decision = await _pipeline(SpyRewriter("khong phai JSON")).recognize(user_message="tho ti x vf năm")

    assert decision.rewrite.applied is False
    assert decision.message_for_extraction == "tho ti x vf năm"


@pytest.mark.asyncio
async def test_a_fenced_json_payload_is_still_read() -> None:
    fenced = '```json\n{"rewritten": "thông tin xe VF 5", "confidence": 0.95}\n```'

    decision = await _pipeline(SpyRewriter(fenced)).recognize(user_message="tho ti x vf năm")

    assert decision.rewrite.applied is True
    assert decision.message_for_extraction == "thông tin xe VF 5"


# ── Câu gốc đi song song, không bị ghi đè ─────────────────────────────────────


@pytest.mark.asyncio
async def test_the_original_message_is_always_preserved() -> None:
    spy = SpyRewriter({"rewritten": "thông tin xe VF 5", "confidence": 0.95})

    decision = await _pipeline(spy).recognize(user_message="tho ti x vf năm")

    assert decision.rewrite.original == "tho ti x vf năm"
    assert decision.rewrite.rewritten == "thông tin xe VF 5"


# ── Lớp 4: ba nhánh ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_unintelligible_message_asks_for_clarification_with_buttons() -> None:
    """PRD 5.9: mọi câu từ chối phải kèm lối thoát."""

    decision = await _pipeline(SpyRewriter({"rewritten": "zxcv qwer", "confidence": 0.0})).recognize(
        user_message="zxcv qwer asdf"
    )

    assert decision.tier is NluTier.CLARIFY
    assert decision.reply is not None
    assert len(decision.quick_replies) > 0
    assert decision.pending_confirmation is None


@pytest.mark.asyncio
async def test_a_medium_confidence_turn_asks_the_customer_to_confirm() -> None:
    thresholds_force_confirm = NluPipelineConfig()
    pipeline = NluPipelineServiceImpl(
        rewrite_service=RewriteServiceImpl(
            rewriter=SpyRewriter({"rewritten": "thông tin xe VF 5", "confidence": 0.72}),
            known_tokens=KNOWN_TOKENS,
        ),
        catalog=CATALOG,
        config=thresholds_force_confirm,
    )

    decision = await pipeline.recognize(user_message="thog tn xe vf nem")

    assert decision.tier is NluTier.CONFIRM
    assert decision.pending_confirmation is not None
    assert "VF 5" in (decision.reply or "")
    assert [option.value for option in decision.quick_replies] == ["đúng", "không phải"]


@pytest.mark.asyncio
async def test_the_confirmation_record_remembers_what_to_run_next_turn() -> None:
    """Lượt sau khách chỉ gõ "đúng" — câu đó không mang nội dung nào để chạy lại."""

    pipeline = NluPipelineServiceImpl(
        rewrite_service=RewriteServiceImpl(
            rewriter=SpyRewriter({"rewritten": "thông tin xe VF 5", "confidence": 0.72}),
            known_tokens=KNOWN_TOKENS,
        ),
        catalog=CATALOG,
    )

    decision = await pipeline.recognize(user_message="thog tn xe vf nem")

    assert decision.pending_confirmation is not None
    assert decision.pending_confirmation.proposed_text == "thông tin xe VF 5"
    assert decision.pending_confirmation.vehicle_names == ("VF 5",)


# ── Ba lối tắt bắt buộc đi thẳng ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_active_advisory_flow_is_never_interrupted() -> None:
    """Bot hỏi ngân sách, khách đáp "700 triệu": không khớp entity nào."""

    decision = await _pipeline(SpyRewriter()).recognize(user_message="tam 700 tr", known_slots={"passenger_count": 5})

    assert decision.tier is NluTier.AUTO


@pytest.mark.asyncio
async def test_an_active_handoff_is_never_interrupted() -> None:
    decision = await _pipeline(SpyRewriter()).recognize(user_message="zxcv qwer asdf", handoff_active=True)

    assert decision.tier is NluTier.AUTO


@pytest.mark.asyncio
async def test_shadow_mode_keeps_the_logs_but_changes_no_behaviour() -> None:
    """Nút lùi một bước: bốn lớp vẫn chạy, hệ thống vẫn hành xử y như trước."""

    decision = await _pipeline(SpyRewriter(), routing_enabled=False).recognize(user_message="zxcv qwer asdf")

    assert decision.tier is NluTier.AUTO
    assert decision.reply is None


# ── Config ────────────────────────────────────────────────────────────────────


def test_config_reads_thresholds_from_the_environment() -> None:
    config = NluPipelineConfig.from_env({"NLU_AUTO_THRESHOLD": "0.9", "NLU_CONFIRM_THRESHOLD": "0.5"})

    assert config.thresholds.auto == 0.9
    assert config.thresholds.confirm == 0.5


def test_a_broken_threshold_keeps_the_default() -> None:
    """Một biến môi trường gõ sai không được lặng lẽ đẩy ngưỡng về 0."""

    config = NluPipelineConfig.from_env({"NLU_AUTO_THRESHOLD": "khong-phai-so"})

    assert config.thresholds.auto == 0.85


def test_inverted_thresholds_are_rejected() -> None:
    """Đảo ngưỡng thì dải "xác nhận" biến mất mà không ai nhận ra."""

    config = NluPipelineConfig.from_env({"NLU_AUTO_THRESHOLD": "0.5", "NLU_CONFIRM_THRESHOLD": "0.9"})

    assert (config.thresholds.auto, config.thresholds.confirm) == (0.85, 0.60)


def test_suggested_models_only_offer_vehicles_the_catalog_knows() -> None:
    """Một lối thoát dẫn vào ngõ cụt còn tệ hơn không có lối thoát nào.

    Khách bấm một mẫu xe không còn trong danh mục sẽ nhận "chưa tìm thấy mẫu
    này" — đúng lúc họ vừa được mời bấm để thoát khỏi chỗ bế tắc.
    """

    pipeline = NluPipelineServiceImpl(catalog=CATALOG)
    known = set(CATALOG.canonical_names(EntityCategory.VEHICLE))

    assert set(pipeline.suggested_models()) <= known


@pytest.mark.asyncio
async def test_intent_hint_never_invents_a_label_outside_the_existing_enum() -> None:
    """`intent_hint` là GỢI Ý cho `Intent` hiện có, không phải tập nhãn thứ hai.

    Nguồn sự thật của `state["intents"]` vẫn là `reconcile_intents`; hai bộ cùng
    sinh nhãn thì chúng phải nói cùng một ngôn ngữ, nếu không việc so sánh chúng
    ở downstream trở thành vô nghĩa.
    """

    valid = {member.value for member in Intent}
    pipeline = _pipeline(SpyRewriter())

    for message in ("VF5 giá bao nhiêu", "cho tôi xem các xe máy điện"):
        decision = await pipeline.recognize(user_message=message)

        assert decision.classification.intent_hint in valid
        assert {item.intent for item in decision.classification.candidates} <= valid


@pytest.mark.asyncio
async def test_a_bare_advisory_opening_yields_no_intent_hint() -> None:
    """Ghi lại một mất mát ĐÃ BIẾT, không phải hành vi mong muốn.

    "tư vấn" nằm trong `OVERVIEW_KEYWORDS` (`domain/vehicle_overview.py`), mà bảng
    đó cũng là nguồn sinh alias thuộc tính của Lớp 2. Nên câu trần "tôi cần tư vấn"
    khớp ATTRIBUTE:OVERVIEW và át mất INTENT_KEYWORD:ADVISORY — Lớp 3 không còn
    gợi ý nào để đưa ra.

    `None` vẫn TÔN TRỌNG hợp đồng của `test_intent_hint_never_invents_a_label...`:
    không có nhãn bịa nào được sinh ra, chỉ là không có nhãn nào cả. Test này giữ
    sự thật đó ở chỗ nhìn thấy được, thay vì nới lỏng assertion kia thành
    "in valid or None" và để mất mát trôi qua im lặng.

    Muốn lấy lại gợi ý ADVISORY thì phải tách "tư vấn" khỏi `FIELD_KEYWORDS` —
    xem `OVERVIEW_ONLY_KEYWORDS` trong lịch sử git.
    """

    pipeline = _pipeline(SpyRewriter())

    decision = await pipeline.recognize(user_message="tôi cần tư vấn")

    assert decision.classification.intent_hint is None
