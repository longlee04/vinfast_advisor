"""Service Locations chuẩn hoá tham số trước khi chạm repository."""

from decimal import Decimal

import pytest

from src.locations.application.contracts import LocationPage
from src.locations.application.location_service import LocationService
from src.locations.domain.errors import InvalidBoundsError, InvalidRadiusError


class FakeStore:
    def __init__(self) -> None:
        self.last_call: dict = {}

    async def list_in_bounds(self, **kwargs) -> LocationPage:
        self.last_call = kwargs
        return LocationPage(items=(), total=0, truncated=False)

    async def list_nearby(self, **kwargs) -> LocationPage:
        self.last_call = kwargs
        return LocationPage(items=(), total=0, truncated=False)

    async def count_by_category(self):
        return ()

    async def list_regions(self):
        return ()


@pytest.mark.asyncio
async def test_limit_is_capped_at_two_thousand() -> None:
    store = FakeStore()
    service = LocationService(store)

    await service.list_locations(limit=99999)

    assert store.last_call["limit"] == 2000


@pytest.mark.asyncio
async def test_limit_below_one_becomes_one() -> None:
    store = FakeStore()
    service = LocationService(store)

    await service.list_locations(limit=0)

    assert store.last_call["limit"] == 1


@pytest.mark.asyncio
async def test_partial_bounds_are_rejected() -> None:
    service = LocationService(FakeStore())

    with pytest.raises(InvalidBoundsError):
        await service.list_locations(south=10.0, north=11.0)


@pytest.mark.asyncio
async def test_complete_bounds_are_passed_through() -> None:
    store = FakeStore()
    service = LocationService(store)

    await service.list_locations(south=10.0, north=11.0, west=106.0, east=107.0)

    assert store.last_call["bounds"] is not None


@pytest.mark.asyncio
async def test_nearby_rejects_a_radius_over_the_ceiling() -> None:
    service = LocationService(FakeStore())

    with pytest.raises(InvalidRadiusError):
        await service.list_nearby(latitude=21.0, longitude=105.0, radius_km=500.0)


@pytest.mark.asyncio
async def test_nearby_limit_is_capped_at_two_hundred() -> None:
    store = FakeStore()
    service = LocationService(store)

    await service.list_nearby(latitude=21.0, longitude=105.0, radius_km=10.0, limit=9999)

    assert store.last_call["limit"] == 200
    assert store.last_call["radius_km"] == Decimal("10.0")
