"""Unit tests for A5-4 comparison through the snapshot-backed service."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.agents.domain.values import SlotName
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

RUN_ID = UUID("10000000-0000-0000-0000-000000000201")
CAR_1 = UUID("00000000-0000-0000-0000-000000000201")
CAR_2 = UUID("00000000-0000-0000-0000-000000000202")
CAPTURED_AT = datetime(2026, 8, 7, 10, 30, tzinfo=UTC)


def _candidate(vehicle_id: UUID, price: str, range_km: str, model_name: str = "VF 8 Eco") -> SnapshotCandidate:
    return SnapshotCandidate(
        vehicle_id=vehicle_id,
        model_name=model_name,
        facts=(
            SnapshotFact(
                fact_code="VEHICLE_TYPE",
                value_text="CAR",
                source_table="vehicles",
                source_id=vehicle_id,
            ),
            SnapshotFact(
                fact_code="STARTING_PRICE_VND",
                value_text=price,
                source_table="vehicle_prices",
            ),
            SnapshotFact(
                fact_code="CAR_RANGE_KM",
                value_text=range_km,
                source_table="cars",
                source_id=vehicle_id,
            ),
            SnapshotFact(
                fact_code="CAR_SEAT_COUNT",
                value_text="5",
                source_table="cars",
                source_id=vehicle_id,
            ),
            SnapshotFact(
                fact_code="HOME_CHARGE_TIME_MINUTES",
                value_text="480",
                source_table="cars",
                source_id=vehicle_id,
            ),
        ),
    )


class FakeRecommendationDataSource:
    def __init__(self, context: RunScoringContext | None) -> None:
        self.context = context
        self.live_catalog_price = "999999999"
        self.calls: list[UUID] = []

    async def load(self, run_id: UUID) -> RunScoringContext | None:
        self.calls.append(run_id)
        return self.context


def _context() -> RunScoringContext:
    return RunScoringContext(
        snapshot=RunSnapshotEnvelope(
            captured_at=CAPTURED_AT,
            candidates=(
                _candidate(CAR_1, "600000000", "400", "VF 8 Eco"),
                _candidate(CAR_2, "700000000", "500", "VF 9 Plus"),
            ),
            assertions=(
                SnapshotFeatureAssertion(
                    vehicle_id=CAR_1,
                    feature_code="PREMIUM_AUDIO",
                    status="YES",
                    source="DOCUMENT",
                    evidence_ref="document_chunks:chunk-1",
                ),
                SnapshotFeatureAssertion(
                    vehicle_id=CAR_2,
                    feature_code="PREMIUM_AUDIO",
                    status="YES",
                    source="FLAG",
                    evidence_ref="vehicle_feature_flags:flag-2",
                ),
            ),
        ),
        slots={SlotName.VEHICLE_TYPE: "CAR"},
    )


@pytest.mark.asyncio
async def test_comparison_and_lookup_at_same_snapshot_time_return_same_number() -> None:
    source = FakeRecommendationDataSource(_context())
    service = DefaultRecommendationService(source=source)

    table = await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_1, CAR_2])
    source.live_catalog_price = "123"
    lookup = await service.lookup_fact(
        run_id=RUN_ID,
        vehicle_id=CAR_1,
        fact_code="STARTING_PRICE_VND",
    )

    price_row = next(row for row in table.rows if row.criterion_code == "STARTING_PRICE_VND")
    compared = next(cell for cell in price_row.cells if cell.vehicle_id == CAR_1)
    assert table.captured_at == CAPTURED_AT
    assert lookup is not None
    assert compared.value_text == lookup.value_text == "600000000"
    assert source.calls == [RUN_ID, RUN_ID]


@pytest.mark.asyncio
async def test_comparison_uses_model_names_frozen_in_snapshot() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context()))

    table = await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_2, CAR_1])

    assert table.vehicle_names == ("VF 9 Plus", "VF 8 Eco")


@pytest.mark.asyncio
async def test_service_preserves_document_unverified_label() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context()))

    table = await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_1, CAR_2])

    row = next(item for item in table.rows if item.criterion_code == "PREMIUM_AUDIO")
    cells = {cell.vehicle_id: cell for cell in row.cells}
    assert cells[CAR_1].label == "theo tài liệu, chưa xác minh"


@pytest.mark.asyncio
async def test_service_leaves_flag_cell_unlabelled() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context()))

    table = await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_1, CAR_2])

    row = next(item for item in table.rows if item.criterion_code == "PREMIUM_AUDIO")
    cells = {cell.vehicle_id: cell for cell in row.cells}
    assert cells[CAR_2].label is None


@pytest.mark.asyncio
async def test_compare_rejects_vehicle_not_present_in_run_snapshot() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(_context()))

    with pytest.raises(ValueError, match="outside run snapshot"):
        await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_1, UUID(int=999)])


@pytest.mark.asyncio
async def test_compare_rejects_missing_run_context() -> None:
    service = DefaultRecommendationService(source=FakeRecommendationDataSource(None))

    with pytest.raises(ValueError, match="run snapshot not found"):
        await service.compare(run_id=RUN_ID, vehicle_ids=[CAR_1, CAR_2])
