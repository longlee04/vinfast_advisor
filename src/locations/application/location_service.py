"""Use case cho module Locations."""

from typing import Final

from src.locations.application.contracts import CategoryCount, LocationPage, RegionEntry
from src.locations.application.ports import LocationStore
from src.locations.domain.errors import InvalidBoundsError
from src.locations.domain.values import BoundingBox, Coordinate

DEFAULT_LIMIT: Final[int] = 500
MAX_LIMIT: Final[int] = 2000
DEFAULT_NEARBY_LIMIT: Final[int] = 50
MAX_NEARBY_LIMIT: Final[int] = 200
DEFAULT_RADIUS_KM: Final[float] = 10.0


def _bounded(value: int, ceiling: int) -> int:
    return min(max(1, value), ceiling)


class LocationService:
    """Chuẩn hoá tham số rồi giao cho store."""

    def __init__(self, store: LocationStore) -> None:
        self._store = store

    async def list_locations(
        self,
        *,
        south: float | None = None,
        north: float | None = None,
        west: float | None = None,
        east: float | None = None,
        types: tuple[str, ...] = (),
        city: str | None = None,
        district: str | None = None,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> LocationPage:
        supplied = [value is not None for value in (south, north, west, east)]
        if any(supplied) and not all(supplied):
            raise InvalidBoundsError("south, north, west and east must be supplied together")
        bounds = BoundingBox.parse(south=south, north=north, west=west, east=east) if all(supplied) else None
        return await self._store.list_in_bounds(
            bounds=bounds,
            types=types,
            city=city,
            district=district,
            query=query,
            limit=_bounded(limit, MAX_LIMIT),
        )

    async def list_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = DEFAULT_RADIUS_KM,
        types: tuple[str, ...] = (),
        limit: int = DEFAULT_NEARBY_LIMIT,
    ) -> LocationPage:
        return await self._store.list_nearby(
            origin=Coordinate.parse(latitude=latitude, longitude=longitude),
            radius_km=Coordinate.validate_radius_km(radius_km),
            types=types,
            limit=_bounded(limit, MAX_NEARBY_LIMIT),
        )

    async def list_categories(self) -> tuple[CategoryCount, ...]:
        return await self._store.count_by_category()

    async def list_regions(self) -> tuple[RegionEntry, ...]:
        return await self._store.list_regions()
