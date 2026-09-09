"""A selected vehicle branch changes only when the customer says so."""

from __future__ import annotations

import pytest

from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_type_lock import explicit_vehicle_type, keeps_known_vehicle_type


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Em muốn mua xe máy điện", VehicleType.ELECTRIC_MOTORBIKE),
        ("Cho em xem Feliz với", VehicleType.ELECTRIC_MOTORBIKE),
        ("Em cần ô tô điện 4 chỗ", VehicleType.CAR),
        ("VF 5 giá bao nhiêu ạ", VehicleType.CAR),
        ("Em ưu tiên xe tiết kiệm, dễ đi trong phố", None),
        ("", None),
    ],
)
def test_explicit_vehicle_type_uses_only_customer_text(message: str, expected: VehicleType | None) -> None:
    assert explicit_vehicle_type(message) is expected


def test_vague_answer_keeps_the_existing_branch() -> None:
    assert keeps_known_vehicle_type(
        known=VehicleType.CAR,
        proposed=VehicleType.ELECTRIC_MOTORBIKE,
        user_message="Em ưu tiên xe tiết kiệm, dễ đi trong phố",
    )


def test_explicit_change_is_allowed() -> None:
    assert not keeps_known_vehicle_type(
        known=VehicleType.CAR,
        proposed=VehicleType.ELECTRIC_MOTORBIKE,
        user_message="Em đổi ý, em muốn mua xe máy điện",
    )
