"""Contract tests for A5-7 need-based feature introductions."""

from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.feature_introduction import (
    FeatureIntroductionRecord,
    derive_need_tags,
    select_feature_introductions,
)
from src.agents.domain.values import SlotName

VEHICLE_1 = UUID("00000000-0000-0000-0000-000000000301")
VEHICLE_2 = UUID("00000000-0000-0000-0000-000000000302")


def _record(
    vehicle_id: UUID,
    feature_code: str,
    *,
    need_tag: str = "LONG_DISTANCE",
    relevance: str = "0.80",
    flag_status: str = "YES",
    verification_status: str = "APPROVED",
    feature_status: str = "ACTIVE",
    display_order: int = 10,
) -> FeatureIntroductionRecord:
    return FeatureIntroductionRecord(
        vehicle_id=vehicle_id,
        feature_code=feature_code,
        feature_name=feature_code.replace("_", " ").title(),
        need_tag=need_tag,
        relevance=Decimal(relevance),
        flag_status=flag_status,
        verification_status=verification_status,
        feature_status=feature_status,
        display_order=display_order,
        evidence_ref=f"vehicle_feature_flags:{vehicle_id}:{feature_code}",
    )


def _select(
    records: list[FeatureIntroductionRecord],
    *,
    asked: set[str] | None = None,
    maximum: int = 2,
):
    return select_feature_introductions(
        ranked_vehicle_ids=[VEHICLE_1, VEHICLE_2],
        confirmed_need_tags={"LONG_DISTANCE"},
        records=records,
        customer_asked_feature_codes=asked or set(),
        max_introductions=maximum,
    )


def test_no_eligible_feature_returns_empty_without_generic_fallback() -> None:
    assert _select([]) == []


def test_feature_customer_already_asked_is_not_introduced() -> None:
    result = _select(
        [_record(VEHICLE_1, "ADAS_LEVEL_2")],
        asked={"ADAS_LEVEL_2"},
    )

    assert result == []


def test_feature_present_on_every_ranked_candidate_is_removed() -> None:
    result = _select(
        [
            _record(VEHICLE_1, "ADAS_LEVEL_2"),
            _record(VEHICLE_2, "ADAS_LEVEL_2"),
            _record(VEHICLE_1, "POWER_ADJUST_SEAT", relevance="0.60"),
        ]
    )

    assert [item.feature_code for item in result] == ["POWER_ADJUST_SEAT"]


def test_unknown_flag_is_not_introduced() -> None:
    assert _select([_record(VEHICLE_1, "ADAS_LEVEL_2", flag_status="UNKNOWN")]) == []


def test_pending_flag_is_not_introduced() -> None:
    assert _select([_record(VEHICLE_1, "ADAS_LEVEL_2", verification_status="PENDING")]) == []


def test_no_flag_is_not_introduced() -> None:
    assert _select([_record(VEHICLE_1, "ADAS_LEVEL_2", flag_status="NO")]) == []


def test_archived_feature_definition_is_not_introduced() -> None:
    assert _select([_record(VEHICLE_1, "ADAS_LEVEL_2", feature_status="ARCHIVED")]) == []


def test_introductions_are_limited_and_ordered_by_rank_relevance_then_display_order() -> None:
    result = _select(
        [
            _record(VEHICLE_2, "SECOND_RANK_HIGH", relevance="1.00", display_order=1),
            _record(VEHICLE_1, "LOW", relevance="0.60", display_order=1),
            _record(VEHICLE_1, "HIGH_LATE", relevance="0.90", display_order=20),
            _record(VEHICLE_1, "HIGH_EARLY", relevance="0.90", display_order=2),
        ],
        maximum=2,
    )

    assert [(item.vehicle_id, item.feature_code) for item in result] == [
        (VEHICLE_1, "HIGH_EARLY"),
        (VEHICLE_1, "HIGH_LATE"),
    ]


def test_record_outside_ranked_candidates_is_rejected_instead_of_expanding_set() -> None:
    with pytest.raises(ValueError, match="outside ranked candidate set"):
        _select([_record(UUID(int=999), "ADAS_LEVEL_2")])


def test_need_tags_are_derived_deterministically_from_confirmed_slots() -> None:
    tags = derive_need_tags(
        {
            SlotName.REQUIRED_RANGE_KM: 160,
            SlotName.PASSENGER_COUNT: 7,
            SlotName.HOME_CHARGING: False,
            SlotName.PURPOSE: "kinh doanh",
            SlotName.BUDGET_MAX_VND: 400_000_000,
            SlotName.HABIT_NEED_TAGS: ["URBAN_TRAFFIC"],
        },
        lowest_price_tier_ceiling_vnd=Decimal("450000000"),
    )

    assert tags == (
        "LONG_DISTANCE",
        "URBAN_TRAFFIC",
        "HIGHWAY_SAFETY",
        "FAMILY_LARGE",
        "NO_HOME_CHARGING",
        "LOW_OPERATING_COST",
        "TIGHT_BUDGET",
    )


def test_delivery_purpose_as_natural_text_still_derives_the_need_tag() -> None:
    """Bug thật 2026-08-21: `purpose` trích xuất luôn là câu tự nhiên, không
    phải chuỗi snake_case đóng — "giao hàng" (có dấu cách) phải khớp được."""

    assert derive_need_tags({SlotName.PURPOSE: "giao hàng"}) == ("DELIVERY_USE",)


def test_persisted_purpose_bucket_wins_over_keyword_match_on_purpose_text() -> None:
    """T2: khi slot `PURPOSE_BUCKET` (LLM đóng gói) đã có, need tag phải theo
    bucket đó — không còn suy lại từ keyword-match trên `purpose` tự do."""

    assert derive_need_tags({SlotName.PURPOSE: "đi chợ", SlotName.PURPOSE_BUCKET: "delivery"}) == ("DELIVERY_USE",)


def test_unmapped_purpose_does_not_invent_a_need_tag() -> None:
    """Mục đích không khớp bucket nào có tag (family/work/personal) → không tự
    suy tag nào — chỉ SERVICE/DELIVERY mới có tag purpose-driven, theo thiết
    kế gốc; đây là hành vi giữ nguyên, không phải phần vừa sửa."""

    assert derive_need_tags({SlotName.PURPOSE: "đi phượt xuyên việt"}) == ()


def test_personal_purpose_alone_does_not_invent_need_tag() -> None:
    assert derive_need_tags({SlotName.PURPOSE: "cá nhân"}) == ()


def test_unknown_habit_need_tag_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown need_tag"):
        derive_need_tags({SlotName.HABIT_NEED_TAGS: ["MADE_UP_TAG"]})


def test_non_positive_introduction_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_introductions must be positive"):
        _select([_record(VEHICLE_1, "ADAS_LEVEL_2")], maximum=0)
