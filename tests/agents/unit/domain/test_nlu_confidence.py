from __future__ import annotations

from src.agents.domain.entity_catalog import EntityCategory
from src.agents.domain.fuzzy_match import EntityMatch
from src.agents.domain.nlu_confidence import (
    ConfidenceThresholds,
    NluClassification,
    NluTier,
    advisory_flow_active,
    classify_intent,
    route_confidence,
)
from src.agents.domain.values import DECLINED_SLOT_VALUE, Intent
from src.agents.domain.vehicle_overview import VehicleAttribute

THRESHOLDS = ConfidenceThresholds()


def _match(
    category: EntityCategory,
    canonical: str,
    score: float = 100.0,
    matched_on: str = "original",
    is_weak: bool = False,
) -> EntityMatch:
    return EntityMatch(
        category=category,
        canonical=canonical,
        matched_alias=canonical.casefold(),
        score=score,
        source_span=canonical.casefold(),
        matched_on=matched_on,  # type: ignore[arg-type]
        is_weak=is_weak,
    )


# ── Lớp 3: phân loại có căn cứ ────────────────────────────────────────────────


def test_a_named_model_points_at_catalog_lookup() -> None:
    result = classify_intent(entities=[_match(EntityCategory.VEHICLE, "VF 5")])

    assert result.intent_hint == Intent.CATALOG_LOOKUP.value
    assert result.vehicle_names == ("VF 5",)


def test_every_conclusion_carries_the_evidence_that_produced_it() -> None:
    """Nhãn sai phải truy được về đúng entity gây ra nó, không phải đoán."""

    result = classify_intent(
        entities=[
            _match(EntityCategory.VEHICLE, "VF 5"),
            _match(EntityCategory.ATTRIBUTE, VehicleAttribute.PRICE.value),
        ]
    )

    assert {item.canonical for item in result.evidence} == {"VF 5", "PRICE"}


def test_a_model_name_outranks_a_type_name() -> None:
    """[A4-7] "VF 5 với các ô tô khác thì sao" phải trả bảng của VF 5."""

    result = classify_intent(
        entities=[
            _match(EntityCategory.VEHICLE, "VF 5"),
            _match(EntityCategory.INTENT_KEYWORD, Intent.CATALOG_BROWSE.value),
        ]
    )

    assert result.intent_hint == Intent.CATALOG_LOOKUP.value


def test_a_type_name_alone_points_at_browse() -> None:
    result = classify_intent(entities=[_match(EntityCategory.INTENT_KEYWORD, Intent.CATALOG_BROWSE.value)])

    assert result.intent_hint == Intent.CATALOG_BROWSE.value


def test_no_entity_means_no_intent_and_no_confidence() -> None:
    result = classify_intent(entities=[])

    assert result.intent_hint is None
    assert result.confidence == 0.0


def test_weak_candidates_alone_do_not_produce_an_intent() -> None:
    result = classify_intent(entities=[_match(EntityCategory.VEHICLE, "VF 5", score=72.0, is_weak=True)])

    assert result.intent_hint is None


def test_confidence_drops_when_the_rewrite_is_uncertain() -> None:
    entities = [_match(EntityCategory.VEHICLE, "VF 5")]

    confident = classify_intent(entities=entities, rewrite_trust=1.0)
    unsure = classify_intent(entities=entities, rewrite_trust=0.7)

    assert unsure.confidence < confident.confidence


def test_evidence_found_only_after_rewriting_is_penalised() -> None:
    """Kết luận đứng trên suy đoán của mô hình, không trên chữ khách đã viết."""

    from_original = classify_intent(entities=[_match(EntityCategory.VEHICLE, "VF 5", matched_on="original")])
    from_rewrite = classify_intent(entities=[_match(EntityCategory.VEHICLE, "VF 5", matched_on="rewritten")])

    assert from_rewrite.confidence < from_original.confidence


# ── Lớp 3: tương thích ngược với pending-slot (A7-10) ─────────────────────────


def test_a_pending_slot_takes_absolute_priority() -> None:
    """Lượt đang trả lời câu hỏi slot không được phân loại lại như tin nhắn mới.

    Đó chính là con bug A7-10 sinh ra để sửa, chỉ khác chỗ phát sinh.
    """

    result = classify_intent(entities=[], pending_slot="province", pending_intent="ON_ROAD_PRICE_LOOKUP")

    assert result.resolved_via_pending_slot is True
    assert result.confidence == 1.0
    assert result.intent_hint == "ON_ROAD_PRICE_LOOKUP"
    assert route_confidence(result, THRESHOLDS) is NluTier.AUTO


# ── Lớp 4: định tuyến ─────────────────────────────────────────────────────────


def test_thresholds_split_the_three_tiers() -> None:
    assert THRESHOLDS.tier_for(0.90) is NluTier.AUTO
    assert THRESHOLDS.tier_for(0.85) is NluTier.AUTO
    assert THRESHOLDS.tier_for(0.70) is NluTier.CONFIRM
    assert THRESHOLDS.tier_for(0.60) is NluTier.CONFIRM
    assert THRESHOLDS.tier_for(0.59) is NluTier.CLARIFY


def test_a_clean_message_is_never_hijacked_by_a_clarifying_question() -> None:
    """Bốn lớp này chỉ cứu input BỊ NHIỄU.

    Câu sạch không khớp entity nào ("chào em", "tôi muốn mua xe") đã có
    `classify_scope` và `extract_slots` xử lý bằng LLM, tốt hơn hẳn một bảng
    keyword tĩnh. Bỏ guard này thì câu chào đầu tiên của mọi hội thoại nhận về
    "em chưa nắm rõ ý anh/chị".
    """

    unrecognised = classify_intent(entities=[])

    assert route_confidence(unrecognised, THRESHOLDS, input_looks_noisy=False) is NluTier.AUTO
    assert route_confidence(unrecognised, THRESHOLDS, input_looks_noisy=True) is NluTier.CLARIFY


def test_an_active_handoff_silences_the_bot() -> None:
    """PENDING_HANDOFF: khách vừa được báo "đã chuyển tư vấn viên" mà lại nhận
    "ý anh/chị là gì ạ?" thì hai câu phủ định nhau, và câu sau xoá câu trước."""

    unrecognised = classify_intent(entities=[])

    assert route_confidence(unrecognised, THRESHOLDS, handoff_active=True) is NluTier.AUTO


def test_an_active_advisory_flow_silences_the_bot() -> None:
    """Bot hỏi ngân sách, khách đáp "700 triệu" — câu đó không khớp entity nào."""

    unrecognised = classify_intent(entities=[])

    assert route_confidence(unrecognised, THRESHOLDS, slot_flow_active=True) is NluTier.AUTO


# ── Guard "đang giữa cuộc tư vấn" ─────────────────────────────────────────────


def test_advisory_flow_is_active_once_a_real_slot_is_filled() -> None:
    assert advisory_flow_active({"budget_max_vnd": 700_000_000}) is True
    assert advisory_flow_active({"passenger_count": 5}) is True


def test_a_declined_slot_does_not_count_as_an_active_flow() -> None:
    """`DECLINED_SLOT_VALUE` đánh dấu một ô đã đóng, không phải thông tin thu được."""

    assert advisory_flow_active({"purpose": DECLINED_SLOT_VALUE}) is False


def test_unknown_or_empty_slots_never_break_the_guard() -> None:
    assert advisory_flow_active(None) is False
    assert advisory_flow_active({}) is False
    assert advisory_flow_active({"khong_phai_slot": "x"}) is False
    assert advisory_flow_active({"vehicle_type": "CAR"}) is False


def test_a_recognised_but_shaky_intent_is_confirmed_even_on_clean_input() -> None:
    """Đây là chỗ ngưỡng tin cậy thật sự làm việc, và nó từng bị tắt hoàn toàn.

    Lối tắt cũ `not input_looks_noisy → AUTO` khiến MỌI câu gõ sạch đi thẳng,
    nên ngưỡng `0.85/0.60` chỉ áp cho câu gõ hỏng. Một câu sạch mà bộ khớp chỉ
    nhận ra được lờ mờ ("vf ba") đúng là ca đáng hỏi lại nhất: hệ ĐÃ hiểu một ý
    định, chỉ chưa chắc — khác hẳn ca không hiểu gì.
    """

    shaky = NluClassification(intent_hint="CATALOG_LOOKUP", confidence=0.70)

    assert route_confidence(shaky, THRESHOLDS, input_looks_noisy=False) is NluTier.CONFIRM


def test_a_recognised_but_shaky_intent_is_confirmed_mid_advisory_too() -> None:
    """Lối tắt `slot_flow_active` cũng từng nuốt cả nhánh hỏi lại.

    Nó sinh ra để cứu câu trả lời TRẦN ("700 triệu") — câu không khớp entity
    nào. Câu đó vẫn được cứu bằng nhánh "không hiểu gì" ở dưới. Nhưng một câu
    giữa cuộc tư vấn mà hệ đọc ra được một ý định lờ mờ thì vẫn phải hỏi lại.
    """

    shaky = NluClassification(intent_hint="COMPARE_VEHICLES", confidence=0.65)

    assert route_confidence(shaky, THRESHOLDS, slot_flow_active=True) is NluTier.CONFIRM


def test_a_confident_intent_still_goes_straight_through() -> None:
    confident = NluClassification(intent_hint="CATALOG_LOOKUP", confidence=0.92)

    assert route_confidence(confident, THRESHOLDS, input_looks_noisy=False) is NluTier.AUTO


def test_an_active_handoff_still_wins_over_a_shaky_intent() -> None:
    """Khách đang chờ NGƯỜI thì bot không chen câu hỏi nào, kể cả câu xác nhận."""

    shaky = NluClassification(intent_hint="CATALOG_LOOKUP", confidence=0.10)

    assert route_confidence(shaky, THRESHOLDS, handoff_active=True) is NluTier.AUTO
