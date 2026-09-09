"""Hệ số thẻ chi phí phải dựng lại ĐÚNG tổng máy chủ vừa tính.

Đây là hợp đồng client dựa vào để kéo thanh trượt số km mà không phải chờ một
lượt chat. Lệch ở đây nghĩa là khách thấy hai con số khác nhau trong cùng một
màn hình — và con số họ đem đi so với đại lý là con số nào thì không ai biết.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

import pytest

from src.agents.core.act import build_tco_card, build_tco_rates
from src.agents.domain.values import VehicleType
from src.agents.tools.tco import (
    BatteryPolicyInput,
    TcoAssumptionInput,
    VehicleTcoInput,
    vinfast_tco_v1,
)

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
CAR_ID = UUID("00000000-0000-0000-0000-000000000001")
BIKE_ID = UUID("00000000-0000-0000-0000-000000000002")


def _car() -> VehicleTcoInput:
    return VehicleTcoInput(
        vehicle_type=VehicleType.CAR,
        prices_vnd={"STARTING_PRICE": Decimal("1000000000")},
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=UUID("10000000-0000-0000-0000-000000000001"),
                vehicle_type=VehicleType.CAR,
                region_code="KHU_VUC_I",
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
                source_note="Bộ giả định CAR đã duyệt",
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("15.5"),
    )


def _bike() -> VehicleTcoInput:
    return VehicleTcoInput(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        prices_vnd={"STARTING_PRICE": Decimal("30000000"), "BATTERY_SUBSCRIPTION": Decimal("24000000")},
        battery_policy=BatteryPolicyInput(ownership_model="SUBSCRIPTION", monthly_fee_vnd=Decimal("350000")),
        assumptions=(
            TcoAssumptionInput(
                assumption_id=UUID("10000000-0000-0000-0000-000000000002"),
                vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
                region_code="KHU_VUC_II",
                electricity_vnd_per_kwh=Decimal("3000"),
                registration_fee_flat_vnd=Decimal("600000"),
                plate_fee_vnd=Decimal("500000"),
                mandatory_insurance_vnd_per_year=Decimal("66000"),
                road_fee_vnd_per_year=Decimal("0"),
                maintenance_vnd_per_service=Decimal("200000"),
                maintenance_interval_km=Decimal("4000"),
                source_note="Bộ giả định xe máy điện đã duyệt",
            ),
        ),
        energy_consumption_kwh_per_100km=Decimal("3.5"),
    )


def _client_total(rates, daily_km: float) -> Decimal:
    """ĐÚNG phép tính client sẽ chạy — chép từ docstring `TcoRatesView`."""

    km = Decimal(str(daily_km)) * rates.days_per_year * rates.years
    interval = Decimal(rates.maintenance_interval_km)
    services = 0
    if interval > 0:
        services = int((km / interval).to_integral_value(rounding=ROUND_CEILING))
    return (
        Decimal(rates.fixed_vnd)
        + Decimal(rates.energy_vnd_per_km) * km
        + Decimal(rates.insurance_vnd_per_year) * rates.years
        + Decimal(rates.maintenance_vnd_per_service) * services
        + Decimal(rates.battery_vnd_per_month) * 12 * rates.years
    )


@pytest.mark.parametrize("daily_km", [10.0, 30.0, 55.5, 120.0])
@pytest.mark.parametrize(
    ("vehicle_id", "data", "plan"), [(CAR_ID, _car(), "INCLUDED"), (BIKE_ID, _bike(), "SUBSCRIPTION")]
)
def test_cong_thuc_client_ra_dung_tong_may_chu(
    daily_km: float, vehicle_id: UUID, data: VehicleTcoInput, plan: str
) -> None:
    result = vinfast_tco_v1(
        vehicle_id=vehicle_id,
        daily_distance_km=Decimal(str(daily_km)),
        data=data,
        computed_at=NOW,
        battery_plan=plan,  # type: ignore[arg-type]
    )
    rates = build_tco_rates(result, daily_km=daily_km)
    assert rates is not None
    assert abs(_client_total(rates, daily_km) - Decimal(str(result.total_vnd))) <= 1000


def test_the_chi_phi_co_du_khoan_muc_va_he_so() -> None:
    result = vinfast_tco_v1(vehicle_id=CAR_ID, daily_distance_km=Decimal("30"), data=_car(), computed_at=NOW)
    card = build_tco_card(
        result,
        vehicle_id=str(CAR_ID),
        vehicle_name="VinFast VF 8",
        daily_km=30.0,
        known_distance=False,
        province="HN",
    )
    assert card.total_vnd == str(result.total_vnd)
    assert {item.code for item in card.components} >= {"promoted_purchase_price_vnd", "energy_vnd"}
    assert card.region_code == "KHU_VUC_I"
    assert card.province_options  # gửi kèm để ô chọn không phụ thuộc một lần gọi mạng thứ hai
    assert "tạm tính" in card.assumption_note
    assert card.rates is not None and card.rates.days_per_year == 360


def test_khong_du_du_lieu_thi_khong_bia_he_so() -> None:
    class Tho:
        total_vnd = Decimal("1000")
        components_vnd: dict = {}
        breakdown_detail = None

    assert build_tco_rates(Tho(), daily_km=30.0) is None
