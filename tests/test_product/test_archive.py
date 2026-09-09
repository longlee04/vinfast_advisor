"""Archive thay hard delete — docs/vehicle-catalog-schema.md §6.5."""

from __future__ import annotations

import pytest

from src.products.application import PageParams
from src.products.application.vehicle_service import VehicleCatalogService
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.values import VehicleStatus
from tests.test_product.test_services import FakeVehicleRepository, _car_detail


@pytest.mark.asyncio
async def test_archive_sets_status_and_keeps_row() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    result = await service.archive_vehicle("v-1", is_admin=True)

    assert result.vehicle.status is VehicleStatus.ARCHIVED
    # Bản ghi vẫn còn — đây là điểm khác cốt lõi so với hard delete cũ.
    assert await repo.get_vehicle("v-1") is not None


@pytest.mark.asyncio
async def test_archived_vehicle_disappears_from_public_list() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)
    await service.archive_vehicle("v-1", is_admin=True)

    items = await service.list_active_vehicles(PageParams(skip=0, limit=10))

    assert items == []


@pytest.mark.asyncio
async def test_restore_brings_vehicle_back_to_active() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)
    await service.archive_vehicle("v-1", is_admin=True)

    result = await service.restore_vehicle("v-1", is_admin=True)

    assert result.vehicle.status is VehicleStatus.ACTIVE
    items = await service.list_active_vehicles(PageParams(skip=0, limit=10))
    assert len(items) == 1


@pytest.mark.asyncio
async def test_archive_requires_admin() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    with pytest.raises(ProductPermissionError):
        await service.archive_vehicle("v-1", is_admin=False)


@pytest.mark.asyncio
async def test_archive_missing_vehicle_raises_not_found() -> None:
    service = VehicleCatalogService(FakeVehicleRepository())

    with pytest.raises(ProductNotFoundError):
        await service.archive_vehicle("khong-ton-tai", is_admin=True)


@pytest.mark.asyncio
async def test_archive_is_idempotent() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-1"))
    service = VehicleCatalogService(repo)

    await service.archive_vehicle("v-1", is_admin=True)
    result = await service.archive_vehicle("v-1", is_admin=True)

    assert result.vehicle.status is VehicleStatus.ARCHIVED
