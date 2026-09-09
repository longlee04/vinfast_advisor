"""Contract tests for pure A5-4 snapshot comparison."""

from uuid import UUID

import pytest

from src.agents.domain.comparison import (
    DOCUMENT_UNVERIFIED_LABEL,
    ComparisonAssertion,
    ComparisonCandidate,
    ComparisonFact,
    ComparisonSelectionError,
    ComparisonTable,
    CrossVehicleTypeComparisonError,
    compare_candidates,
)
from src.agents.domain.values import VehicleType

CAR_1 = UUID("00000000-0000-0000-0000-000000000201")
CAR_2 = UUID("00000000-0000-0000-0000-000000000202")
MOTORBIKE = UUID("00000000-0000-0000-0000-000000000203")


def _car(
    vehicle_id: UUID,
    *,
    price: str,
    range_km: str,
    seats: str,
    charge_minutes: str,
    assertions: tuple[ComparisonAssertion, ...] = (),
) -> ComparisonCandidate:
    return ComparisonCandidate(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.CAR,
        facts=(
            ComparisonFact("STARTING_PRICE_VND", price, "vehicle_prices"),
            ComparisonFact("CAR_RANGE_KM", range_km, "cars"),
            ComparisonFact("CAR_SEAT_COUNT", seats, "cars"),
            ComparisonFact("HOME_CHARGE_TIME_MINUTES", charge_minutes, "cars"),
        ),
        assertions=assertions,
    )


def _motorbike(vehicle_id: UUID) -> ComparisonCandidate:
    return ComparisonCandidate(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        facts=(
            ComparisonFact("STARTING_PRICE_VND", "30000000", "vehicle_prices"),
            ComparisonFact("MOTORBIKE_RANGE_MAX_KM", "120", "motorbikes"),
            ComparisonFact("MOTORBIKE_MAX_LOAD_KG", "150", "motorbikes"),
            ComparisonFact("BATTERY_REMOVABLE", "true", "motorbikes"),
        ),
        assertions=(),
    )


def test_cross_vehicle_type_comparison_is_blocked_with_reason() -> None:
    with pytest.raises(CrossVehicleTypeComparisonError) as captured:
        compare_candidates(
            [
                _car(
                    CAR_1,
                    price="600000000",
                    range_km="400",
                    seats="5",
                    charge_minutes="480",
                ),
                _motorbike(MOTORBIKE),
            ]
        )

    assert captured.value.reason == "Không thể so sánh ô tô với xe máy điện trong cùng bảng"


def test_car_comparison_contains_minimum_rows_and_marks_better_cells() -> None:
    table = compare_candidates(
        [
            _car(
                CAR_1,
                price="600000000",
                range_km="400",
                seats="5",
                charge_minutes="480",
            ),
            _car(
                CAR_2,
                price="700000000",
                range_km="500",
                seats="7",
                charge_minutes="360",
            ),
        ]
    )

    rows = {row.criterion_code: row for row in table.rows}
    assert set(rows) >= {
        "STARTING_PRICE_VND",
        "CAR_RANGE_KM",
        "CAR_SEAT_COUNT",
        "HOME_CHARGE_TIME_MINUTES",
    }
    assert _best_vehicle(rows["STARTING_PRICE_VND"]) == CAR_1
    assert _best_vehicle(rows["CAR_RANGE_KM"]) == CAR_2
    assert _best_vehicle(rows["CAR_SEAT_COUNT"]) == CAR_2
    assert _best_vehicle(rows["HOME_CHARGE_TIME_MINUTES"]) == CAR_2


def test_comparison_preserves_ordered_vehicle_model_names() -> None:
    table = compare_candidates(
        [
            ComparisonCandidate(
                vehicle_id=CAR_1,
                vehicle_type=VehicleType.CAR,
                model_name="VF 8 Eco",
                facts=(),
                assertions=(),
            ),
            ComparisonCandidate(
                vehicle_id=CAR_2,
                vehicle_type=VehicleType.CAR,
                model_name="VF 9 Plus",
                facts=(),
                assertions=(),
            ),
        ]
    )

    assert table.vehicle_names == ("VF 8 Eco", "VF 9 Plus")


def test_document_cell_always_has_unverified_label() -> None:
    table = _feature_source_table()

    feature_row = next(row for row in table.rows if row.criterion_code == "PANORAMIC_ROOF")
    cells = {cell.vehicle_id: cell for cell in feature_row.cells}
    assert cells[CAR_1].source == "DOCUMENT"
    assert cells[CAR_1].label == DOCUMENT_UNVERIFIED_LABEL


def test_flag_cell_has_no_extra_label() -> None:
    table = _feature_source_table()

    feature_row = next(row for row in table.rows if row.criterion_code == "PANORAMIC_ROOF")
    cells = {cell.vehicle_id: cell for cell in feature_row.cells}
    assert cells[CAR_2].source == "FLAG"
    assert cells[CAR_2].label is None


def test_flag_takes_authority_over_document_for_same_vehicle_feature() -> None:
    document = ComparisonAssertion(
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="DOCUMENT",
        evidence_ref="document_chunks:chunk-1",
    )
    flag = ComparisonAssertion(
        feature_code="PANORAMIC_ROOF",
        status="UNKNOWN",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-1",
    )
    table = compare_candidates(
        [
            _car(
                CAR_1,
                price="600000000",
                range_km="400",
                seats="5",
                charge_minutes="480",
                assertions=(document, flag),
            ),
            _car(
                CAR_2,
                price="700000000",
                range_km="500",
                seats="7",
                charge_minutes="360",
            ),
        ]
    )

    feature_row = next(row for row in table.rows if row.criterion_code == "PANORAMIC_ROOF")
    cell = next(item for item in feature_row.cells if item.vehicle_id == CAR_1)
    assert cell.source == "FLAG"
    assert cell.value_text == "UNKNOWN"
    assert cell.label is None


def _feature_source_table() -> ComparisonTable:
    document = ComparisonAssertion(
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="DOCUMENT",
        evidence_ref="document_chunks:chunk-1",
    )
    flag = ComparisonAssertion(
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-2",
    )
    return compare_candidates(
        [
            _car(
                CAR_1,
                price="600000000",
                range_km="400",
                seats="5",
                charge_minutes="480",
                assertions=(document,),
            ),
            _car(
                CAR_2,
                price="700000000",
                range_km="500",
                seats="7",
                charge_minutes="360",
                assertions=(flag,),
            ),
        ]
    )


@pytest.mark.parametrize("count", [1, 4])
def test_comparison_rejects_selection_outside_two_to_three_samples(count: int) -> None:
    candidates = [
        _car(
            UUID(int=300 + index),
            price=str(600000000 + index),
            range_km="400",
            seats="5",
            charge_minutes="480",
        )
        for index in range(count)
    ]

    with pytest.raises(ComparisonSelectionError, match="exactly two or three"):
        compare_candidates(candidates)


def test_duplicate_vehicle_selection_is_rejected() -> None:
    candidate = _car(
        CAR_1,
        price="600000000",
        range_km="400",
        seats="5",
        charge_minutes="480",
    )

    with pytest.raises(ComparisonSelectionError, match="unique"):
        compare_candidates([candidate, candidate])


def _best_vehicle(row: object) -> UUID:
    cells = getattr(row, "cells")
    return next(cell.vehicle_id for cell in cells if cell.is_better)
