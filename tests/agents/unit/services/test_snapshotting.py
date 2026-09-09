"""Unit tests for the A5-2 immutable snapshot service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.agents.contracts import FeatureAssertion
from src.agents.domain.comparison import ComparisonCell, ComparisonRow, ComparisonTable
from src.agents.domain.values import VehicleType
from src.agents.services.operations.comparison_image import render_comparison_image
from src.agents.services.snapshotting import (
    DefaultSnapshottingService,
    RunSnapshotEnvelope,
    SnapshotCandidate,
    SnapshotFact,
    _ordered_candidates,
    parse_snapshot,
)

NOW = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)
RUN_ID = UUID("30000000-0000-0000-0000-000000000001")
VEHICLE_ID = UUID("40000000-0000-0000-0000-000000000001")
VEHICLE_ID_2 = UUID("40000000-0000-0000-0000-000000000002")


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeCatalogSnapshotSource:
    def __init__(self, catalog: dict[UUID, dict[str, str]]) -> None:
        self.catalog = catalog
        self.calls: list[tuple[tuple[UUID, ...], datetime]] = []

    async def load(self, *, candidate_ids: tuple[UUID, ...], at: datetime) -> tuple[SnapshotCandidate, ...]:
        self.calls.append((candidate_ids, at))
        return tuple(
            SnapshotCandidate(
                vehicle_id=vehicle_id,
                facts=tuple(
                    SnapshotFact(
                        fact_code=fact_code,
                        value_text=value,
                        source_table="vehicle_prices",
                        source_id=UUID("50000000-0000-0000-0000-000000000001"),
                    )
                    for fact_code, value in self.catalog[vehicle_id].items()
                ),
            )
            for vehicle_id in candidate_ids
            if vehicle_id in self.catalog
        )


class FakeRunRepository:
    def __init__(self, *, fail_on_state: bool = False) -> None:
        self.payloads: dict[UUID, dict[str, object]] = {}
        self.states: dict[UUID, str] = {}
        self.fail_on_state = fail_on_state

    async def save_snapshot(self, run_id: UUID, payload: dict) -> None:
        self.payloads[run_id] = deepcopy(payload)

    async def set_state(self, run_id: UUID, state: str) -> None:
        if self.fail_on_state:
            raise RuntimeError("state write failed")
        self.states[run_id] = state

    async def save_evidence(self, run_id: UUID, facts) -> None:
        return None

    async def save_candidates(self, run_id: UUID, candidates) -> None:
        return None

    async def save_scores(self, run_id: UUID, scores) -> None:
        return None

    async def set_candidate_ranks(self, run_id: UUID, ranks) -> None:
        return None

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]:
        return []

    async def save_tco_estimate(self, run_id: UUID, result) -> None:
        return None


class FakeUnitOfWork:
    def __init__(self, runs: FakeRunRepository) -> None:
        self.runs = runs
        self.transaction_count = 0

    @asynccontextmanager
    async def transaction(self):
        self.transaction_count += 1
        old_payloads = deepcopy(self.runs.payloads)
        old_states = self.runs.states.copy()
        try:
            yield SimpleNamespace(runs=self.runs)
        except Exception:
            self.runs.payloads = old_payloads
            self.runs.states = old_states
            raise


def _service(
    catalog: dict[UUID, dict[str, str]], *, fail_on_state: bool = False
) -> tuple[DefaultSnapshottingService, FakeCatalogSnapshotSource, FakeRunRepository, FakeUnitOfWork]:
    source = FakeCatalogSnapshotSource(catalog)
    runs = FakeRunRepository(fail_on_state=fail_on_state)
    unit_of_work = FakeUnitOfWork(runs)
    return (
        DefaultSnapshottingService(source=source, unit_of_work=unit_of_work, clock=FakeClock()),
        source,
        runs,
        unit_of_work,
    )


def test_ordered_candidates_preserve_model_names_through_round_trip_and_placeholder() -> None:
    loaded = (
        SnapshotCandidate(vehicle_id=VEHICLE_ID_2, facts=(), model_name="VF 9 Plus"),
        SnapshotCandidate(vehicle_id=VEHICLE_ID, facts=(), model_name="VF 8 Eco"),
    )

    ordered = _ordered_candidates((VEHICLE_ID, VEHICLE_ID_2), loaded)
    persisted = RunSnapshotEnvelope(captured_at=NOW, candidates=ordered, assertions=()).model_dump(mode="json")
    restored = parse_snapshot(persisted)
    table = ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(VEHICLE_ID, VEHICLE_ID_2),
        vehicle_names=tuple(candidate.model_name for candidate in restored.candidates),
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=(
                    ComparisonCell(VEHICLE_ID, "1", "STRUCTURED", "snapshot", None),
                    ComparisonCell(VEHICLE_ID_2, "2", "STRUCTURED", "snapshot", None),
                ),
            ),
        ),
    )

    image_text = render_comparison_image(table, photos={}, _debug_text=True)

    assert tuple(candidate.model_name for candidate in restored.candidates) == (
        "VF 8 Eco",
        "VF 9 Plus",
    )
    assert "Chưa có ảnh: VF 8 Eco" in image_text
    assert "Chưa có ảnh: VF 9 Plus" in image_text


@pytest.mark.asyncio
async def test_catalog_change_after_snapshot_does_not_change_saved_run_payload() -> None:
    catalog = {VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}}
    service, source, runs, _ = _service(catalog)

    await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[])
    catalog[VEHICLE_ID]["STARTING_PRICE_VND"] = "800000000"
    live_after_update = await source.load(candidate_ids=(VEHICLE_ID,), at=NOW)
    saved = parse_snapshot(runs.payloads[RUN_ID])

    assert live_after_update[0].facts[0].value_text == "800000000"
    assert saved.candidates[0].facts[0].value_text == "700000000"
    assert runs.states[RUN_ID] == "SNAPSHOT_READY"


@pytest.mark.asyncio
async def test_snapshot_persists_assertions_and_state_in_one_transaction() -> None:
    service, source, runs, unit_of_work = _service({VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}})
    assertion = FeatureAssertion(
        vehicle_id=VEHICLE_ID,
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref=f"{VEHICLE_ID}:PANORAMIC_ROOF",
        confidence=0.99,
    )

    await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[assertion])
    saved = parse_snapshot(runs.payloads[RUN_ID])

    assert source.calls == [((VEHICLE_ID,), NOW)]
    assert unit_of_work.transaction_count == 1
    assert saved.assertions[0].feature_code == "PANORAMIC_ROOF"
    assert runs.states[RUN_ID] == "SNAPSHOT_READY"


@pytest.mark.asyncio
async def test_missing_catalog_candidate_rejects_snapshot_without_writing() -> None:
    service, _, runs, unit_of_work = _service({})

    with pytest.raises(ValueError, match="candidate mismatch"):
        await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[])

    assert unit_of_work.transaction_count == 0
    assert runs.payloads == {}


@pytest.mark.asyncio
async def test_assertion_for_vehicle_outside_candidate_set_is_rejected() -> None:
    service, _, runs, unit_of_work = _service({VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}})
    assertion = FeatureAssertion(
        vehicle_id=UUID("40000000-0000-0000-0000-000000000099"),
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="outside:feature",
    )

    with pytest.raises(ValueError, match="outside candidate set"):
        await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[assertion])

    assert unit_of_work.transaction_count == 0
    assert runs.payloads == {}


@pytest.mark.asyncio
async def test_state_write_failure_rolls_back_snapshot_payload() -> None:
    service, _, runs, unit_of_work = _service({VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}}, fail_on_state=True)

    with pytest.raises(RuntimeError, match="state write failed"):
        await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[])

    assert unit_of_work.transaction_count == 1
    assert runs.payloads == {}
    assert runs.states == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_ids", [[], [VEHICLE_ID, VEHICLE_ID]])
async def test_empty_or_duplicate_candidate_ids_are_rejected_before_catalog_read(
    candidate_ids: list[UUID],
) -> None:
    service, source, runs, unit_of_work = _service({VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}})

    with pytest.raises(ValueError, match="candidate"):
        await service.snapshot(run_id=RUN_ID, candidate_ids=candidate_ids, assertions=[])

    assert source.calls == []
    assert unit_of_work.transaction_count == 0
    assert runs.payloads == {}


@pytest.mark.asyncio
async def test_invalid_assertion_confidence_is_rejected_before_transaction() -> None:
    service, _, runs, unit_of_work = _service({VEHICLE_ID: {"STARTING_PRICE_VND": "700000000"}})
    assertion = FeatureAssertion(
        vehicle_id=VEHICLE_ID,
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle:feature",
        confidence=1.5,
    )

    with pytest.raises(ValueError, match="confidence"):
        await service.snapshot(run_id=RUN_ID, candidate_ids=[VEHICLE_ID], assertions=[assertion])

    assert unit_of_work.transaction_count == 0
    assert runs.payloads == {}
