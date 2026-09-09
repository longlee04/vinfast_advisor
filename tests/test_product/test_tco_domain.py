"""Công thức TCO thuần, đối chiếu vector tính tay."""

from decimal import Decimal

import pytest

from src.products.domain.tco import (
    TcoInput,
    calculate_tco,
    count_inspections,
    derive_consumption,
    resolve_region_code,
)


def car_input(**overrides) -> TcoInput:
    base = dict(
        vehicle_price_vnd=Decimal("646000000"),
        monthly_km=Decimal("1000"),
        years=5,
        kwh_per_100km=Decimal("12.3"),
        electricity_vnd_per_kwh=Decimal("3150"),
        registration_fee_percent=Decimal("0.00"),
        registration_fee_flat_vnd=Decimal("0"),
        plate_fee_vnd=Decimal("14000000"),
        inspection_fee_vnd=Decimal("290000"),
        inspection_first_month=36,
        inspection_interval_months=24,
        inspection_interval_months_after_7y=12,
        insurance_vnd_per_year=Decimal("480000"),
        road_fee_vnd_per_year=Decimal("1560000"),
        maintenance_vnd_per_service=Decimal("1500000"),
        maintenance_interval_km=Decimal("12000"),
    )
    base.update(overrides)
    return TcoInput(**base)


def test_car_five_years_matches_hand_calculation() -> None:
    result = calculate_tco(car_input())

    # 1000 km/tháng × 60 tháng = 60.000 km
    # điện: 60000 / 100 × 12,3 × 3150 = 23.247.000
    # bảo dưỡng: ceil(60000 / 12000) = 5 lần × 1.500.000 = 7.500.000
    # đăng kiểm: mốc tháng 36 và 60 = 2 lần × 290.000 = 580.000
    # bảo hiểm: 480.000 × 5 = 2.400.000
    # đường bộ: 1.560.000 × 5 = 7.800.000
    # trước bạ: 646.000.000 × 0% = 0
    # upfront: 646.000.000 + 0 + 14.000.000 = 660.000.000
    assert result.electricity_vnd == Decimal("23247000")
    assert result.maintenance_count == 5
    assert result.maintenance_vnd == Decimal("7500000")
    assert result.inspection_count == 2
    assert result.inspection_vnd == Decimal("580000")
    assert result.insurance_vnd == Decimal("2400000")
    assert result.road_fee_vnd == Decimal("7800000")
    assert result.registration_fee_vnd == Decimal("0")
    assert result.total_upfront_vnd == Decimal("660000000")
    assert result.total_ownership_vnd == Decimal("701527000")


def test_electric_car_registration_fee_is_zero() -> None:
    result = calculate_tco(car_input())

    assert result.registration_fee_vnd == Decimal("0")


def test_motorbike_pays_two_percent_registration_and_uses_zero_inspection_assumption() -> None:
    result = calculate_tco(
        car_input(
            vehicle_price_vnd=Decimal("22500000"),
            kwh_per_100km=Decimal("1.7"),
            registration_fee_percent=Decimal("2.00"),
            plate_fee_vnd=Decimal("2000000"),
            inspection_fee_vnd=Decimal("0"),
            inspection_first_month=0,
            inspection_interval_months=0,
            inspection_interval_months_after_7y=0,
            insurance_vnd_per_year=Decimal("66000"),
            road_fee_vnd_per_year=Decimal("0"),
            maintenance_vnd_per_service=Decimal("200000"),
            maintenance_interval_km=Decimal("5000"),
        )
    )

    assert result.registration_fee_vnd == Decimal("450000")
    assert result.inspection_count == 0
    assert result.inspection_vnd == Decimal("0")


def test_maintenance_rounds_up_past_the_interval() -> None:
    result = calculate_tco(car_input(monthly_km=Decimal("1000.0167"), maintenance_interval_km=Decimal("12000")))

    # 60.001 km với chu kỳ 12.000 km cần 6 lần, không phải 5
    assert result.maintenance_count == 6


def test_exactly_on_the_interval_does_not_add_a_service() -> None:
    result = calculate_tco(car_input(monthly_km=Decimal("200"), maintenance_interval_km=Decimal("12000")))

    # 200 × 60 = 12.000 km chẵn, đúng 1 lần
    assert result.maintenance_count == 1


@pytest.mark.parametrize(
    ("months", "expected"),
    [(12, 0), (30, 0), (36, 1), (48, 1), (60, 2), (84, 3), (96, 3), (108, 4), (120, 5)],
)
def test_inspection_schedule_follows_the_legal_cycle(months: int, expected: int) -> None:
    assert count_inspections(months=months, first_month=36, interval_months=24, interval_after_7y=12) == expected


def test_zero_inspection_schedule_excludes_the_unmodelled_cost() -> None:
    assert count_inspections(months=120, first_month=0, interval_months=0, interval_after_7y=0) == 0


def test_consumption_is_derived_from_battery_over_range() -> None:
    derived = derive_consumption(
        published_kwh_per_100km=None,
        battery_capacity_kwh=Decimal("3.5"),
        range_km=Decimal("203"),
    )

    assert derived == Decimal("1.724")


def test_published_consumption_wins_over_derivation() -> None:
    derived = derive_consumption(
        published_kwh_per_100km=Decimal("13.0"),
        battery_capacity_kwh=Decimal("59.6"),
        range_km=Decimal("485"),
    )

    assert derived == Decimal("13.0")


def test_consumption_is_none_when_nothing_can_be_derived() -> None:
    assert derive_consumption(published_kwh_per_100km=None, battery_capacity_kwh=None, range_km=Decimal("203")) is None


def test_consumption_is_none_when_range_is_zero() -> None:
    assert (
        derive_consumption(
            published_kwh_per_100km=None,
            battery_capacity_kwh=Decimal("3.5"),
            range_km=Decimal("0"),
        )
        is None
    )


def test_hanoi_and_hcmc_resolve_to_khu_vuc_i() -> None:
    assert resolve_region_code("Hà Nội") == "KHU_VUC_I"
    assert resolve_region_code("Hồ Chí Minh") == "KHU_VUC_I"


def test_other_provinces_resolve_to_khu_vuc_ii() -> None:
    assert resolve_region_code("Khánh Hòa") == "KHU_VUC_II"
    assert resolve_region_code("Cần Thơ") == "KHU_VUC_II"


def test_unknown_province_name_defaults_to_khu_vuc_ii_without_raising() -> None:
    """Validate tên tỉnh là việc của tầng trích slot, không phải của hàm thuần."""

    assert resolve_region_code("Xyz Không Tồn Tại") == "KHU_VUC_II"


def test_surrounding_whitespace_does_not_change_the_region() -> None:
    """Tên tỉnh đi từ dropdown/LLM thường kèm khoảng trắng thừa."""

    assert resolve_region_code("  Hà Nội  ") == "KHU_VUC_I"
