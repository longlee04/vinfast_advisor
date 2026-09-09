"""Unit tests for the read-only vehicle overview SQLAlchemy adapter."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from src.agents.adapters.vehicle_overview_source import SqlAlchemyVehicleOverviewSource
from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_overview import AmbiguousVehicleResolution

ECO_ID = "11111111-1111-1111-1111-111111111111"
PLUS_ID = "22222222-2222-2222-2222-222222222222"


class FakeEmbedding:
    """Deterministic embedding double; catalog tests never need network access."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FakeResult:
    """Small SQLAlchemy result double supporting the adapter's read API."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    """Serve scripted query results while recording emitted SQL statements."""

    def __init__(self, responses: list[FakeResult]) -> None:
        self.responses = responses
        self.statements: list[Any] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return self.responses.pop(0)


class FakeSessionFactory:
    """Return a shared scripted session for each short-lived adapter read."""

    def __init__(self, *responses: FakeResult) -> None:
        self.session = FakeSession(list(responses))

    def __call__(self) -> FakeSession:
        return self.session


def _vehicle(vehicle_id: str, variant_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        vehicle_id=vehicle_id,
        vehicle_type="CAR",
        brand="VinFast",
        model_name="VF 7",
        variant_name=variant_name,
    )


def _source(*responses: FakeResult) -> tuple[SqlAlchemyVehicleOverviewSource, FakeSession]:
    factory = FakeSessionFactory(*responses)
    return SqlAlchemyVehicleOverviewSource(factory, FakeEmbedding()), factory.session


@pytest.mark.asyncio
async def test_resolve_model_returns_all_active_variants_in_stable_order() -> None:
    source, session = _source(FakeResult([_vehicle(ECO_ID, "Eco"), _vehicle(PLUS_ID, "Plus")]))

    resolved = await source.resolve("VF7")

    assert resolved is not None
    assert resolved.vehicle_name == "VinFast VF 7"
    assert resolved.vehicle_type is VehicleType.CAR
    assert resolved.vehicle_ids == (UUID(ECO_ID), UUID(PLUS_ID))
    assert resolved.variant_names == ("Eco", "Plus")
    sql = str(session.statements[0])
    assert "vehicles.status" in sql
    assert "ORDER BY vehicles.variant_name, vehicles.vehicle_id" in sql


@pytest.mark.asyncio
async def test_resolve_full_variant_returns_only_that_variant() -> None:
    source, _ = _source(FakeResult([_vehicle(PLUS_ID, "Plus")]))

    resolved = await source.resolve("VF 7 Plus")

    assert resolved is not None
    assert resolved.vehicle_ids == (UUID(PLUS_ID),)
    assert resolved.variant_names == ("Plus",)


@pytest.mark.asyncio
async def test_resolve_reports_cross_family_matches_as_ambiguous() -> None:
    other_family = SimpleNamespace(
        vehicle_id=PLUS_ID,
        vehicle_type="MOTORBIKE",
        brand="Other",
        model_name="VF 7",
        variant_name="Standard",
    )
    source, _ = _source(FakeResult([_vehicle(ECO_ID, "Eco"), other_family]))

    resolved = await source.resolve("VF7")

    assert resolved == AmbiguousVehicleResolution(vehicle_name="VF7")


@pytest.mark.asyncio
async def test_lookup_prices_maps_only_active_starting_price_query_rows() -> None:
    active_price = SimpleNamespace(
        amount_vnd=799_000_000,
        price_type="STARTING_PRICE",
        region_code="VN",
    )
    source, session = _source(FakeResult([(_vehicle(ECO_ID, "Eco"), active_price)]))

    prices = await source.lookup_prices((UUID(ECO_ID), UUID(PLUS_ID)))

    assert [price.model_dump() for price in prices] == [
        {
            "vehicle_id": UUID(ECO_ID),
            "variant_name": "Eco",
            "amount_vnd": Decimal("799000000"),
            "price_type": "STARTING_PRICE",
            "region_code": "VN",
        }
    ]
    compiled = session.statements[0].compile()
    assert "vehicle_prices.status" in str(compiled)
    assert "vehicle_prices.price_type" in str(compiled)
    assert "vehicle_prices.valid_from" in str(compiled)
    assert "vehicle_prices.valid_to" in str(compiled)
    assert "ACTIVE" in compiled.params.values()
    assert "STARTING_PRICE" in compiled.params.values()
    # Giá MUA ĐỨT PIN phải được ưu tiên. Thiếu vế này thì bảng thông số nói giá
    # thuê pin còn bảng chi phí tính theo giá mua đứt — hai con số cho một chiếc.
    assert "BATTERY_INCLUDED" in compiled.params.values()


@pytest.mark.asyncio
async def test_lookup_engine_specs_preserves_values_per_variant() -> None:
    eco = SimpleNamespace(
        motor_power_kw=Decimal("130.5"),
        torque_nm=Decimal("250"),
    )
    plus = SimpleNamespace(
        motor_power_kw=Decimal("150"),
        torque_nm=Decimal("310.25"),
    )
    source, session = _source(
        FakeResult(
            [
                (_vehicle(ECO_ID, "Eco"), eco),
                (_vehicle(PLUS_ID, "Plus"), plus),
            ]
        )
    )

    specs = await source.lookup_engine_specs((UUID(ECO_ID), UUID(PLUS_ID)))

    assert specs is not None
    assert [
        variant.model_dump(include={"variant_name", "motor_power_kw", "torque_nm", "drivetrain"})
        for variant in specs.variants
    ] == [
        {
            "variant_name": "Eco",
            "motor_power_kw": Decimal("130.5"),
            "torque_nm": Decimal("250"),
            "drivetrain": None,
        },
        {
            "variant_name": "Plus",
            "motor_power_kw": Decimal("150"),
            "torque_nm": Decimal("310.25"),
            "drivetrain": None,
        },
    ]
    sql = str(session.statements[0])
    assert "cars.effective_from" in sql
    assert "cars.effective_to" in sql


@pytest.mark.asyncio
async def test_lookup_engine_specs_returns_none_when_every_engine_field_is_empty() -> None:
    empty_spec = SimpleNamespace(motor_power_kw=None, torque_nm=None)
    source, _ = _source(FakeResult([(_vehicle(ECO_ID, "Eco"), empty_spec)]))

    assert await source.lookup_engine_specs((UUID(ECO_ID),)) is None


@pytest.mark.asyncio
async def test_missing_catalog_dimensions_and_colors_return_none_without_querying() -> None:
    source, session = _source()

    assert await source.lookup_dimensions((UUID(ECO_ID),)) is None
    assert await source.lookup_colors((UUID(ECO_ID),)) is None
    assert session.statements == []


@pytest.mark.asyncio
async def test_lookup_facts_uses_the_same_active_catalog_rows() -> None:
    price = SimpleNamespace(amount_vnd=799_000_000)
    car = SimpleNamespace(body_type="SUV", seat_count=5, range_km=Decimal("450"))
    source, session = _source(FakeResult([(_vehicle(ECO_ID, "Eco"), price, car, None)]))

    facts = await source.lookup_facts((UUID(ECO_ID),))

    assert len(facts) == 1
    assert facts[0].vehicle_id == UUID(ECO_ID)
    assert facts[0].display_name == "VinFast VF 7 Eco"
    assert facts[0].starting_price_vnd == Decimal("799000000")
    assert facts[0].specs == {"body_type": "SUV", "seat_count": 5, "range_km": "450"}
    compiled = session.statements[0].compile()
    assert "vehicles.status" in str(compiled)
    assert "vehicle_prices.status" in str(compiled)
    assert "vehicle_prices.valid_from" in str(compiled)
    assert "vehicle_prices.valid_to" in str(compiled)
    assert "cars.effective_from" in str(compiled)
    assert "cars.effective_to" in str(compiled)
    assert "motorbikes.effective_from" in str(compiled)
    assert "STARTING_PRICE" in compiled.params.values()


@pytest.mark.asyncio
async def test_lookup_facts_xe_may_dien_bom_cot_motorbikes_dang_chuoi() -> None:
    """Đợt 9: xe máy điện không có hàng `cars` — thông số phải đọc từ `motorbikes`,
    và là CHUỖI (Decimal làm 503 khi ghi JSON, đã dính trên prod)."""

    bike_vehicle = SimpleNamespace(
        vehicle_id=ECO_ID, vehicle_type="ELECTRIC_MOTORBIKE", brand="VinFast", model_name="Evo", variant_name="Grand"
    )
    price = SimpleNamespace(amount_vnd=21_000_000)
    bike = SimpleNamespace(
        range_max_km=Decimal("262.00"),
        battery_capacity_kwh=Decimal("4.480"),
        battery_type="LFP",
        motor_power_w=1500,
        max_speed_kmh=Decimal("70.00"),
        max_load_kg=Decimal("150.00"),
        charging_time_minutes=360,
        seat_height_mm=Decimal("770.00"),
        license_requirement="A1",
    )
    source, _ = _source(FakeResult([(bike_vehicle, price, None, bike)]))

    facts = await source.lookup_facts((UUID(ECO_ID),))

    specs = facts[0].specs
    assert specs["range_max_km"] == "262.00" and specs["license_requirement"] == "A1"
    assert specs["motor_power_w"] == "1500" and specs["max_speed_kmh"] == "70.00"
    assert all(
        isinstance(value, str) for key, value in specs.items() if value is not None and key not in ("seat_count",)
    )
    assert specs["body_type"] is None and specs["range_km"] is None
