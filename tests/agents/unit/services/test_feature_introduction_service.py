"""Unit tests for A5-7 orchestration through the recommendation service."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import Recommendation
from src.agents.domain.feature_introduction import FeatureIntroductionRecord
from src.agents.domain.values import SlotName
from src.agents.services.recommendation import (
    DefaultRecommendationService,
    RunScoringContext,
)
from src.agents.services.snapshotting import RunSnapshotEnvelope, SnapshotCandidate, SnapshotFact

RUN_ID = UUID("10000000-0000-0000-0000-000000000301")
VEHICLE_1 = UUID("00000000-0000-0000-0000-000000000301")
VEHICLE_2 = UUID("00000000-0000-0000-0000-000000000302")


class FakeRecommendationDataSource:
    def __init__(self, context: RunScoringContext) -> None:
        self.context = context

    async def load(self, run_id: UUID) -> RunScoringContext | None:
        return self.context if run_id == RUN_ID else None


class FakeFeatureIntroductionSource:
    def __init__(self, records: list[FeatureIntroductionRecord]) -> None:
        self.records = records
        self.calls: list[tuple[tuple[UUID, ...], tuple[str, ...]]] = []

    async def load(
        self, *, vehicle_ids: tuple[UUID, ...], need_tags: tuple[str, ...]
    ) -> list[FeatureIntroductionRecord]:
        self.calls.append((vehicle_ids, need_tags))
        return self.records


def _context(*, slots: dict[SlotName, object]) -> RunScoringContext:
    candidates = tuple(
        SnapshotCandidate(
            vehicle_id=vehicle_id,
            facts=(
                SnapshotFact(
                    fact_code="VEHICLE_TYPE",
                    value_text="CAR",
                    source_table="vehicles",
                    source_id=vehicle_id,
                ),
            ),
        )
        for vehicle_id in (VEHICLE_1, VEHICLE_2)
    )
    return RunScoringContext(
        snapshot=RunSnapshotEnvelope(
            captured_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
            candidates=candidates,
            assertions=(),
        ),
        slots=slots,
        lowest_price_tier_ceiling_vnd=Decimal("450000000"),
    )


def _record() -> FeatureIntroductionRecord:
    return FeatureIntroductionRecord(
        vehicle_id=VEHICLE_1,
        feature_code="ADAS_LEVEL_2",
        feature_name="Hỗ trợ lái nâng cao",
        need_tag="LONG_DISTANCE",
        relevance=Decimal("0.90"),
        flag_status="YES",
        verification_status="APPROVED",
        feature_status="ACTIVE",
        display_order=1,
        evidence_ref="vehicle_feature_flags:flag-1",
    )


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(vehicle_id=VEHICLE_1, rank=1, reasons=["a", "b"]),
        Recommendation(vehicle_id=VEHICLE_2, rank=2, reasons=["a", "b"]),
    ]


@pytest.mark.asyncio
async def test_service_derives_tags_from_slots_and_loads_only_ranked_candidates() -> None:
    feature_source = FakeFeatureIntroductionSource([_record()])
    service = DefaultRecommendationService(
        source=FakeRecommendationDataSource(_context(slots={SlotName.REQUIRED_RANGE_KM: 160})),
        feature_introduction_source=feature_source,
    )

    result = await service.introduce_features(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        customer_asked_feature_codes=set(),
    )

    assert [item.feature_code for item in result] == ["ADAS_LEVEL_2"]
    assert feature_source.calls == [((VEHICLE_1, VEHICLE_2), ("LONG_DISTANCE", "HIGHWAY_SAFETY"))]


@pytest.mark.asyncio
async def test_service_with_no_derived_need_tags_returns_empty_without_query() -> None:
    feature_source = FakeFeatureIntroductionSource([_record()])
    service = DefaultRecommendationService(
        source=FakeRecommendationDataSource(_context(slots={SlotName.PURPOSE: "ca_nhan"})),
        feature_introduction_source=feature_source,
    )

    result = await service.introduce_features(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        customer_asked_feature_codes=set(),
    )

    assert result == []
    assert feature_source.calls == []


@pytest.mark.asyncio
async def test_service_does_not_introduce_customer_asked_feature() -> None:
    feature_source = FakeFeatureIntroductionSource([_record()])
    service = DefaultRecommendationService(
        source=FakeRecommendationDataSource(_context(slots={SlotName.REQUIRED_RANGE_KM: 160})),
        feature_introduction_source=feature_source,
    )

    result = await service.introduce_features(
        run_id=RUN_ID,
        recommendations=_recommendations(),
        customer_asked_feature_codes={"ADAS_LEVEL_2"},
    )

    assert result == []


@pytest.mark.asyncio
async def test_service_rejects_unranked_recommendation_input() -> None:
    service = DefaultRecommendationService(
        source=FakeRecommendationDataSource(_context(slots={SlotName.REQUIRED_RANGE_KM: 160})),
        feature_introduction_source=FakeFeatureIntroductionSource([]),
    )
    invalid = [Recommendation(vehicle_id=UUID(int=999), rank=1, reasons=["a", "b"])]

    with pytest.raises(ValueError, match="outside run snapshot"):
        await service.introduce_features(
            run_id=RUN_ID,
            recommendations=invalid,
            customer_asked_feature_codes=set(),
        )
