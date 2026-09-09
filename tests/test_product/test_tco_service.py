"""Service TCO chọn đúng loại giá và báo thiếu dữ liệu thay vì đoán."""

from decimal import Decimal

import pytest

from src.products.application.tco_service import TcoService, TcoUnavailableError
from src.products.domain.errors import ProductNotFoundError


class FakeTcoRepository:
    def __init__(self, snapshot: dict | None) -> None:
        self._snapshot = snapshot

    async def get_tco_snapshot(self, identifier: str, *, region_code: str) -> dict | None:
        return self._snapshot


def car_snapshot(**overrides) -> dict:
    base = {
        "vehicle_id": "veh-1",
        "vehicle_type": "CAR",
        "prices": {"BATTERY_INCLUDED": Decimal("646000000"), "STARTING_PRICE": Decimal("600000000")},
        "energy_consumption_kwh_per_100km": Decimal("12.3"),
        "battery_capacity_kwh": Decimal("59.6"),
        "range_km": Decimal("485"),
        "assumptions": {
            "region_code": "KHU_VUC_II",
            "assumption_version": 3,
            "electricity_vnd_per_kwh": Decimal("3150"),
            "registration_fee_percent": Decimal("0.00"),
            "registration_fee_flat_vnd": Decimal("0"),
            "plate_fee_vnd": Decimal("14000000"),
            "inspection_fee_vnd": Decimal("290000"),
            "inspection_first_month": 36,
            "inspection_interval_months": 24,
            "inspection_interval_months_after_7y": 12,
            "mandatory_insurance_vnd_per_year": Decimal("480000"),
            "road_fee_vnd_per_year": Decimal("1560000"),
            "maintenance_vnd_per_service": Decimal("1500000"),
            "maintenance_interval_km": Decimal("12000"),
            "horizon_months": 60,
            "source_note": "nguồn mẫu",
        },
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_battery_included_price_wins() -> None:
    service = TcoService(FakeTcoRepository(car_snapshot()))

    estimate = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")

    assert estimate.price_type == "BATTERY_INCLUDED"
    assert estimate.breakdown.vehicle_price_vnd == Decimal("646000000")


@pytest.mark.asyncio
async def test_starting_price_is_used_when_battery_included_is_absent() -> None:
    snapshot = car_snapshot(prices={"STARTING_PRICE": Decimal("22500000")})
    service = TcoService(FakeTcoRepository(snapshot))

    estimate = await service.estimate("veh-1", monthly_km=Decimal("500"), years=5, region_code="KHU_VUC_II")

    assert estimate.price_type == "STARTING_PRICE"
    assert estimate.breakdown.vehicle_price_vnd == Decimal("22500000")


@pytest.mark.asyncio
async def test_promotion_and_subscription_prices_are_never_chosen() -> None:
    snapshot = car_snapshot(
        prices={
            "PROMOTION_PRICE": Decimal("1"),
            "BATTERY_SUBSCRIPTION": Decimal("2"),
            "STARTING_PRICE": Decimal("500000000"),
        }
    )
    service = TcoService(FakeTcoRepository(snapshot))

    estimate = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")

    assert estimate.price_type == "STARTING_PRICE"


@pytest.mark.asyncio
async def test_published_consumption_is_reported_as_published() -> None:
    service = TcoService(FakeTcoRepository(car_snapshot()))

    estimate = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")

    assert estimate.consumption_source == "published"
    assert estimate.derivation is None


@pytest.mark.asyncio
async def test_derived_consumption_explains_itself() -> None:
    snapshot = car_snapshot(energy_consumption_kwh_per_100km=None)
    service = TcoService(FakeTcoRepository(snapshot))

    estimate = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")

    assert estimate.consumption_source == "derived"
    assert "59.6" in estimate.derivation
    assert "485" in estimate.derivation


@pytest.mark.asyncio
async def test_missing_vehicle_raises_not_found() -> None:
    service = TcoService(FakeTcoRepository(None))

    with pytest.raises(ProductNotFoundError):
        await service.estimate("khong-ton-tai", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")


@pytest.mark.asyncio
async def test_no_usable_price_is_unavailable_not_a_guess() -> None:
    snapshot = car_snapshot(prices={"PROMOTION_PRICE": Decimal("1")})
    service = TcoService(FakeTcoRepository(snapshot))

    with pytest.raises(TcoUnavailableError):
        await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")


@pytest.mark.asyncio
async def test_no_consumption_data_is_unavailable() -> None:
    snapshot = car_snapshot(energy_consumption_kwh_per_100km=None, battery_capacity_kwh=None, range_km=None)
    service = TcoService(FakeTcoRepository(snapshot))

    with pytest.raises(TcoUnavailableError):
        await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")


@pytest.mark.asyncio
async def test_missing_assumptions_is_unavailable() -> None:
    snapshot = car_snapshot(assumptions=None)
    service = TcoService(FakeTcoRepository(snapshot))

    with pytest.raises(TcoUnavailableError):
        await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")


@pytest.mark.asyncio
async def test_different_region_uses_a_different_plate_fee() -> None:
    """Hai khu vực chênh nhau 100 lần ở lệ phí biển số.

    Dùng chung một dòng giả định cho cả nước nghĩa là mọi khách ngoài Hà
    Nội/TP.HCM đọc được con số cao hơn thực tế gần 14 triệu.
    """

    class RegionAwareRepo:
        async def get_tco_snapshot(self, identifier, *, region_code):
            snapshot = car_snapshot()
            snapshot["assumptions"]["plate_fee_vnd"] = (
                Decimal("14000000") if region_code == "KHU_VUC_I" else Decimal("140000")
            )
            snapshot["assumptions"]["region_code"] = region_code
            return snapshot

    service = TcoService(RegionAwareRepo())

    hanoi = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_I")
    other = await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_II")

    assert hanoi.breakdown.plate_fee_vnd == Decimal("14000000")
    assert other.breakdown.plate_fee_vnd == Decimal("140000")
    assert hanoi.breakdown.total_ownership_vnd - other.breakdown.total_ownership_vnd == Decimal("13860000")


@pytest.mark.asyncio
async def test_a_region_without_assumptions_is_unavailable_not_a_fallback() -> None:
    """Không có dòng cho vùng đó thì báo thiếu, KHÔNG rơi về dòng vùng khác."""

    class EmptyRegionRepo:
        async def get_tco_snapshot(self, identifier, *, region_code):
            snapshot = car_snapshot()
            snapshot["assumptions"] = None
            return snapshot

    service = TcoService(EmptyRegionRepo())

    with pytest.raises(TcoUnavailableError, match="KHU_VUC_I"):
        await service.estimate("veh-1", monthly_km=Decimal("1000"), years=5, region_code="KHU_VUC_I")
