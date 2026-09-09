"""Regression checks for motorbike values verified on official VinFast pages."""

from __future__ import annotations

import csv
from pathlib import Path

CATALOG_DIR = Path(__file__).parents[2] / "data-p150" / "catalog"


def _rows(filename: str) -> list[dict[str, str]]:
    with (CATALOG_DIR / filename).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_corrected_official_motorbike_specs_are_kept_current() -> None:
    specs = {row["vehicle_id"]: row for row in _rows("motorbikes.csv")}

    assert specs["973e909c-5461-5ca2-b6ee-9fa78cf03780"]["max_power_w"] == "5200"
    assert specs["973e909c-5461-5ca2-b6ee-9fa78cf03780"]["range_max_km"] == "145"
    assert specs["48143671-050b-5388-a3b9-3c99bcf62f4f"]["max_speed_kmh"] == "49"
    assert specs["48143671-050b-5388-a3b9-3c99bcf62f4f"]["range_max_km"] == "87"
    assert specs["5e379762-e8fb-528b-bce0-de2100bc1662"]["max_speed_kmh"] == "30"
    assert specs["c54c10de-36d1-5aaa-b49b-3a53e5876956"]["range_max_km"] == "65"
    assert specs["3c13690f-0b7c-55df-a6a5-786de0e00a6a"]["max_power_w"] == "1900"
    assert specs["f0ee5858-35de-5616-b445-de8af6c83de6"]["max_power_w"] == "2250"
    assert specs["f9bf70f8-4f49-5d1b-b08a-2ac7f19a61f6"]["motor_power_w"] == "250"
    assert specs["f9bf70f8-4f49-5d1b-b08a-2ac7f19a61f6"]["range_max_km"] == "110"


def test_official_motorbike_prices_are_available_for_menu_variants() -> None:
    prices = _rows("vehicle_prices.csv")
    keyed = {(row["vehicle_id"], row["price_type"]): row["amount_vnd"] for row in prices}

    assert keyed[("69bd6f00-e733-5ba4-a7a6-2fe413903eb8", "BATTERY_INCLUDED")] == "18900000"
    assert keyed[("7b23f259-56e6-5abb-bfc6-dabbc06dc220", "BATTERY_INCLUDED")] == "28700000"
    assert keyed[("48143671-050b-5388-a3b9-3c99bcf62f4f", "BATTERY_INCLUDED")] == "17300000"
    assert keyed[("417618a2-734f-5389-81b6-6cfd597dedc2", "STARTING_PRICE")] == "10900000"
    assert keyed[("417618a2-734f-5389-81b6-6cfd597dedc2", "BATTERY_INCLUDED")] == "14400000"
    assert keyed[("27b32cdc-923c-5e48-838f-499e45e3a300", "BATTERY_INCLUDED")] == "40600000"
    assert keyed[("f9bf70f8-4f49-5d1b-b08a-2ac7f19a61f6", "STARTING_PRICE")] == "18690000"
