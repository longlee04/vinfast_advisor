"""Regression tests for the current official VinFast car catalog data."""

from __future__ import annotations

from decimal import Decimal

from src.products.domain.values import RecordLifecycleStatus, VehicleStatus, VehicleType
from src.products.infrastructure.csv_import import load_all

OFFICIAL_STARTING_PRICES = {
    "vinfast-vf-2-all-new": 188_000_000,
    "vinfast-vf-3-all-new": 278_000_000,
    "vinfast-vf-5-all-new": 496_000_000,
    "vinfast-vf-6-eco": 646_000_000,
    "vinfast-vf-6-plus": 699_000_000,
    "vinfast-vf-7-all-new": 740_000_000,
    "vinfast-vf-8-all-new": 899_000_000,
    "vinfast-vf-8-eco-extended-range": 898_000_000,
    "vinfast-vf-8-plus-extended-range": 1_079_000_000,
    "vinfast-vf-9-all-new": 1_348_000_000,
}


def test_current_car_prices_match_official_july_2026_policy() -> None:
    dataset = load_all()
    cars = {
        vehicle.vehicle_id: vehicle
        for vehicle in dataset.vehicles
        if vehicle.vehicle_type is VehicleType.CAR and vehicle.status is VehicleStatus.ACTIVE
    }
    active_prices = [
        price for price in dataset.prices if price.vehicle_id in cars and price.status is RecordLifecycleStatus.ACTIVE
    ]

    starting_by_slug = {
        cars[price.vehicle_id].slug: price.amount_vnd for price in active_prices if price.price_type == "STARTING_PRICE"
    }
    included_by_slug = {
        cars[price.vehicle_id].slug: price.amount_vnd
        for price in active_prices
        if price.price_type == "BATTERY_INCLUDED"
    }

    assert starting_by_slug == OFFICIAL_STARTING_PRICES
    assert included_by_slug == OFFICIAL_STARTING_PRICES
    assert not any(price.price_type == "BATTERY_SUBSCRIPTION" for price in active_prices)
    assert "vinfast-vf-wild-all-new" not in starting_by_slug


def test_vf8_specs_match_current_official_variant_sheet() -> None:
    dataset = load_all()
    vehicles_by_id = {vehicle.vehicle_id: vehicle for vehicle in dataset.vehicles}
    specs_by_slug = {
        vehicles_by_id[spec.vehicle_id].slug: spec for spec in dataset.cars if spec.vehicle_id in vehicles_by_id
    }

    eco = specs_by_slug["vinfast-vf-8-eco-extended-range"]
    assert eco.range_km == Decimal("562")
    assert eco.range_cycle == "NEDC"
    assert eco.motor_power_kw == Decimal("150")
    assert eco.torque_nm == Decimal("310")
    assert eco.acceleration_0_100_seconds == Decimal("11.8")
    assert eco.fast_charge_from_percent == 10
    assert eco.fast_charge_to_percent == 70
    assert eco.fast_charge_time_minutes == 31

    plus = specs_by_slug["vinfast-vf-8-plus-extended-range"]
    assert plus.range_km == Decimal("457")
    assert plus.range_cycle == "WLTP"
    assert plus.motor_power_kw == Decimal("300")
    assert plus.torque_nm == Decimal("620")
    assert plus.acceleration_0_100_seconds == Decimal("5.58")
    assert plus.fast_charge_from_percent == 10
    assert plus.fast_charge_to_percent == 70
    assert plus.fast_charge_time_minutes == 31
