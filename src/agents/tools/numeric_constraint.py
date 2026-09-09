"""Deterministic parser for common Vietnamese numeric vehicle constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """One normalized numeric filter."""

    field: str
    operator: str
    value: Decimal


def parse_numeric_constraints(text: str) -> list[FilterSpec]:
    """Parse budget, seats, range, and load constraints without an LLM."""

    folded = text.casefold().replace(",", ".")
    specs: list[FilterSpec] = []
    budget = re.search(r"(\d+(?:\.\d+)?)\s*(tỷ|ty|triệu|trieu|m)", folded)
    if budget:
        multiplier = Decimal("1000000000") if budget.group(2) in {"tỷ", "ty"} else Decimal("1000000")
        specs.append(FilterSpec("price_vnd", "<=", Decimal(budget.group(1)) * multiplier))
    seats = re.search(r"(\d+)\s*chỗ\s*(trở lên|tro len|hoặc hơn|or more)?", folded)
    if seats:
        operator = ">=" if seats.group(2) else "="
        specs.append(FilterSpec("seat_count", operator, Decimal(seats.group(1))))
    range_match = re.search(r"(?:tầm chạy|tam chay|quãng đường|quang duong)\D{0,12}(\d+)", folded)
    if range_match:
        specs.append(FilterSpec("range_km", ">=", Decimal(range_match.group(1))))
    load = re.search(r"(?:tải|tai|chở|cho)\D{0,12}(\d+)\s*kg", folded)
    if load:
        specs.append(FilterSpec("load_kg", ">=", Decimal(load.group(1))))
    return specs
