"""Deterministic, non-promotional feature introduction rules for A5-7."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, cast
from uuid import UUID

from src.agents.domain.slot_mapping import purpose_bucket_for
from src.agents.domain.values import PurposeBucket, SlotName, SlotValue

NeedTag = Literal[
    "LONG_DISTANCE",
    "URBAN_TRAFFIC",
    "HIGHWAY_SAFETY",
    "FAMILY_LARGE",
    "NO_HOME_CHARGING",
    "DELIVERY_USE",
    "LOW_OPERATING_COST",
    "TIGHT_BUDGET",
]
FlagStatus = Literal["YES", "NO", "UNKNOWN"]
VerificationStatus = Literal["PENDING", "APPROVED", "REJECTED"]
FeatureStatus = Literal["ACTIVE", "ARCHIVED"]

NEED_TAG_ORDER: tuple[NeedTag, ...] = (
    "LONG_DISTANCE",
    "URBAN_TRAFFIC",
    "HIGHWAY_SAFETY",
    "FAMILY_LARGE",
    "NO_HOME_CHARGING",
    "DELIVERY_USE",
    "LOW_OPERATING_COST",
    "TIGHT_BUDGET",
)
CLOSED_NEED_TAGS = frozenset(NEED_TAG_ORDER)


@dataclass(frozen=True, slots=True)
class FeatureIntroductionRecord:
    """Joined feature-definition, need-tag and vehicle-flag row from the source."""

    vehicle_id: UUID
    feature_code: str
    feature_name: str
    need_tag: str
    relevance: Decimal
    flag_status: str
    verification_status: str
    feature_status: str
    display_order: int
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.feature_code or not self.feature_name or not self.evidence_ref:
            raise ValueError("feature introduction fields must be non-empty")
        if self.need_tag not in CLOSED_NEED_TAGS:
            raise ValueError(f"unknown need_tag: {self.need_tag}")
        if not Decimal("0") < self.relevance <= Decimal("1"):
            raise ValueError("feature relevance must be in (0, 1]")
        if self.flag_status not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid feature flag status")
        if self.verification_status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError("invalid feature verification status")
        if self.feature_status not in {"ACTIVE", "ARCHIVED"}:
            raise ValueError("invalid feature definition status")
        if self.display_order < 0:
            raise ValueError("feature display_order must be non-negative")


@dataclass(frozen=True, slots=True)
class FeatureIntroduction:
    """One evidence-backed feature worth mentioning to the customer."""

    vehicle_id: UUID
    feature_code: str
    feature_name: str
    need_tag: str
    relevance: Decimal
    evidence_ref: str


def derive_need_tags(
    slots: Mapping[SlotName, SlotValue],
    *,
    lowest_price_tier_ceiling_vnd: Decimal | None = None,
) -> tuple[NeedTag, ...]:
    """Derive the closed need-tag set from confirmed slots, never free-form text.

    Bug thật 2026-08-21: trước đây so `purpose == "kinh_doanh"`/`"giao_hang"`
    (chuỗi snake_case đóng) — nhưng `purpose` trích xuất thật luôn là câu tự
    nhiên ("kinh doanh", "giao hàng", "phục vụ gia đình"...), nên hai điều
    kiện đó KHÔNG BAO GIỜ khớp, không riêng mục đích lạ. Dùng lại
    `purpose_bucket_for()` (T2: ưu tiên slot `PURPOSE_BUCKET` LLM đã đóng gói,
    rơi về keyword-match trên `purpose` khi lượt đó chưa có) thay vì so chuỗi
    tuyệt đối.
    """

    tags = set(_habit_need_tags(slots.get(SlotName.HABIT_NEED_TAGS)))
    distance = _numeric_slot(slots.get(SlotName.REQUIRED_RANGE_KM), "required_range_km")
    passengers = _numeric_slot(slots.get(SlotName.PASSENGER_COUNT), "passenger_count")
    budget = _numeric_slot(slots.get(SlotName.BUDGET_MAX_VND), "budget_max_vnd")
    purpose = _text_slot(slots.get(SlotName.PURPOSE), "purpose")
    bucket = purpose_bucket_for(slots) if purpose is not None else None
    home_charging = _boolean_slot(slots.get(SlotName.HOME_CHARGING), "home_charging")
    if distance is not None and distance >= Decimal("150"):
        tags.add("LONG_DISTANCE")
    if distance is not None and distance < Decimal("50"):
        tags.add("URBAN_TRAFFIC")
    if "LONG_DISTANCE" in tags or bucket is PurposeBucket.SERVICE:
        tags.add("HIGHWAY_SAFETY")
    if passengers is not None and passengers >= Decimal("6"):
        tags.add("FAMILY_LARGE")
    if home_charging is False:
        tags.add("NO_HOME_CHARGING")
    if bucket is PurposeBucket.DELIVERY:
        tags.add("DELIVERY_USE")
    if bucket is PurposeBucket.SERVICE:
        tags.add("LOW_OPERATING_COST")
    if _is_tight_budget(budget, lowest_price_tier_ceiling_vnd):
        tags.add("TIGHT_BUDGET")
    return tuple(tag for tag in NEED_TAG_ORDER if tag in tags)


def select_feature_introductions(
    *,
    ranked_vehicle_ids: Sequence[UUID],
    confirmed_need_tags: Collection[str],
    records: Sequence[FeatureIntroductionRecord],
    customer_asked_feature_codes: Collection[str],
    max_introductions: int = 2,
) -> list[FeatureIntroduction]:
    """Return only differentiating, approved YES features, with no generic fallback."""

    if max_introductions <= 0:
        raise ValueError("max_introductions must be positive")
    ranked_ids = tuple(ranked_vehicle_ids)
    _validate_ranked_ids(ranked_ids)
    ranked_set = set(ranked_ids)
    outside = {record.vehicle_id for record in records} - ranked_set
    if outside:
        raise ValueError("feature record is outside ranked candidate set")
    tags = _validated_tags(confirmed_need_tags)
    eligible = [record for record in records if _is_eligible(record, tags)]
    common_features = _common_features(eligible, ranked_set)
    asked = set(customer_asked_feature_codes)
    filtered = [
        record for record in eligible if record.feature_code not in asked and record.feature_code not in common_features
    ]
    rank = {vehicle_id: index for index, vehicle_id in enumerate(ranked_ids)}
    filtered.sort(
        key=lambda record: (
            rank[record.vehicle_id],
            -record.relevance,
            record.display_order,
            record.feature_code,
            record.need_tag,
        )
    )
    unique = _unique_vehicle_features(filtered)
    return [
        FeatureIntroduction(
            vehicle_id=record.vehicle_id,
            feature_code=record.feature_code,
            feature_name=record.feature_name,
            need_tag=record.need_tag,
            relevance=record.relevance,
            evidence_ref=record.evidence_ref,
        )
        for record in unique[:max_introductions]
    ]


def _habit_need_tags(value: SlotValue) -> tuple[NeedTag, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("habit_need_tags slot must be a list of strings")
    unknown = set(value) - CLOSED_NEED_TAGS
    if unknown:
        raise ValueError(f"unknown need_tag: {sorted(unknown)[0]}")
    return cast(tuple[NeedTag, ...], tuple(value))


def _numeric_slot(value: SlotValue, label: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, list):
        raise ValueError(f"{label} slot must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} slot must be numeric") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{label} slot must be a non-negative finite number")
    return parsed


def _text_slot(value: SlotValue, label: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{label} slot must be text")


def _boolean_slot(value: SlotValue, label: str) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"{label} slot must be boolean")


def _is_tight_budget(budget: Decimal | None, ceiling: Decimal | None) -> bool:
    if ceiling is None:
        return False
    if not ceiling.is_finite() or ceiling < 0:
        raise ValueError("lowest price tier ceiling must be a non-negative finite number")
    return budget is not None and budget <= ceiling


def _validate_ranked_ids(ranked_ids: tuple[UUID, ...]) -> None:
    if len(ranked_ids) not in {1, 2, 3}:
        raise ValueError("feature introduction requires one to three ranked candidates")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("ranked vehicle ids must be unique")


def _validated_tags(tags: Collection[str]) -> set[str]:
    unknown = set(tags) - CLOSED_NEED_TAGS
    if unknown:
        raise ValueError(f"unknown need_tag: {sorted(unknown)[0]}")
    return set(tags)


def _is_eligible(record: FeatureIntroductionRecord, tags: set[str]) -> bool:
    return bool(
        record.need_tag in tags
        and record.flag_status == "YES"
        and record.verification_status == "APPROVED"
        and record.feature_status == "ACTIVE"
    )


def _common_features(eligible: Sequence[FeatureIntroductionRecord], ranked_ids: set[UUID]) -> set[str]:
    vehicles_by_feature: dict[str, set[UUID]] = {}
    for record in eligible:
        vehicles_by_feature.setdefault(record.feature_code, set()).add(record.vehicle_id)
    return {feature_code for feature_code, vehicle_ids in vehicles_by_feature.items() if vehicle_ids == ranked_ids}


def _unique_vehicle_features(
    records: Sequence[FeatureIntroductionRecord],
) -> list[FeatureIntroductionRecord]:
    seen: set[tuple[UUID, str]] = set()
    unique: list[FeatureIntroductionRecord] = []
    for record in records:
        key = (record.vehicle_id, record.feature_code)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique
