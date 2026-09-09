"""Unit tests for the A5-5 TCO estimation application service."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.values import VehicleType
from src.agents.services.tco_estimation import DefaultTcoEstimationService
from src.agents.tools.tco import BatteryPolicyInput, TcoAssumptionInput, VehicleTcoInput

NOW = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)
VEHICLE_ID = UUID("00000000-0000-0000-0000-000000000011")
ASSUMPTION_ID = UUID("10000000-0000-0000-0000-000000000011")


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeTcoDataSource:
    def __init__(self, data: VehicleTcoInput | None) -> None:
        self.data = data
        self.calls: list[tuple[UUID, str, datetime]] = []

    async def load(self, *, vehicle_id: UUID, region_code: str, at: datetime) -> VehicleTcoInput | None:
        self.calls.append((vehicle_id, region_code, at))
        return self.data


def _data() -> VehicleTcoInput:
    return VehicleTcoInput(
        vehicle_type=VehicleType.CAR,
        prices_vnd={"STARTING_PRICE": Decimal("100000000")},
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=ASSUMPTION_ID,
                vehicle_type=VehicleType.CAR,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("3000"),
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("10"),
    )


@pytest.mark.asyncio
async def test_service_loads_region_scoped_data_at_clock_time_and_calculates() -> None:
    source = FakeTcoDataSource(_data())
    service = DefaultTcoEstimationService(data_source=source, clock=FakeClock())

    result = await service.estimate(vehicle_id=VEHICLE_ID, daily_distance_km=10.0)

    # Không truyền `region_code` → dùng mặc định Khu vực II (đa số khách).
    assert source.calls == [(VEHICLE_ID, "KHU_VUC_II", NOW)]
    assert result.assumptions_id == ASSUMPTION_ID
    assert result.total_vnd == Decimal("105400000")
    assert result.computed_at == NOW


@pytest.mark.asyncio
async def test_service_missing_catalog_data_returns_tco_unavailable() -> None:
    service = DefaultTcoEstimationService(data_source=FakeTcoDataSource(None), clock=FakeClock())

    result = await service.estimate(vehicle_id=VEHICLE_ID, daily_distance_km=10.0)

    assert result.total_vnd is None
    assert result.unavailable_reason == "TCO_UNAVAILABLE: structured TCO data for vehicle"


@pytest.mark.asyncio
async def test_service_missing_daily_distance_returns_tco_unavailable_without_loading_data() -> None:
    source = FakeTcoDataSource(_data())
    service = DefaultTcoEstimationService(data_source=source, clock=FakeClock())

    result = await service.estimate(vehicle_id=VEHICLE_ID, daily_distance_km=None)

    assert source.calls == []
    assert result.unavailable_reason == "TCO_UNAVAILABLE: daily_distance_km"


class _FakeRuns:
    def __init__(self) -> None:
        self.tco_calls: list[tuple[UUID, object]] = []
        self.evidence_calls: list[tuple[UUID, tuple]] = []

    async def save_tco_estimate(self, run_id: UUID, result: object) -> None:
        self.tco_calls.append((run_id, result))

    async def save_evidence(self, run_id: UUID, facts) -> None:
        self.evidence_calls.append((run_id, tuple(facts)))


class _FakeTransaction:
    def __init__(self, runs: _FakeRuns) -> None:
        self.runs = runs

    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _FakeUnitOfWork:
    def __init__(self, runs: _FakeRuns) -> None:
        self._runs = runs

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self._runs)


RUN_ID = UUID("20000000-0000-0000-0000-000000000011")


@pytest.mark.asyncio
async def test_service_writes_tco_total_as_run_evidence() -> None:
    """Tầng tổng hợp chỉ render số có evidence; thiếu evidence là lượt chat vỡ."""
    runs = _FakeRuns()
    service = DefaultTcoEstimationService(
        data_source=FakeTcoDataSource(_data()),
        clock=FakeClock(),
        unit_of_work=_FakeUnitOfWork(runs),
    )

    result = await service.estimate(vehicle_id=VEHICLE_ID, daily_distance_km=10.0, run_id=RUN_ID)

    assert runs.tco_calls and runs.tco_calls[0][0] == RUN_ID
    assert len(runs.evidence_calls) == 1
    run_id, facts = runs.evidence_calls[0]
    assert run_id == RUN_ID
    assert len(facts) == 1
    assert facts[0].fact_code == "TCO_TOTAL_VND"
    assert facts[0].value_text == str(result.total_vnd)
    assert facts[0].source_id == VEHICLE_ID


@pytest.mark.asyncio
async def test_service_writes_no_evidence_when_tco_is_unavailable() -> None:
    runs = _FakeRuns()
    service = DefaultTcoEstimationService(
        data_source=FakeTcoDataSource(None),
        clock=FakeClock(),
        unit_of_work=_FakeUnitOfWork(runs),
    )

    await service.estimate(vehicle_id=VEHICLE_ID, daily_distance_km=10.0, run_id=RUN_ID)

    assert runs.evidence_calls == []
