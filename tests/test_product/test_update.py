"""PATCH cap nhat vehicle — partial update, khong ghi de field khong gui."""

from __future__ import annotations

import pytest

from src.products.application.vehicle_service import VehicleCatalogService
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.values import RecordLifecycleStatus, VehicleStatus
from tests.test_product.test_services import FakeVehicleRepository, _car_detail


@pytest.mark.asyncio
async def test_update_changes_only_supplied_fields() -> None:
    repo = FakeVehicleRepository()
    original = _car_detail("v-1")
    repo.add_vehicle(original)
    service = VehicleCatalogService(repo)

    result = await service.update_vehicle("v-1", {"model_name": "VF 9"}, is_admin=True)

    assert result.vehicle.model_name == "VF 9"
    # Field khong gui phai giu nguyen — day la diem cot loi cua partial update.
    assert result.vehicle.brand == original.vehicle.brand
    assert result.vehicle.slug == original.vehicle.slug


@pytest.mark.asyncio
async def test_update_ignores_none_values() -> None:
    repo = FakeVehicleRepository()
    original = _car_detail("v-1")
    repo.add_vehicle(original)
    service = VehicleCatalogService(repo)

    result = await service.update_vehicle("v-1", {"model_name": None, "brand": "VinFast Moi"}, is_admin=True)

    assert result.vehicle.model_name == original.vehicle.model_name
    assert result.vehicle.brand == "VinFast Moi"


@pytest.mark.asyncio
async def test_update_can_change_status() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    result = await service.update_vehicle("v-1", {"status": "INACTIVE"}, is_admin=True)

    assert result.vehicle.status is VehicleStatus.INACTIVE


@pytest.mark.asyncio
async def test_update_rejects_invalid_status() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    with pytest.raises(ValueError):
        await service.update_vehicle("v-1", {"status": "KHONG_TON_TAI"}, is_admin=True)


@pytest.mark.asyncio
async def test_update_requires_admin() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    with pytest.raises(ProductPermissionError):
        await service.update_vehicle("v-1", {"brand": "X"}, is_admin=False)


@pytest.mark.asyncio
async def test_update_missing_vehicle_raises_not_found() -> None:
    service = VehicleCatalogService(FakeVehicleRepository())

    with pytest.raises(ProductNotFoundError):
        await service.update_vehicle("khong-ton-tai", {"brand": "X"}, is_admin=True)


@pytest.mark.asyncio
async def test_update_with_empty_payload_is_noop() -> None:
    repo = FakeVehicleRepository()
    original = _car_detail("v-1")
    repo.add_vehicle(original)
    service = VehicleCatalogService(repo)

    result = await service.update_vehicle("v-1", {}, is_admin=True)

    assert result.vehicle.brand == original.vehicle.brand
    assert result.vehicle.model_name == original.vehicle.model_name


@pytest.mark.asyncio
async def test_replace_prices_expires_old_and_activates_new() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    result = await service.replace_vehicle_prices(
        "v-1",
        [{"price_type": "LISTED", "amount_vnd": 1_200_000_000, "currency": "VND"}],
        is_admin=True,
    )

    active = [p for p in result.prices if p.status is RecordLifecycleStatus.ACTIVE]
    assert len(active) == 1
    assert active[0].amount_vnd == 1_200_000_000
    # Gia cu khong bi xoa — chi chuyen sang EXPIRED de giu lich su.
    assert any(p.status is RecordLifecycleStatus.EXPIRED for p in result.prices)


@pytest.mark.asyncio
async def test_replace_prices_requires_admin() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    with pytest.raises(ProductPermissionError):
        await service.replace_vehicle_prices("v-1", [], is_admin=False)


@pytest.mark.asyncio
async def test_replace_prices_rejects_negative_amount() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    with pytest.raises(ValueError):
        await service.replace_vehicle_prices("v-1", [{"price_type": "LISTED", "amount_vnd": -1}], is_admin=True)


@pytest.mark.asyncio
async def test_replace_prices_missing_vehicle_raises_not_found() -> None:
    service = VehicleCatalogService(FakeVehicleRepository())

    with pytest.raises(ProductNotFoundError):
        await service.replace_vehicle_prices(
            "khong-ton-tai", [{"price_type": "LISTED", "amount_vnd": 1}], is_admin=True
        )
