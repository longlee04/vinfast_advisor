"""[A7-4] Quy tắc default-deny của cổng rủi ro báo giá.

Mỗi test dưới đây khoá một đường về phía `False` (auto-approve). Đó là hướng
nguy hiểm duy nhất của module này: chặn nhầm chỉ làm khách chờ, thả nhầm là để
agent tự hứa giá với khách.
"""

from __future__ import annotations

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.quote_risk import (
    CONFIDENCE_THRESHOLD,
    DeliveryAction,
    OutputKind,
    OutputRiskContext,
    OutputSource,
    QuoteEvaluation,
    QuoteRiskTier,
    classify_delivery,
    classify_tier,
    detect_risk_flags,
    is_near_threshold,
    is_quote_turn,
    legacy_requires_sync_hitl,
    requires_sync_hitl,
)

SAFE_FLAGS = {
    "is_personalized": False,
    "is_negotiated": False,
    "has_non_standard_offer": False,
    "has_financial_commitment": False,
}


def _standard_quote(**overrides) -> QuoteEvaluation:
    """Báo giá niêm yết sạch — điểm xuất phát duy nhất dẫn tới auto-approve."""

    payload = {
        **SAFE_FLAGS,
        "confidence_score": 1.0,
        "is_deterministic_standard": True,
    }
    payload.update(overrides)
    return QuoteEvaluation(**payload)


def test_deterministic_listed_price_is_auto_approved() -> None:
    """Giá niêm yết deterministic, không cờ rủi ro nào bật → không chặn."""

    assert requires_sync_hitl(_standard_quote()) is False


@pytest.mark.parametrize(
    "flag",
    ["is_personalized", "is_negotiated", "has_non_standard_offer", "has_financial_commitment"],
)
def test_any_single_risk_flag_forces_hitl(flag: str) -> None:
    """Một cờ rủi ro là đủ chặn, dù confidence cao và mọi cờ khác tắt."""

    assert requires_sync_hitl(_standard_quote(**{flag: True})) is True


def test_confidence_below_threshold_forces_hitl() -> None:
    """Dưới ngưỡng thì chặn, kể cả khi không cờ rủi ro nào bật."""

    assert requires_sync_hitl(_standard_quote(confidence_score=CONFIDENCE_THRESHOLD - 0.01)) is True


def test_confidence_exactly_at_threshold_is_allowed() -> None:
    """Ngưỡng là biên ĐƯỢC PHÉP (`>=`), không phải biên bị chặn."""

    assert requires_sync_hitl(_standard_quote(confidence_score=CONFIDENCE_THRESHOLD)) is False


def test_missing_confidence_forces_hitl() -> None:
    """Thiếu dữ liệu không bao giờ được biến thành auto-approve."""

    assert requires_sync_hitl(_standard_quote(confidence_score=None)) is True


@pytest.mark.parametrize("flag_value", [None])
@pytest.mark.parametrize(
    "flag",
    ["is_personalized", "is_negotiated", "has_non_standard_offer", "has_financial_commitment"],
)
def test_unknown_risk_flag_forces_hitl(flag: str, flag_value: None) -> None:
    """`None` là "chưa biết", và chưa biết thì không được đi qua."""

    assert requires_sync_hitl(_standard_quote(**{flag: flag_value})) is True


def test_missing_evaluation_forces_hitl() -> None:
    assert requires_sync_hitl(None) is True
    assert requires_sync_hitl(QuoteEvaluation.unknown()) is True


def test_non_deterministic_quote_forces_hitl() -> None:
    """Bản nháp qua LLM không còn là giá niêm yết thuần → luôn chặn."""

    assert requires_sync_hitl(_standard_quote(is_deterministic_standard=False)) is True


def test_verified_recommendation_is_delivered_with_async_audit() -> None:
    decision = classify_delivery(
        OutputRiskContext(
            output_kind=OutputKind.RECOMMENDATION,
            source_kinds={OutputSource.SNAPSHOT, OutputSource.CONSTRAINED_LLM},
            facts_verified=True,
            unresolved_entity_count=0,
            **SAFE_FLAGS,
        )
    )

    assert decision.action is DeliveryAction.DELIVER_WITH_AUDIT
    assert decision.tier is QuoteRiskTier.EVIDENCE_BACKED_AUTO
    assert decision.requires_hitl is False


def test_unverified_recommendation_remains_default_deny() -> None:
    decision = classify_delivery(
        OutputRiskContext(
            output_kind=OutputKind.RECOMMENDATION,
            source_kinds={OutputSource.CONSTRAINED_LLM},
            facts_verified=None,
            unresolved_entity_count=0,
            **SAFE_FLAGS,
        )
    )

    assert decision.action is DeliveryAction.SYNC_REVIEW
    assert decision.requires_hitl is True
    assert "facts_not_verified" in decision.reasons


def test_negotiation_is_a_business_handoff_not_draft_review() -> None:
    decision = classify_delivery(
        OutputRiskContext(
            output_kind=OutputKind.COMMERCIAL_REQUEST,
            source_kinds=set(),
            facts_verified=None,
            unresolved_entity_count=0,
            is_negotiated=True,
            is_personalized=False,
            has_non_standard_offer=False,
            has_financial_commitment=False,
        )
    )

    assert decision.action is DeliveryAction.ADVISOR_HANDOFF
    assert decision.tier is QuoteRiskTier.ADVISOR_HANDOFF
    assert decision.requires_hitl is True


def test_tco_estimate_keeps_synchronous_review() -> None:
    decision = classify_delivery(
        OutputRiskContext(
            output_kind=OutputKind.TCO_ESTIMATE,
            source_kinds={OutputSource.DETERMINISTIC_TOOL},
            facts_verified=True,
            unresolved_entity_count=0,
            **SAFE_FLAGS,
        )
    )

    assert decision.action is DeliveryAction.SYNC_REVIEW
    assert decision.tier is QuoteRiskTier.SYNC_HITL


@pytest.mark.parametrize("broken", [float("nan"), 1.5, -0.1, True])
def test_unusable_confidence_values_force_hitl(broken: object) -> None:
    """NaN, ngoài [0,1], hay một boolean lọt vào ô confidence đều là dữ liệu hỏng.

    `True` đáng chú ý nhất: `isinstance(True, int)` đúng trong Python, nên nếu
    không chặn tường minh thì nó được đọc thành 1.0 và mở thẳng cửa auto-approve.
    """

    evaluation = QuoteEvaluation(**SAFE_FLAGS, is_deterministic_standard=True)
    assert requires_sync_hitl(evaluation.model_copy(update={"confidence_score": broken})) is True


def test_corrupt_payload_degrades_to_maximum_risk() -> None:
    """Payload hỏng trả về bản `unknown()` chứ không raise giữa lượt của khách."""

    evaluation = QuoteEvaluation.from_raw({"confidence_score": "không phải số"})
    assert evaluation == QuoteEvaluation.unknown()
    assert requires_sync_hitl(evaluation) is True


def test_triggered_reasons_name_every_blocking_condition() -> None:
    evaluation = _standard_quote(is_negotiated=True, confidence_score=0.5)
    reasons = evaluation.triggered_reasons()
    assert "is_negotiated" in reasons
    assert "confidence_below_threshold" in reasons


# ── Nhận diện rủi ro từ lời khách ─────────────────────────────────────────────


def test_price_cut_request_is_detected_as_negotiation() -> None:
    assert (
        detect_risk_flags(
            user_message="anh giảm cho em 20 triệu được không",
            canonical=build_canonical_text("anh giảm cho em 20 triệu được không"),
        )["is_negotiated"]
        is True
    )


def test_plain_price_question_carries_no_risk_flag() -> None:
    assert (
        detect_risk_flags(user_message="giá xe VF3 bao nhiêu", canonical=build_canonical_text("giá xe VF3 bao nhiêu"))
        == SAFE_FLAGS
    )


@pytest.mark.parametrize(
    ("message", "flag"),
    [
        ("bên mình có khuyến mãi gì không ạ", "has_non_standard_offer"),
        ("em muốn trả góp thì lãi suất bao nhiêu", "has_financial_commitment"),
        ("chốt giá giúp em đi anh", "is_negotiated"),
    ],
)
def test_risk_vocabulary_maps_to_the_right_flag(message: str, flag: str) -> None:
    assert detect_risk_flags(user_message=message, canonical=build_canonical_text(message))[flag] is True


def test_an_on_road_price_question_is_no_longer_treated_as_personalised() -> None:
    """[A7-9] "Giá lăn bánh" từng bị xếp là cá nhân hoá nên luôn chặn chờ duyệt.

    Đã gỡ: nó được tính bằng công thức cố định trên biểu phí đã công bố, tức
    deterministic đúng như giá niêm yết — không phải con số ai đó thương lượng
    riêng. Điều kiện đổi lại là phải đủ slot (`domain/pricing_intent.py`): thiếu
    tỉnh thì HỎI, không phải đoán rồi chặn.
    """

    assert (
        detect_risk_flags(
            user_message="báo em giá lăn bánh ở Hà Nội với",
            canonical=build_canonical_text("báo em giá lăn bánh ở Hà Nội với"),
        )
        == SAFE_FLAGS
    )
    # Nhưng vừa hỏi vừa mặc cả thì vẫn phải chặn.
    assert (
        detect_risk_flags(
            user_message="giá lăn bánh giảm cho em được không",
            canonical=build_canonical_text("giá lăn bánh giảm cho em được không"),
        )["is_negotiated"]
        is True
    )


def test_promotion_on_the_approved_list_is_not_off_policy() -> None:
    """Ưu đãi nằm trong bảng đã duyệt thì không phải "ngoài chính sách chuẩn"."""

    flags = detect_risk_flags(
        user_message="cho em hỏi ưu đãi tháng vàng còn không",
        canonical=build_canonical_text("cho em hỏi ưu đãi tháng vàng còn không"),
        standard_promotions=frozenset({"ưu đãi tháng vàng"}),
    )
    assert flags["has_non_standard_offer"] is False


# ── Tier: cái gì mới được coi là "báo giá" ────────────────────────────────────


def test_spec_lookup_without_price_is_not_a_quote() -> None:
    """Tra thông số/tồn kho/so sánh xe không áp chính sách báo giá."""

    assert is_quote_turn(priced_fact_count=0, risk_flags=SAFE_FLAGS) is False
    assert classify_tier(None, is_quote=False) is QuoteRiskTier.NON_QUOTE


def test_priced_catalog_answer_is_a_quote() -> None:
    assert is_quote_turn(priced_fact_count=1, risk_flags=SAFE_FLAGS) is True
    assert classify_tier(_standard_quote(), is_quote=True) is QuoteRiskTier.DETERMINISTIC_AUTO


def test_risk_wording_makes_a_priceless_turn_a_quote() -> None:
    """Mặc cả mà không kèm tên xe vẫn là chuyện báo giá, phải đánh giá như báo giá."""

    flags = detect_risk_flags(
        user_message="giảm cho em 20 triệu nhé", canonical=build_canonical_text("giảm cho em 20 triệu nhé")
    )
    assert is_quote_turn(priced_fact_count=0, risk_flags=flags) is True


# ── Dữ liệu để tune ngưỡng và so sánh shadow-mode ─────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.84, True), (0.75, True), (0.749, False), (0.85, False), (None, False)],
)
def test_near_threshold_band_is_half_open(score: float | None, expected: bool) -> None:
    """`[THRESHOLD - MARGIN, THRESHOLD)` — trên ngưỡng thì đã auto, không cần tune."""

    assert is_near_threshold(score) is expected


def test_legacy_policy_blocks_every_data_touching_turn() -> None:
    assert legacy_requires_sync_hitl(touched_catalog=True) is True
    assert legacy_requires_sync_hitl(touched_catalog=False) is False
