"""Snapshot-backed application service for A5-3 recommendations."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from src.agents.contracts import Recommendation, ScoreInput
from src.agents.domain.comparison import (
    ComparisonAssertion,
    ComparisonCandidate,
    ComparisonCell,
    ComparisonFact,
    ComparisonTable,
    compare_candidates,
    structured_fact_cell,
)
from src.agents.domain.feature_introduction import (
    FeatureIntroduction,
    FeatureIntroductionRecord,
    derive_need_tags,
    select_feature_introductions,
)
from src.agents.domain.scoring import (
    NeedTagLink,
    RankedCandidate,
    ScoringAssertion,
    ScoringCandidate,
    ScoringProfile,
    rank_candidates,
)
from src.agents.domain.values import SlotName, SlotValue, VehicleType, is_declined
from src.agents.ports import UnitOfWorkPort
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS, FEATURE_LABELS
from src.agents.services.snapshotting import (
    RunSnapshotEnvelope,
    SnapshotCandidate,
    SnapshotFeatureAssertion,
)

NEED_TAG_FACT_PREFIX = "NEED_TAG::"


@dataclass(frozen=True, slots=True)
class RunScoringContext:
    """Immutable run snapshot paired with the confirmed slots for that run."""

    snapshot: RunSnapshotEnvelope
    slots: Mapping[SlotName, SlotValue]
    lowest_price_tier_ceiling_vnd: Decimal | None = None


class RecommendationDataSource(Protocol):
    """Load frozen scoring input without exposing persistence to the domain."""

    async def load(self, run_id: UUID) -> RunScoringContext | None: ...


class FeatureIntroductionSource(Protocol):
    """Load joined feature rows for ranked vehicles and confirmed need tags."""

    async def load(
        self, *, vehicle_ids: tuple[UUID, ...], need_tags: tuple[str, ...]
    ) -> Sequence[FeatureIntroductionRecord]: ...


class DefaultRecommendationService:
    """Convert one frozen run context into ranked public recommendations."""

    def __init__(
        self,
        *,
        source: RecommendationDataSource,
        feature_introduction_source: FeatureIntroductionSource | None = None,
        unit_of_work: UnitOfWorkPort | None = None,
    ) -> None:
        self._source = source
        self._feature_introduction_source = feature_introduction_source
        self._unit_of_work = unit_of_work

    async def recommend(
        self,
        run_id: UUID,
        *,
        customer_asked_feature_codes: Collection[str] = (),
        preferred_trait_codes: Collection[str] = (),
        budget_relaxed: bool = False,
        vehicle_type: str | None = None,
    ) -> list[Recommendation]:
        """Rank from snapshot only; never re-read mutable catalog records.

        `customer_asked_feature_codes` (Sếp 2026-08-21): mã tính năng khách
        vừa xác nhận quan tâm ở lượt 2 — xe có tính năng đó (FLAG đã duyệt)
        được thêm lý do, để câu đề xuất cuối có căn cứ nhắc lại đúng điều
        khách vừa nói, thay vì bị luật synthesis chặn vì thiếu claim.

        `vehicle_type` (bug prod 15:20:30): `context.slots` đọc từ
        `conversation_slots` — bảng CHỈ có slot đã CHỐT ở lượt trước, còn
        `VEHICLE_TYPE` suy từ ngân sách trong lượt này (`act.infer_vehicle_type`)
        chưa kịp ghi xuống. Không có tham số này, `_profile_from_slots` đọc
        slot rỗng và ném `ValueError` ngay bộ ứng viên đầu tiên. Người gọi
        (`act._recommend`) LUÔN truyền giá trị đã suy; tham số optional chỉ để
        không phá caller cũ (test node/chain) chưa cập nhật.
        """

        context = await self._source.load(run_id)
        if context is None:
            return []
        profile = _profile_from_slots(
            context.slots,
            feature_mentions=customer_asked_feature_codes,
            preferred_traits=preferred_trait_codes,
            budget_relaxed=budget_relaxed,
            vehicle_type_override=vehicle_type,
        )
        assertions = _assertions_by_vehicle(context.snapshot.assertions)
        candidates = [
            _candidate_from_snapshot(candidate, assertions.get(candidate.vehicle_id, ()))
            for candidate in context.snapshot.candidates
        ]
        names_by_vehicle = {candidate.vehicle_id: candidate.model_name for candidate in context.snapshot.candidates}
        ranked = rank_candidates(profile, candidates)
        recommendations = [
            Recommendation(
                vehicle_id=item.vehicle_id,
                rank=rank,
                reasons=[reason.render() for reason in item.reasons],
                display_name=names_by_vehicle.get(item.vehicle_id, ""),
                over_budget_percent=(float(item.over_budget_percent) if item.over_budget_percent is not None else None),
            )
            for rank, item in enumerate(ranked, start=1)
        ]
        await self._persist(run_id, ranked, recommendations)
        return recommendations

    async def _persist(
        self,
        run_id: UUID,
        ranked: Sequence[RankedCandidate],
        recommendations: Sequence[Recommendation],
    ) -> None:
        """Lưu điểm và thứ hạng; không có unit_of_work thì bỏ qua (test fake).

        Ghi ở service chứ không ở `ScoreNode`: node bị giới hạn 15 câu lệnh và
        cấm chạm adapter (mục 6.5/6.5b), còn ở đây đã có sẵn cả điểm lẫn lý do.
        """

        if self._unit_of_work is None or not ranked:
            return
        scores = [
            ScoreInput(vehicle_id=item.vehicle_id, score=item.score, reasons=tuple(rec.reasons))
            for item, rec in zip(ranked, recommendations, strict=True)
        ]
        async with self._unit_of_work.transaction() as transaction:
            await transaction.runs.save_scores(run_id, scores)
            await transaction.runs.set_candidate_ranks(run_id, {rec.vehicle_id: rec.rank for rec in recommendations})

    async def compare(self, *, run_id: UUID, vehicle_ids: Sequence[UUID]) -> ComparisonTable:
        """Build a same-type comparison from one immutable run snapshot."""

        context = await self._load_required_context(run_id)
        selected = _select_snapshot_candidates(context.snapshot, vehicle_ids)
        assertions = _assertions_by_vehicle(context.snapshot.assertions)
        candidates = tuple(
            _comparison_candidate(candidate, assertions.get(candidate.vehicle_id, ())) for candidate in selected
        )
        return compare_candidates(candidates, captured_at=context.snapshot.captured_at)

    async def lookup_fact(self, *, run_id: UUID, vehicle_id: UUID, fact_code: str) -> ComparisonCell | None:
        """Read one fact through the same snapshot path used by comparison."""

        context = await self._load_required_context(run_id)
        candidate = next(
            (item for item in context.snapshot.candidates if item.vehicle_id == vehicle_id),
            None,
        )
        if candidate is None:
            return None
        fact = next((item for item in candidate.facts if item.fact_code == fact_code), None)
        if fact is None:
            return None
        return structured_fact_cell(
            vehicle_id,
            ComparisonFact(
                fact_code=fact.fact_code,
                value_text=fact.value_text,
                source_table=fact.source_table,
                source_id=fact.source_id,
            ),
        )

    async def introduce_features(
        self,
        *,
        run_id: UUID,
        recommendations: Sequence[Recommendation],
        customer_asked_feature_codes: Collection[str],
        max_introductions: int = 2,
    ) -> list[FeatureIntroduction]:
        """Select evidence-backed introductions without promotional fallback text."""

        context = await self._load_required_context(run_id)
        ranked = tuple(sorted(recommendations, key=lambda item: item.rank))
        vehicle_ids = tuple(item.vehicle_id for item in ranked)
        _ensure_ranked_candidates_are_in_snapshot(context.snapshot, vehicle_ids)
        need_tags = derive_need_tags(
            context.slots,
            lowest_price_tier_ceiling_vnd=context.lowest_price_tier_ceiling_vnd,
        )
        if not need_tags:
            return []
        if self._feature_introduction_source is None:
            raise ValueError("feature introduction source is not configured")
        records = await self._feature_introduction_source.load(vehicle_ids=vehicle_ids, need_tags=need_tags)
        return select_feature_introductions(
            ranked_vehicle_ids=vehicle_ids,
            confirmed_need_tags=need_tags,
            records=records,
            customer_asked_feature_codes=customer_asked_feature_codes,
            max_introductions=max_introductions,
        )

    async def _load_required_context(self, run_id: UUID) -> RunScoringContext:
        context = await self._source.load(run_id)
        if context is None:
            raise ValueError("run snapshot not found")
        return context


def _profile_from_slots(
    slots: Mapping[SlotName, SlotValue],
    *,
    feature_mentions: Collection[str] = (),
    preferred_traits: Collection[str] = (),
    budget_relaxed: bool = False,
    vehicle_type_override: str | None = None,
) -> ScoringProfile:
    #: Ưu tiên giá trị caller vừa suy (`act.infer_vehicle_type`) — slot đã CHỐT
    #: trong `conversation_slots` chỉ theo kịp từ lượt SAU. Không có override
    #: thì rơi về slot cũ, giữ đúng hành vi trước đây cho caller chưa cập nhật.
    vehicle_type_value = vehicle_type_override if vehicle_type_override is not None else slots.get(SlotName.VEHICLE_TYPE)
    try:
        vehicle_type = VehicleType(str(vehicle_type_value))
    except ValueError as error:
        raise ValueError("vehicle_type slot is required and must be valid") from error
    return ScoringProfile(
        vehicle_type=vehicle_type,
        # Lớp 1 đã BỎ trần giá (không mẫu nào đủ N chỗ trong ngân sách) thì
        # xếp hạng không được loại lại theo đúng trần đó — nếu không mọi bậc nới
        # lỏng đều vô nghĩa và khách nhận "chưa tìm thấy mẫu xe" (prod
        # 2026-08-27: "300 triệu, 5 người, đi làm" lặp 5 lần). Nhãn "cao hơn
        # ngân sách" vẫn được gắn ở tầng viết bài vì tầng đó đọc slot gốc.
        budget_max_vnd=(
            None if budget_relaxed else _slot_decimal(slots.get(SlotName.BUDGET_MAX_VND), "budget_max_vnd")
        ),
        budget_min_vnd=_slot_decimal(slots.get(SlotName.BUDGET_MIN_VND), "budget_min_vnd"),
        passenger_count=_slot_int(slots.get(SlotName.PASSENGER_COUNT), "passenger_count"),
        required_range_km=_slot_int(slots.get(SlotName.REQUIRED_RANGE_KM), "required_range_km"),
        home_charging=_slot_bool(slots.get(SlotName.HOME_CHARGING), "home_charging"),
        purpose=_slot_text(slots.get(SlotName.PURPOSE), "purpose"),
        max_load_kg=_slot_int(slots.get(SlotName.MAX_LOAD_KG), "max_load_kg"),
        habit_need_tags=_slot_tags(slots.get(SlotName.HABIT_NEED_TAGS)),
        feature_mentions=tuple(dict.fromkeys(feature_mentions)),
        # Dự phòng `FEATURE_DISPLAY_LABELS` (28 mã) chứ không chỉ `FEATURE_LABELS`
        # (6 mã hỏi được lượt 2). Bug thật 2026-08-26, thấy khi chạy hội thoại
        # thật trên prod: khách chọn "cảnh báo điểm mù" — mã ngoài sáu mã kia —
        # nên `_feature_mention_reasons` rơi về fallback in MÃ THÔ, và pitch gửi
        # khách đọc "có đúng BLIND_SPOT_MONITOR mà Quý khách vừa xác nhận quan tâm".
        feature_mention_labels={
            code: FEATURE_LABELS.get(code) or FEATURE_DISPLAY_LABELS[code]
            for code in feature_mentions
            if code in FEATURE_LABELS or code in FEATURE_DISPLAY_LABELS
        },
        # Nhãn của TOÀN BỘ danh mục, không lọc theo lượt hội thoại: `scoring.
        # _feature_showcase_reasons` dùng nó để kể cả những tính năng khách chưa
        # hỏi tới. Lọc ở đây là dựng lại đúng cái bộ lọc đang cần gỡ.
        feature_labels=FEATURE_DISPLAY_LABELS,
        preferred_traits=tuple(dict.fromkeys(preferred_traits)),
    )


def _candidate_from_snapshot(
    candidate: SnapshotCandidate,
    assertions: tuple[SnapshotFeatureAssertion, ...],
) -> ScoringCandidate:
    facts = {fact.fact_code: fact.value_text for fact in candidate.facts}
    vehicle_type_text = facts.get("VEHICLE_TYPE")
    if vehicle_type_text is None:
        raise ValueError("VEHICLE_TYPE must be present and valid")
    try:
        vehicle_type = VehicleType(vehicle_type_text)
    except ValueError as error:
        raise ValueError("VEHICLE_TYPE must be present and valid") from error
    return ScoringCandidate(
        vehicle_id=candidate.vehicle_id,
        vehicle_type=vehicle_type,
        price_vnd=_fact_decimal(facts, "STARTING_PRICE_VND"),
        range_km=_first_fact_decimal(facts, ("CAR_RANGE_KM", "MOTORBIKE_RANGE_MAX_KM")),
        seat_count=_fact_int(facts, "CAR_SEAT_COUNT"),
        max_load_kg=_fact_decimal(facts, "MOTORBIKE_MAX_LOAD_KG"),
        cargo_volume_l=_fact_decimal(facts, "CARGO_VOLUME_STANDARD_L"),
        energy_consumption_per_100km=_fact_decimal(facts, "ENERGY_CONSUMPTION_KWH_PER_100KM"),
        home_charge_time_minutes=_fact_decimal(facts, "HOME_CHARGE_TIME_MINUTES"),
        battery_removable=_fact_bool(facts, "BATTERY_REMOVABLE"),
        battery_swappable=_fact_bool(facts, "BATTERY_SWAPPABLE"),
        over_budget_percent=_fact_decimal(facts, "OVER_BUDGET_PERCENT"),
        assertions=tuple(
            ScoringAssertion(
                feature_code=assertion.feature_code,
                status=assertion.status,
                source=assertion.source,
                evidence_ref=assertion.evidence_ref,
            )
            for assertion in assertions
        ),
        need_tag_links=_need_tag_links(facts),
    )


def _assertions_by_vehicle(
    assertions: tuple[SnapshotFeatureAssertion, ...],
) -> dict[UUID, tuple[SnapshotFeatureAssertion, ...]]:
    grouped: dict[UUID, list[SnapshotFeatureAssertion]] = {}
    for assertion in assertions:
        grouped.setdefault(assertion.vehicle_id, []).append(assertion)
    return {vehicle_id: tuple(values) for vehicle_id, values in grouped.items()}


def _select_snapshot_candidates(
    snapshot: RunSnapshotEnvelope, vehicle_ids: Sequence[UUID]
) -> tuple[SnapshotCandidate, ...]:
    requested = tuple(vehicle_ids)
    by_id = {candidate.vehicle_id: candidate for candidate in snapshot.candidates}
    if any(vehicle_id not in by_id for vehicle_id in requested):
        raise ValueError("comparison vehicle is outside run snapshot")
    return tuple(by_id[vehicle_id] for vehicle_id in requested)


def _ensure_ranked_candidates_are_in_snapshot(snapshot: RunSnapshotEnvelope, vehicle_ids: tuple[UUID, ...]) -> None:
    snapshot_ids = {candidate.vehicle_id for candidate in snapshot.candidates}
    if any(vehicle_id not in snapshot_ids for vehicle_id in vehicle_ids):
        raise ValueError("ranked vehicle is outside run snapshot")


def _comparison_candidate(
    candidate: SnapshotCandidate,
    assertions: tuple[SnapshotFeatureAssertion, ...],
) -> ComparisonCandidate:
    vehicle_type_fact = next((fact for fact in candidate.facts if fact.fact_code == "VEHICLE_TYPE"), None)
    if vehicle_type_fact is None:
        raise ValueError("VEHICLE_TYPE must be present and valid")
    try:
        vehicle_type = VehicleType(vehicle_type_fact.value_text)
    except ValueError as error:
        raise ValueError("VEHICLE_TYPE must be present and valid") from error
    return ComparisonCandidate(
        vehicle_id=candidate.vehicle_id,
        vehicle_type=vehicle_type,
        model_name=candidate.model_name,
        facts=tuple(
            ComparisonFact(
                fact_code=fact.fact_code,
                value_text=fact.value_text,
                source_table=fact.source_table,
                source_id=fact.source_id,
            )
            for fact in candidate.facts
            if fact.fact_code != "VEHICLE_TYPE"
        ),
        assertions=tuple(
            ComparisonAssertion(
                feature_code=assertion.feature_code,
                status=assertion.status,
                source=assertion.source,
                evidence_ref=assertion.evidence_ref,
            )
            for assertion in assertions
        ),
    )


def _need_tag_links(facts: Mapping[str, str]) -> tuple[NeedTagLink, ...]:
    links: list[NeedTagLink] = []
    for code, value in facts.items():
        if not code.startswith(NEED_TAG_FACT_PREFIX):
            continue
        parts = code.split("::")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise ValueError(f"invalid need-tag snapshot fact code: {code}")
        links.append(
            NeedTagLink(
                need_tag=parts[1],
                feature_code=parts[2],
                relevance=_required_decimal(value, code),
            )
        )
    return tuple(sorted(links, key=lambda link: (link.need_tag, link.feature_code)))


def _fact_decimal(facts: Mapping[str, str], code: str) -> Decimal | None:
    value = facts.get(code)
    return None if value is None else _required_decimal(value, code)


def _first_fact_decimal(facts: Mapping[str, str], codes: tuple[str, ...]) -> Decimal | None:
    present = [code for code in codes if code in facts]
    if len(present) > 1:
        raise ValueError(f"conflicting snapshot facts: {', '.join(present)}")
    return _fact_decimal(facts, present[0]) if present else None


def _fact_int(facts: Mapping[str, str], code: str) -> int | None:
    value = facts.get(code)
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{code} must be an integer") from error
    if parsed != parsed.to_integral_value():
        raise ValueError(f"{code} must be an integer")
    return int(parsed)


def _fact_bool(facts: Mapping[str, str], code: str) -> bool | None:
    value = facts.get(code)
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"{code} must be true or false")


def _required_decimal(value: str, label: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be numeric") from error


def _slot_decimal(value: SlotValue, label: str) -> Decimal | None:
    if value is None or is_declined(value):
        return None
    if isinstance(value, bool) or isinstance(value, list):
        raise ValueError(f"{label} slot must be numeric")
    return _required_decimal(str(value), label)


def _slot_int(value: SlotValue, label: str) -> int | None:
    decimal_value = _slot_decimal(value, label)
    if decimal_value is None:
        return None
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"{label} slot must be an integer")
    return int(decimal_value)


def _slot_bool(value: SlotValue, label: str) -> bool | None:
    if value is None or is_declined(value):
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{label} slot must be boolean")


def _slot_text(value: SlotValue, label: str) -> str | None:
    if value is None or is_declined(value):
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"{label} slot must be text")


def _slot_tags(value: SlotValue) -> tuple[str, ...]:
    if value is None or is_declined(value):
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("habit_need_tags slot must be a list of non-empty strings")
    return tuple(value)
