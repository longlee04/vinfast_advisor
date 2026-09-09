"""Port cho Locations persistence."""

from abc import ABC, abstractmethod
from decimal import Decimal

from src.locations.application.contracts import CategoryCount, LocationPage, RegionEntry
from src.locations.domain.values import BoundingBox, Coordinate


class LocationStore(ABC):
    """Nguồn dữ liệu địa điểm."""

    @abstractmethod
    async def list_in_bounds(
        self,
        *,
        bounds: BoundingBox | None,
        types: tuple[str, ...],
        city: str | None,
        district: str | None,
        query: str | None,
        limit: int,
    ) -> LocationPage: ...

    @abstractmethod
    async def list_nearby(
        self,
        *,
        origin: Coordinate,
        radius_km: Decimal,
        types: tuple[str, ...],
        limit: int,
    ) -> LocationPage: ...

    @abstractmethod
    async def count_by_category(self) -> tuple[CategoryCount, ...]: ...

    @abstractmethod
    async def list_regions(self) -> tuple[RegionEntry, ...]: ...
