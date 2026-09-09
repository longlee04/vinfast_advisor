"""Unit tests for the A5-3 snapshot-backed recommendation service."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.agents.domain.values import DECLINED_SLOT_VALUE, SlotName
from src.agents.services.recommendation import (
    DefaultRecommendationService,
    RunScoringContext,
)
from src.agents.services.snapshotting import (
    RunSnapshotEnvelope,
    SnapshotCandidate,
    SnapshotFact,
    SnapshotFeatureAssertion,
)

RUN_ID = UUID("10000000-0000-0000-0000-000000000101")
VEHICLE_1 = UUID("00000000-0000-0000-0000-000000000101")
VEHICLE_2 = UUID("00000000-0000-0000-0000-000000000102")


def _fact(code: str, value: str, *, table: str = "vehicles") -> SnapshotFact:
    return SnapshotFact(fact_code=code, value_text=value, source_table=table)


def _candidate(vehicle_id: UUID, *, range_km: str, model_name: str = "") -> SnapshotCandidate:
    return SnapshotCandidate(
        vehicle_id=vehicle_id,
        model_name=model_name,
        facts=(
            _fact("VEHICLE_TYPE", "CAR"),
            _fact("STARTING_PRICE_VND", "650000000", table="vehicle_prices"),
            _fact("CAR_RANGE_KM", range_km, table="cars"),
            _fact("CAR_SEAT_COUNT", "5", table="cars"),
            _fact("CARGO_VOLUME_STANDARD_L", "500", table="cars"),
            _fact("HOME_CHARGE_TIME_MINUTES", "480", table="cars"),
        ),
    )


def _context(*, assertions: tuple[SnapshotFeatureAssertion, ...] = ()) -> RunScoringContext:
    return RunScoringContext(
        snapshot=RunSnapshotEnvelope(
            captured_at=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
            candidates=(
                _candidate(VEHICLE_1, range_km="350", model_name="VF 6"),
                _candidate(VEHICLE_2, range_km="450", model_name="VF 8"),
            ),
            assertions=assertions,
        ),
        slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 700_000_000,
            SlotName.PASSENGER_COUNT: 5,
            SlotName.REQUIRED_RANGE_KM: 300,
            SlotName.HOME_CHARGING: True,
            SlotName.PURPOSE: "gia_dinh",
        },
    )


class FakeRecommendationDataSource:
    def __init__(self, context: RunScoringContext | None) -> None:
        self.context = context
        self.calls: list[UUID] = []

    async def load(self, run_id: UUID) -> RunScoringContext | None:
        self.calls.append(run_id)
        return self.context


@pytest.mark.asyncio
async def test_service_reads_one_run_context_and_returns_ranked_contracts() -> None:
    source = FakeRecommendationDataSource(_context())
    service = DefaultRecommendationService(source=source)

    recommendations = await service.recommend(RUN_ID)

    assert source.calls == [RUN_ID]
    assert [item.vehicle_id for item in recommendations] == [VEHICLE_2, VEHICLE_1]
    assert [item.rank for item in recommendations] == [1, 2]
    assert all(len(item.reasons) >= 2 for item in recommendations)
    assert all(reason.startswith("[slot=") for item in recommendations for reason in item.reasons)


@pytest.mark.asyncio
async def test_service_returns_empty_when_run_context_does_not_exist() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(None))

    assert await service.recommend(RUN_ID) == []


@pytest.mark.asyncio
async def test_service_rejects_malformed_numeric_snapshot_fact() -> None:
    bad_candidate = SnapshotCandidate(
        vehicle_id=VEHICLE_1,
        facts=(
            _fact("VEHICLE_TYPE", "CAR"),
            _fact("STARTING_PRICE_VND", "not-a-number", table="vehicle_prices"),
        ),
    )
    context = RunScoringContext(
        snapshot=RunSnapshotEnvelope(
            captured_at=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
            candidates=(bad_candidate,),
            assertions=(),
        ),
        slots={SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 700_000_000},
    )
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(context))

    with pytest.raises(ValueError, match="STARTING_PRICE_VND must be numeric"):
        await service.recommend(RUN_ID)


@pytest.mark.asyncio
async def test_need_tag_trace_is_rendered_from_snapshot_flag_only() -> None:
    need_tag_fact = _fact(
        "NEED_TAG::URBAN_TRAFFIC::PANORAMIC_ROOF",
        "0.75",
        table="feature_need_tags",
    )
    candidate = _candidate(VEHICLE_1, range_km="350").model_copy(
        update={"facts": (*_candidate(VEHICLE_1, range_km="350").facts, need_tag_fact)}
    )
    assertion = SnapshotFeatureAssertion(
        vehicle_id=VEHICLE_1,
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-1",
    )
    context = RunScoringContext(
        snapshot=RunSnapshotEnvelope(
            captured_at=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
            candidates=(candidate,),
            assertions=(assertion,),
        ),
        slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 700_000_000,
            SlotName.HABIT_NEED_TAGS: ["URBAN_TRAFFIC"],
        },
    )
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(context))

    recommendations = await service.recommend(RUN_ID)

    tag_reason = next(reason for reason in recommendations[0].reasons if "need_tag=URBAN_TRAFFIC" in reason)
    assert "slot=habit_need_tags" in tag_reason
    assert "feature_code=PANORAMIC_ROOF" in tag_reason
    assert "source=FLAG" in tag_reason
    assert "evidence=vehicle_feature_flags:flag-1" in tag_reason


@pytest.mark.asyncio
async def test_declined_habit_tags_do_not_crash_scoring_or_become_a_need_tag() -> None:
    context = _context()
    context = replace(
        context,
        slots={
            **context.slots,
            SlotName.HABIT_NEED_TAGS: DECLINED_SLOT_VALUE,
        },
    )
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(context))

    recommendations = await service.recommend(RUN_ID)

    assert [item.vehicle_id for item in recommendations] == [VEHICLE_2, VEHICLE_1]
    assert all("__declined__" not in reason for item in recommendations for reason in item.reasons)


@pytest.mark.asyncio
async def test_declined_home_charging_scores_as_unknown_instead_of_raising() -> None:
    """Hỏi hết lượt mà khách chưa nói chỗ sạc → slot ghi `__declined__`.

    `_slot_bool` từng raise "home_charging slot must be boolean" trên marker
    này (500 thật ở `/api/v1/agent/turn`): mọi parser slot khác đều đã coi
    declined là "khách không cho biết" — bool phải theo cùng quy ước đó.
    """

    context = replace(
        _context(),
        slots={
            **_context().slots,
            SlotName.HOME_CHARGING: DECLINED_SLOT_VALUE,
        },
    )
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(context))

    recommendations = await service.recommend(RUN_ID)

    assert [item.vehicle_id for item in recommendations] == [VEHICLE_2, VEHICLE_1]
    charging_reasons = [reason for item in recommendations for reason in item.reasons if "slot=home_charging" in reason]
    assert charging_reasons == []
    assert all("__declined__" not in reason for item in recommendations for reason in item.reasons)


@pytest.mark.asyncio
async def test_recommendation_carries_snapshot_model_name() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context()))

    recommendations = await service.recommend(RUN_ID)

    names = {item.vehicle_id: item.display_name for item in recommendations}
    assert names[VEHICLE_1] == "VF 6"
    assert names[VEHICLE_2] == "VF 8"


@pytest.mark.asyncio
async def test_customer_asked_feature_resolves_to_its_vietnamese_label() -> None:
    """Đầu-cuối service: mã tính năng khách chọn ở lượt 2 phải tới `scoring.py`
    ĐÃ KÈM nhãn tiếng Việt (`FEATURE_LABELS` thật, không phải giả lập) — bug
    thật Sếp báo 2026-08-21: đề xuất chỉ nói chung chung, không gọi tên."""

    assertion = SnapshotFeatureAssertion(
        vehicle_id=VEHICLE_1,
        feature_code="ANTI_THEFT",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-9",
    )
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context(assertions=(assertion,))))

    recommendations = await service.recommend(RUN_ID, customer_asked_feature_codes=("ANTI_THEFT",))

    feature_reason = next(
        reason for item in recommendations for reason in item.reasons if "feature_code=ANTI_THEFT" in reason
    )
    assert "khoá chống trộm" in feature_reason
    assert "ANTI_THEFT" not in feature_reason.split("]", 1)[1]  # phần message, bỏ trace
