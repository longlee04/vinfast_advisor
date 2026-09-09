"""Pure snapshot comparison rules for A5-4."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from src.agents.domain.values import VehicleType

DOCUMENT_UNVERIFIED_LABEL = "theo tài liệu, chưa xác minh"
ComparisonSource = Literal["STRUCTURED", "FLAG", "DOCUMENT"]
AssertionStatus = Literal["YES", "NO", "UNKNOWN"]
AssertionSource = Literal["FLAG", "DOCUMENT"]

CAR_CRITERIA = (
    "STARTING_PRICE_VND",
    "CAR_RANGE_KM",
    "CAR_SEAT_COUNT",
    "HOME_CHARGE_TIME_MINUTES",
)
MOTORBIKE_CRITERIA = (
    "STARTING_PRICE_VND",
    "MOTORBIKE_RANGE_MAX_KM",
    "MOTORBIKE_MAX_LOAD_KG",
    "BATTERY_REMOVABLE",
    "BATTERY_SWAPPABLE",
)
LOWER_IS_BETTER = {"STARTING_PRICE_VND", "HOME_CHARGE_TIME_MINUTES"}


class ComparisonSelectionError(ValueError):
    """The requested comparison selection is not a valid set of two or three vehicles."""


class CrossVehicleTypeComparisonError(ValueError):
    """Raised when a table would compare incomparable vehicle categories."""

    def __init__(self) -> None:
        self.reason = "Không thể so sánh ô tô với xe máy điện trong cùng bảng"
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class ComparisonFact:
    """One structured fact copied from the immutable run snapshot."""

    fact_code: str
    value_text: str
    source_table: str
    source_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComparisonAssertion:
    """One frozen feature assertion available for an additional-preference row."""

    feature_code: str
    status: AssertionStatus
    source: AssertionSource
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class ComparisonCandidate:
    """Snapshot facts and assertions for one selected vehicle."""

    vehicle_id: UUID
    vehicle_type: VehicleType
    facts: tuple[ComparisonFact, ...]
    assertions: tuple[ComparisonAssertion, ...]
    model_name: str = ""

    def __post_init__(self) -> None:
        codes = [fact.fact_code for fact in self.facts]
        if len(codes) != len(set(codes)):
            raise ComparisonSelectionError("comparison fact codes must be unique per vehicle")


@dataclass(frozen=True, slots=True)
class ComparisonCell:
    """One vehicle value, its authority label and whether it is best in the row."""

    vehicle_id: UUID
    value_text: str | None
    source: ComparisonSource | None
    evidence_ref: str | None
    label: str | None
    is_better: bool = False


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    """One deterministic comparison criterion across all selected vehicles."""

    criterion_code: str
    cells: tuple[ComparisonCell, ...]


@dataclass(frozen=True, slots=True)
class ComparisonTable:
    """Complete A5-4 table built from one immutable snapshot timestamp."""

    vehicle_type: VehicleType
    vehicle_ids: tuple[UUID, ...]
    rows: tuple[ComparisonRow, ...]
    captured_at: datetime | None = None
    vehicle_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.vehicle_names and len(self.vehicle_names) != len(self.vehicle_ids):
            raise ComparisonSelectionError("vehicle names must align with vehicle ids")


def compare_candidates(
    candidates: Sequence[ComparisonCandidate], *, captured_at: datetime | None = None
) -> ComparisonTable:
    """Compare exactly two or three same-type vehicles using structured rules only."""

    _validate_selection(candidates)
    vehicle_type = candidates[0].vehicle_type
    if any(candidate.vehicle_type is not vehicle_type for candidate in candidates[1:]):
        raise CrossVehicleTypeComparisonError
    rows = [_structured_row(code, candidates) for code in _criteria_for(vehicle_type)]
    rows.extend(_assertion_rows(candidates))
    return ComparisonTable(
        vehicle_type=vehicle_type,
        vehicle_ids=tuple(candidate.vehicle_id for candidate in candidates),
        rows=tuple(rows),
        captured_at=captured_at,
        vehicle_names=tuple(candidate.model_name for candidate in candidates),
    )


def structured_fact_cell(vehicle_id: UUID, fact: ComparisonFact) -> ComparisonCell:
    """Render one structured snapshot fact for both lookup and comparison paths."""

    source_ref = fact.source_table
    if fact.source_id is not None:
        source_ref = f"{source_ref}:{fact.source_id}"
    return ComparisonCell(
        vehicle_id=vehicle_id,
        value_text=fact.value_text,
        source="STRUCTURED",
        evidence_ref=source_ref,
        label=None,
    )


def _validate_selection(candidates: Sequence[ComparisonCandidate]) -> None:
    if len(candidates) not in {2, 3}:
        raise ComparisonSelectionError("comparison requires exactly two or three samples")
    vehicle_ids = [candidate.vehicle_id for candidate in candidates]
    if len(vehicle_ids) != len(set(vehicle_ids)):
        raise ComparisonSelectionError("comparison vehicle ids must be unique")


def _criteria_for(vehicle_type: VehicleType) -> tuple[str, ...]:
    if vehicle_type is VehicleType.CAR:
        return CAR_CRITERIA
    return MOTORBIKE_CRITERIA


def _structured_row(criterion_code: str, candidates: Sequence[ComparisonCandidate]) -> ComparisonRow:
    cells = []
    for candidate in candidates:
        fact = next((item for item in candidate.facts if item.fact_code == criterion_code), None)
        cells.append(
            structured_fact_cell(candidate.vehicle_id, fact)
            if fact is not None
            else _missing_cell(candidate.vehicle_id)
        )
    return ComparisonRow(
        criterion_code=criterion_code,
        cells=_mark_better(tuple(cells), criterion_code),
    )


def _assertion_rows(
    candidates: Sequence[ComparisonCandidate],
) -> list[ComparisonRow]:
    feature_codes = sorted({assertion.feature_code for candidate in candidates for assertion in candidate.assertions})
    return [
        ComparisonRow(
            criterion_code=feature_code,
            cells=_mark_better(
                tuple(_assertion_cell(candidate, feature_code) for candidate in candidates),
                feature_code,
            ),
        )
        for feature_code in feature_codes
    ]


def _assertion_cell(candidate: ComparisonCandidate, feature_code: str) -> ComparisonCell:
    matching = [assertion for assertion in candidate.assertions if assertion.feature_code == feature_code]
    if not matching:
        return _missing_cell(candidate.vehicle_id)
    assertion = min(
        matching,
        key=lambda item: (0 if item.source == "FLAG" else 1, -_status_rank(item.status)),
    )
    return ComparisonCell(
        vehicle_id=candidate.vehicle_id,
        value_text=assertion.status,
        source=assertion.source,
        evidence_ref=assertion.evidence_ref,
        label=DOCUMENT_UNVERIFIED_LABEL if assertion.source == "DOCUMENT" else None,
    )


def _missing_cell(vehicle_id: UUID) -> ComparisonCell:
    return ComparisonCell(
        vehicle_id=vehicle_id,
        value_text=None,
        source=None,
        evidence_ref=None,
        label=None,
    )


def _mark_better(cells: tuple[ComparisonCell, ...], criterion_code: str) -> tuple[ComparisonCell, ...]:
    ranked = [(cell, _comparable_value(cell.value_text)) for cell in cells]
    present = [(cell, value) for cell, value in ranked if value is not None]
    if not present:
        return cells
    values = [value for _, value in present]
    best = min(values) if criterion_code in LOWER_IS_BETTER else max(values)
    return tuple(replace(cell, is_better=value == best) if value is not None else cell for cell, value in ranked)


def _comparable_value(value_text: str | None) -> Decimal | None:
    if value_text is None:
        return None
    statuses = {"NO": Decimal("0"), "UNKNOWN": Decimal("1"), "YES": Decimal("2")}
    booleans = {"false": Decimal("0"), "true": Decimal("1")}
    if value_text in statuses:
        return statuses[value_text]
    if value_text.lower() in booleans:
        return booleans[value_text.lower()]
    try:
        return Decimal(value_text)
    except InvalidOperation:
        return None


def _status_rank(status: AssertionStatus) -> int:
    return {"NO": 0, "UNKNOWN": 1, "YES": 2}[status]
