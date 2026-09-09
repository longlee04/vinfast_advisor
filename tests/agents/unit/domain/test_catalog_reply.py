"""Catalog lookup replies are rendered from verified facts without an LLM."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from src.agents.contracts import VehicleFacts
from src.agents.domain.catalog_reply import render_lookup_answer
from src.agents.domain.values import VehicleType

VF5 = VehicleFacts(
    vehicle_id=uuid4(),
    display_name="VinFast VF 5 Plus",
    vehicle_type=VehicleType.CAR,
    starting_price_vnd=Decimal("529000000"),
    specs={"seat_count": 5, "body_type": "SUV", "range_km": "326"},
)


def test_answer_formats_verified_vehicle_price_and_specs() -> None:
    answer = render_lookup_answer([VF5])

    assert answer is not None
    assert "VinFast VF 5 Plus" in answer
    assert "529.000.000" in answer
    assert "5 chỗ" in answer


def test_missing_price_is_stated_instead_of_replaced_by_zero() -> None:
    facts = VehicleFacts(
        vehicle_id=uuid4(),
        display_name="VinFast VF 3",
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=None,
        specs={},
    )

    answer = render_lookup_answer([facts])

    assert answer is not None
    assert "chưa có giá" in answer
    assert "0 đồng" not in answer


def test_unmatched_and_ambiguous_mentions_receive_explicit_guidance() -> None:
    unmatched = render_lookup_answer([], unmatched=["VF 20"])
    ambiguous = render_lookup_answer([], ambiguous=["VF 5"])

    assert unmatched is not None and "chưa tìm thấy" in unmatched
    assert ambiguous is not None and "?" in ambiguous


def test_empty_lookup_has_no_invented_answer() -> None:
    assert render_lookup_answer([]) is None
