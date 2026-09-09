"""Snapshot adapter maps effective catalog rows into immutable facts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.agents.adapters.snapshot_source import SqlAlchemyCatalogSnapshotSource


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self._rows


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self._results = iter(results)

    async def execute(self, _statement: object) -> _Result:
        return next(self._results)

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.asyncio
async def test_load_maps_requested_car_price_and_spec_facts() -> None:
    vehicle_id = uuid4()
    price_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="CAR",
                        brand=None,
                        model_name="VF test",
                        variant_name=None,
                    )
                ]
            ),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        price_id=str(price_id),
                        price_type="STARTING_PRICE",
                        amount_vnd=700_000_000,
                    )
                ]
            ),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        range_km=400,
                        seat_count=5,

                        fast_charge_time_minutes=30,
                        home_charge_time_minutes=None,
                        energy_consumption_kwh_per_100km=None,
                        cargo_volume_standard_l=None,
                        body_type=None,
                        battery_capacity_kwh=None,
                        motor_power_kw=None,
                        torque_nm=None,
                        max_speed_kmh=None,
                        acceleration_0_100_seconds=None,
                        fast_charge_power_kw=None,
                        cargo_volume_maximum_l=None,
                        towing_capacity_kg=None,
                    )
                ]
            ),
            _Result([]),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    assert len(candidates) == 1
    assert candidates[0].model_name == "VF test"
    facts = {fact.fact_code: fact for fact in candidates[0].facts}
    assert facts["VEHICLE_TYPE"].value_text == "CAR"
    assert facts["STARTING_PRICE_VND"].source_id == price_id
    assert facts["CAR_RANGE_KM"].value_text == "400"
    assert facts["CAR_SEAT_COUNT"].value_text == "5"
    assert "HOME_CHARGE_TIME_MINUTES" not in facts


@pytest.mark.asyncio
async def test_load_emits_vehicle_type_fact_for_a_car() -> None:
    vehicle_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="CAR",
                        brand=None,
                        model_name="VF test",
                        variant_name=None,
                    )
                ]
            ),
            _Result([]),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        range_km=None,
                        seat_count=None,
                        fast_charge_time_minutes=None,
                        home_charge_time_minutes=None,
                        energy_consumption_kwh_per_100km=None,
                        cargo_volume_standard_l=None,
                        body_type=None,
                        battery_capacity_kwh=None,
                        motor_power_kw=None,
                        torque_nm=None,
                        max_speed_kmh=None,
                        acceleration_0_100_seconds=None,
                        fast_charge_power_kw=None,
                        cargo_volume_maximum_l=None,
                        towing_capacity_kg=None,
                    )
                ]
            ),
            _Result([]),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    facts = {fact.fact_code: fact for fact in candidates[0].facts}
    assert facts["VEHICLE_TYPE"].value_text == "CAR"
    assert facts["VEHICLE_TYPE"].source_table == "vehicles"


@pytest.mark.asyncio
async def test_load_emits_vehicle_type_fact_for_an_electric_motorbike() -> None:
    vehicle_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="ELECTRIC_MOTORBIKE",
                        brand="VF",
                        model_name="Evo test",
                        variant_name=None,
                    )
                ]
            ),
            _Result([]),
            _Result([]),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        range_max_km=None,
                        motor_power_w=None,
                        max_power_w=None,
                        torque_nm=None,
                        max_speed_kmh=None,
                        battery_capacity_kwh=None,
                        charging_time_minutes=None,
                        seat_height_mm=None,
                        max_load_kg=None,
                        energy_consumption_kwh_per_100km=None,
                        battery_removable=None,
                        battery_swappable=None,
                    )
                ]
            ),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    facts = {fact.fact_code: fact for fact in candidates[0].facts}
    assert facts["VEHICLE_TYPE"].value_text == "ELECTRIC_MOTORBIKE"


@pytest.mark.asyncio
async def test_load_emits_lowercase_battery_bool_facts() -> None:
    vehicle_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="ELECTRIC_MOTORBIKE",
                        brand="VF",
                        model_name="Evo test",
                        variant_name=None,
                    )
                ]
            ),
            _Result([]),
            _Result([]),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        range_max_km=None,
                        motor_power_w=None,
                        max_power_w=None,
                        torque_nm=None,
                        max_speed_kmh=None,
                        battery_capacity_kwh=None,
                        charging_time_minutes=None,
                        seat_height_mm=None,
                        max_load_kg=None,
                        energy_consumption_kwh_per_100km=None,
                        battery_removable=True,
                        battery_swappable=False,
                    )
                ]
            ),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    facts = {fact.fact_code: fact for fact in candidates[0].facts}
    assert facts["BATTERY_REMOVABLE"].value_text == "true"
    assert facts["BATTERY_SWAPPABLE"].value_text == "false"


@pytest.mark.asyncio
async def test_load_omits_facts_for_null_columns() -> None:
    vehicle_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="CAR",
                        brand=None,
                        model_name="VF test",
                        variant_name=None,
                    )
                ]
            ),
            _Result([]),
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        range_km=None,
                        seat_count=None,
                        fast_charge_time_minutes=None,
                        home_charge_time_minutes=None,
                        energy_consumption_kwh_per_100km=None,
                        cargo_volume_standard_l=None,
                        body_type=None,
                        battery_capacity_kwh=None,
                        motor_power_kw=None,
                        torque_nm=None,
                        max_speed_kmh=None,
                        acceleration_0_100_seconds=None,
                        fast_charge_power_kw=None,
                        cargo_volume_maximum_l=None,
                        towing_capacity_kg=None,
                    )
                ]
            ),
            _Result([]),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    facts = {fact.fact_code: fact for fact in candidates[0].facts}
    assert "ENERGY_CONSUMPTION_KWH_PER_100KM" not in facts
    assert "CARGO_VOLUME_STANDARD_L" not in facts


@pytest.mark.asyncio
async def test_load_composes_display_name_with_variant() -> None:
    """[I2] Tên snapshot phải ghép brand + model_name + variant_name."""

    vehicle_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(vehicle_id),
                        vehicle_type="CAR",
                        brand="VinFast",
                        model_name="VF 6",
                        variant_name="Plus",
                    )
                ]
            ),
            _Result([]),
            _Result([]),
            _Result([]),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(vehicle_id,), at=datetime.now(UTC))

    assert candidates[0].model_name == "VinFast VF 6 Plus"


@pytest.mark.asyncio
async def test_load_gives_two_variants_of_one_model_distinct_display_names() -> None:
    """[I2] Hai variant sống sót cùng lượt lọc không được ra hai card trùng tên."""

    eco_id = uuid4()
    plus_id = uuid4()
    session = _Session(
        [
            _Result(
                [
                    SimpleNamespace(
                        vehicle_id=str(eco_id),
                        vehicle_type="CAR",
                        brand="VinFast",
                        model_name="VF 6",
                        variant_name="Eco",
                    ),
                    SimpleNamespace(
                        vehicle_id=str(plus_id),
                        vehicle_type="CAR",
                        brand="VinFast",
                        model_name="VF 6",
                        variant_name="Plus",
                    ),
                ]
            ),
            _Result([]),
            _Result([]),
            _Result([]),
        ]
    )
    source = SqlAlchemyCatalogSnapshotSource(lambda: session)

    candidates = await source.load(candidate_ids=(eco_id, plus_id), at=datetime.now(UTC))

    names = {candidate.vehicle_id: candidate.model_name for candidate in candidates}
    assert names[eco_id] == "VinFast VF 6 Eco"
    assert names[plus_id] == "VinFast VF 6 Plus"
    assert names[eco_id] != names[plus_id]
