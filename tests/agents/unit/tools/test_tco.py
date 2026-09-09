"""Golden-vector tests for the deterministic ``vinfast_tco_v1`` tool."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.values import VehicleType
from src.agents.tools.tco import (
    BatteryPolicyInput,
    PromotionInput,
    TcoAssumptionInput,
    VehicleTcoInput,
    vinfast_tco_v1,
)
from src.products.domain.tco import TcoInput, calculate_tco

NOW = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)
CAR_ID = UUID("00000000-0000-0000-0000-000000000001")
MOTORBIKE_ID = UUID("00000000-0000-0000-0000-000000000002")
CAR_ASSUMPTION_ID = UUID("10000000-0000-0000-0000-000000000001")
MOTORBIKE_ASSUMPTION_ID = UUID("10000000-0000-0000-0000-000000000002")


def _car_input() -> VehicleTcoInput:
    return VehicleTcoInput(
        vehicle_type=VehicleType.CAR,
        prices_vnd={"STARTING_PRICE": Decimal("1000000000")},
        promotions=(
            PromotionInput(
                promotion_id=UUID("20000000-0000-0000-0000-000000000001"),
                discount_percent=Decimal("7.5"),
                valid_to=datetime(2026, 12, 31, tzinfo=UTC),
            ),
        ),
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=CAR_ASSUMPTION_ID,
                vehicle_type=VehicleType.CAR,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("3000"),
                registration_fee_percent=Decimal("10"),
                plate_fee_vnd=Decimal("20000000"),
                inspection_fee_vnd=Decimal("340000"),
                inspection_first_month=36,
                inspection_interval_months=24,
                inspection_interval_months_after_7y=12,
                mandatory_insurance_vnd_per_year=Decimal("480700"),
                road_fee_vnd_per_year=Decimal("1560000"),
                maintenance_vnd_per_service=Decimal("1200000"),
                maintenance_interval_km=Decimal("15000"),
                source_note="Bộ giả định CAR/VN đã duyệt",
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("15.5"),
    )


def _motorbike_input() -> VehicleTcoInput:
    return VehicleTcoInput(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        prices_vnd={"STARTING_PRICE": Decimal("30000000")},
        promotions=(
            PromotionInput(
                promotion_id=UUID("20000000-0000-0000-0000-000000000002"),
                discount_amount_vnd=Decimal("2000000"),
                valid_to=datetime(2026, 10, 31, tzinfo=UTC),
            ),
        ),
        battery_policy=BatteryPolicyInput(
            ownership_model="SUBSCRIPTION",
            monthly_fee_vnd=Decimal("350000"),
        ),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=MOTORBIKE_ASSUMPTION_ID,
                vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("3000"),
                registration_fee_flat_vnd=Decimal("600000"),
                plate_fee_vnd=Decimal("500000"),
                mandatory_insurance_vnd_per_year=Decimal("66000"),
                road_fee_vnd_per_year=Decimal("0"),
                maintenance_vnd_per_service=Decimal("200000"),
                maintenance_interval_km=Decimal("4000"),
                source_note="Bộ giả định xe máy điện/VN đã duyệt",
            ),
        ),
        battery_capacity_kwh=Decimal("3.5"),
        battery_quantity=2,
        range_max_km=Decimal("140"),
    )


def test_car_golden_vector_matches_every_component_to_the_vnd() -> None:
    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("50"),
        data=_car_input(),
        computed_at=NOW,
    )

    assert result.unavailable_reason is None
    assert result.monthly_distance_km == Decimal("1500")
    assert result.components_vnd == {
        "promoted_purchase_price_vnd": Decimal("1000000000"),
        "rolling_fees_vnd": Decimal("130883500"),
        "energy_vnd": Decimal("41850000"),
        "battery_vnd": Decimal("0"),
        "scheduled_maintenance_vnd": Decimal("7200000"),
    }
    assert result.total_vnd == Decimal("1179933500")


def test_agent_adapter_matches_the_canonical_product_calculator() -> None:
    """The Agent may reshape the result but must not maintain a second formula."""

    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("50"),
        data=_car_input(),
        computed_at=NOW,
    )
    canonical = calculate_tco(
        TcoInput(
            vehicle_price_vnd=Decimal("1000000000"),
            monthly_km=Decimal("1500"),
            years=5,
            kwh_per_100km=Decimal("15.5"),
            electricity_vnd_per_kwh=Decimal("3000"),
            registration_fee_percent=Decimal("10"),
            registration_fee_flat_vnd=Decimal("0"),
            plate_fee_vnd=Decimal("20000000"),
            inspection_fee_vnd=Decimal("340000"),
            inspection_first_month=36,
            inspection_interval_months=24,
            inspection_interval_months_after_7y=12,
            insurance_vnd_per_year=Decimal("480700"),
            road_fee_vnd_per_year=Decimal("1560000"),
            maintenance_vnd_per_service=Decimal("1200000"),
            maintenance_interval_km=Decimal("15000"),
        )
    )

    assert result.total_vnd == canonical.total_ownership_vnd
    assert result.components_vnd["energy_vnd"] == canonical.electricity_vnd
    assert result.components_vnd["scheduled_maintenance_vnd"] == canonical.maintenance_vnd


def test_electric_motorbike_golden_vector_derives_consumption_and_matches_to_the_vnd() -> None:
    result = vinfast_tco_v1(
        vehicle_id=MOTORBIKE_ID,
        daily_distance_km=Decimal("40"),
        data=_motorbike_input(),
        computed_at=NOW,
    )

    assert result.unavailable_reason is None
    assert result.monthly_distance_km == Decimal("1200")
    assert result.energy_consumption_kwh_per_100km == Decimal("2.500")
    assert result.energy_consumption_derived is True
    assert result.components_vnd == {
        "promoted_purchase_price_vnd": Decimal("30000000"),
        "rolling_fees_vnd": Decimal("1430000"),
        "energy_vnd": Decimal("5400000"),
        "battery_vnd": Decimal("0"),
        "scheduled_maintenance_vnd": Decimal("3600000"),
    }
    assert result.total_vnd == Decimal("40430000")


def test_changed_daily_distance_recalculates_monthly_distance_and_energy_without_stale_value() -> None:
    first = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("10"),
        data=_car_input(),
        computed_at=NOW,
    )
    second = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("20"),
        data=_car_input(),
        computed_at=NOW,
    )

    assert first.monthly_distance_km == Decimal("300")
    assert second.monthly_distance_km == Decimal("600")
    assert second.components_vnd["energy_vnd"] == first.components_vnd["energy_vnd"] * 2


def test_included_battery_price_never_double_counts_battery_policy_amounts() -> None:
    data = replace(
        _car_input(),
        prices_vnd={
            "STARTING_PRICE": Decimal("700000000"),
            "BATTERY_INCLUDED_PRICE": Decimal("800000000"),
        },
        promotions=(),
        battery_policy=BatteryPolicyInput(
            ownership_model="INCLUDED",
            monthly_fee_vnd=Decimal("1000000"),
            purchase_price_vnd=Decimal("150000000"),
        ),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=CAR_ASSUMPTION_ID,
                vehicle_type=VehicleType.CAR,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("3000"),
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("10"),
    )

    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("10"),
        data=data,
        computed_at=NOW,
    )

    assert result.components_vnd["promoted_purchase_price_vnd"] == Decimal("800000000")
    assert result.components_vnd["battery_vnd"] == Decimal("0")
    assert result.total_vnd == Decimal("805400000")


def test_motorbike_without_consumption_or_derivation_fields_returns_tco_unavailable() -> None:
    data = replace(
        _motorbike_input(),
        energy_consumption_kwh_per_100km=None,
        battery_capacity_kwh=None,
        battery_quantity=None,
        range_max_km=None,
    )

    result = vinfast_tco_v1(
        vehicle_id=MOTORBIKE_ID,
        daily_distance_km=Decimal("40"),
        data=data,
        computed_at=NOW,
    )

    assert result.total_vnd is None
    assert result.components_vnd == {}
    assert result.unavailable_reason is not None
    assert "battery_capacity_kwh" in result.unavailable_reason
    assert "range_max_km" in result.unavailable_reason


def test_promotions_are_not_applied_to_the_stable_catalog_tco() -> None:
    earliest = datetime(2026, 9, 1, tzinfo=UTC)
    winning_id = UUID("20000000-0000-0000-0000-00000000000a")
    data = replace(
        _car_input(),
        prices_vnd={"STARTING_PRICE": Decimal("100000000")},
        promotions=(
            PromotionInput(
                promotion_id=UUID("20000000-0000-0000-0000-00000000000c"),
                discount_amount_vnd=Decimal("10000000"),
                valid_to=datetime(2026, 10, 1, tzinfo=UTC),
            ),
            PromotionInput(
                promotion_id=UUID("20000000-0000-0000-0000-00000000000b"),
                discount_amount_vnd=Decimal("10000000"),
                valid_to=earliest,
            ),
            PromotionInput(
                promotion_id=winning_id,
                discount_percent=Decimal("10"),
                valid_to=earliest,
            ),
        ),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=CAR_ASSUMPTION_ID,
                vehicle_type=VehicleType.CAR,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("0"),
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("10"),
    )

    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("0"),
        data=data,
        computed_at=NOW,
    )

    assert result.components_vnd["promoted_purchase_price_vnd"] == Decimal("100000000")
    assert result.selected_promotion_id is None


def test_half_up_rounds_each_component_before_total_is_added() -> None:
    data = VehicleTcoInput(
        vehicle_type=VehicleType.CAR,
        prices_vnd={"STARTING_PRICE": Decimal("100")},
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=CAR_ASSUMPTION_ID,
                vehicle_type=VehicleType.CAR,
                region_code="VN",
                electricity_vnd_per_kwh=Decimal("1"),
                registration_fee_percent=Decimal("0.5"),
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("0.02777777777777777777777777778"),
    )

    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("1"),
        data=data,
        computed_at=NOW,
    )

    assert result.components_vnd["rolling_fees_vnd"] == Decimal("1")
    assert result.components_vnd["energy_vnd"] == Decimal("1")
    assert result.total_vnd == Decimal("102")


def test_missing_active_assumption_returns_tco_unavailable_instead_of_guessing() -> None:
    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("10"),
        data=replace(_car_input(), assumptions=()),
        computed_at=NOW,
    )

    assert result.total_vnd is None
    assert result.unavailable_reason == "TCO_UNAVAILABLE: expected exactly one ACTIVE tco_assumptions row, got 0"


def test_historical_purchase_policy_does_not_add_a_separate_battery_cost() -> None:
    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("10"),
        data=replace(
            _car_input(),
            battery_policy=BatteryPolicyInput(ownership_model="PURCHASE"),
        ),
        computed_at=NOW,
    )

    assert result.unavailable_reason is None
    assert result.components_vnd["battery_vnd"] == Decimal("0")


def test_negative_daily_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="daily_distance_km"):
        vinfast_tco_v1(
            vehicle_id=CAR_ID,
            daily_distance_km=Decimal("-1"),
            data=_car_input(),
            computed_at=NOW,
        )


def test_available_result_includes_assumption_table_timestamp_and_required_warning() -> None:
    result = vinfast_tco_v1(
        vehicle_id=CAR_ID,
        daily_distance_km=Decimal("50"),
        data=_car_input(),
        computed_at=NOW,
    )

    assert result.computed_at == NOW
    assert result.warning == "Đây là ước tính, không phải báo giá cuối cùng."
    assert {line.code for line in result.assumption_lines} >= {
        "daily_distance_km",
        "days_per_month",
        "monthly_distance_km",
        "horizon_months",
        "energy_consumption_kwh_per_100km",
        "electricity_vnd_per_kwh",
    }
