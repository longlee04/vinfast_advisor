"""Value objects for the Locations domain.

Every value is validated at construction, so a `BoundingBox` that exists is a
window that can actually be queried. The repository therefore never has to
re-check its arguments.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from src.locations.domain.errors import InvalidBoundsError, InvalidRadiusError

MAX_RADIUS_KM: Final[Decimal] = Decimal("50")
MIN_LATITUDE: Final[Decimal] = Decimal("-90")
MAX_LATITUDE: Final[Decimal] = Decimal("90")
MIN_LONGITUDE: Final[Decimal] = Decimal("-180")
MAX_LONGITUDE: Final[Decimal] = Decimal("180")


def _as_decimal(value: float | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A point on Earth."""

    latitude: Decimal
    longitude: Decimal

    @classmethod
    def parse(cls, *, latitude: float | str | Decimal, longitude: float | str | Decimal) -> "Coordinate":
        lat = _as_decimal(latitude)
        lon = _as_decimal(longitude)
        if not MIN_LATITUDE <= lat <= MAX_LATITUDE:
            raise InvalidBoundsError("latitude is outside the range of Earth")
        if not MIN_LONGITUDE <= lon <= MAX_LONGITUDE:
            raise InvalidBoundsError("longitude is outside the range of Earth")
        return cls(latitude=lat, longitude=lon)

    @staticmethod
    def validate_radius_km(radius_km: float | str | Decimal) -> Decimal:
        radius = _as_decimal(radius_km)
        if radius <= 0:
            raise InvalidRadiusError("radius must be greater than zero")
        if radius > MAX_RADIUS_KM:
            raise InvalidRadiusError(f"radius must not exceed {MAX_RADIUS_KM} km")
        return radius


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """A rectangular map window."""

    south: Decimal
    north: Decimal
    west: Decimal
    east: Decimal

    @classmethod
    def parse(
        cls,
        *,
        south: float | str | Decimal,
        north: float | str | Decimal,
        west: float | str | Decimal,
        east: float | str | Decimal,
    ) -> "BoundingBox":
        lower_left = Coordinate.parse(latitude=south, longitude=west)
        upper_right = Coordinate.parse(latitude=north, longitude=east)
        if lower_left.latitude > upper_right.latitude:
            raise InvalidBoundsError("south must not be north of north")
        if lower_left.longitude > upper_right.longitude:
            raise InvalidBoundsError("west must not be east of east")
        return cls(
            south=lower_left.latitude,
            north=upper_right.latitude,
            west=lower_left.longitude,
            east=upper_right.longitude,
        )
