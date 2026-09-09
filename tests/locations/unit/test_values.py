"""Domain values cho module Locations."""

from decimal import Decimal

import pytest

from src.locations.domain.errors import InvalidBoundsError, InvalidRadiusError
from src.locations.domain.values import BoundingBox, Coordinate


def test_bounding_box_accepts_a_normal_window() -> None:
    box = BoundingBox.parse(south=10.0, north=11.0, west=106.0, east=107.0)

    assert box.south == Decimal("10.0")
    assert box.north == Decimal("11.0")


def test_bounding_box_rejects_inverted_latitude() -> None:
    with pytest.raises(InvalidBoundsError):
        BoundingBox.parse(south=11.0, north=10.0, west=106.0, east=107.0)


def test_bounding_box_rejects_inverted_longitude() -> None:
    with pytest.raises(InvalidBoundsError):
        BoundingBox.parse(south=10.0, north=11.0, west=107.0, east=106.0)


def test_bounding_box_rejects_latitude_outside_earth() -> None:
    with pytest.raises(InvalidBoundsError):
        BoundingBox.parse(south=-91.0, north=11.0, west=106.0, east=107.0)


def test_bounding_box_rejects_longitude_outside_earth() -> None:
    with pytest.raises(InvalidBoundsError):
        BoundingBox.parse(south=10.0, north=11.0, west=106.0, east=181.0)


def test_coordinate_rejects_a_point_off_the_earth() -> None:
    with pytest.raises(InvalidBoundsError):
        Coordinate.parse(latitude=95.0, longitude=106.0)


def test_coordinate_accepts_a_point_in_vietnam() -> None:
    point = Coordinate.parse(latitude=21.028511, longitude=105.804817)

    assert point.latitude == Decimal("21.028511")


def test_radius_must_stay_within_the_allowed_ceiling() -> None:
    with pytest.raises(InvalidRadiusError):
        Coordinate.validate_radius_km(51.0)


def test_radius_must_be_positive() -> None:
    with pytest.raises(InvalidRadiusError):
        Coordinate.validate_radius_km(0.0)


def test_radius_at_the_ceiling_is_allowed() -> None:
    assert Coordinate.validate_radius_km(50.0) == Decimal("50.0")
