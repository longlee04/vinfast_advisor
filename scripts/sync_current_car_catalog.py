"""Synchronize verified current car prices, VF 8 specs, and car promotions.

Only rows belonging to active/archived cars and promotions produced by the
official-policy crawler are updated.  The operation is atomic and never
truncates catalog tables or changes motorbike promotions.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data-p150" / "catalog"
VF8_SPEC_IDS = {
    "7b751a66-fd67-54a6-ac13-04a65f712033",
    "102f2ad5-1981-5364-a810-17dd96795e4c",
}
CRAWLER_CREATED_BY = "vinfast_policy_crawler"


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _optional_int(value: str) -> int | None:
    return int(float(value)) if value else None


def _optional_float(value: str) -> float | None:
    return float(value) if value else None


def _optional_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _database_dsn(explicit: str | None) -> str:
    load_dotenv(ROOT / ".env")
    raw = explicit or os.environ.get("PRODUCT_DATABASE_URL_SYNC") or os.environ.get("PRODUCT_DATABASE_URL")
    if not raw:
        raise RuntimeError("PRODUCT_DATABASE_URL_SYNC or PRODUCT_DATABASE_URL is required")
    return raw.replace("postgresql+asyncpg://", "postgresql://")


async def _sync_vf8_specs(connection: asyncpg.Connection[Any]) -> int:
    rows = [row for row in _rows("cars.csv") if row["vehicle_id"] in VF8_SPEC_IDS]
    for row in rows:
        await connection.execute(
            """
            UPDATE cars SET
                range_km = $2, range_cycle = $3,
                energy_consumption_kwh_per_100km = $4,
                battery_capacity_kwh = $5, motor_power_kw = $6,
                torque_nm = $7, max_speed_kmh = $8,
                acceleration_0_100_seconds = $9,
                fast_charge_power_kw = $10, fast_charge_time_minutes = $11,
                fast_charge_from_percent = $12, fast_charge_to_percent = $13,
                specs_version = $14, effective_from = $15,
                effective_to = $16, updated_at = $17
            WHERE vehicle_id = $1
            """,
            row["vehicle_id"],
            _optional_float(row["range_km"]),
            row["range_cycle"],
            _optional_float(row["energy_consumption_kwh_per_100km"]),
            _optional_float(row["battery_capacity_kwh"]),
            _optional_float(row["motor_power_kw"]),
            _optional_float(row["torque_nm"]),
            _optional_float(row["max_speed_kmh"]),
            _optional_float(row["acceleration_0_100_seconds"]),
            _optional_float(row["fast_charge_power_kw"]),
            _optional_int(row["fast_charge_time_minutes"]),
            _optional_int(row["fast_charge_from_percent"]),
            _optional_int(row["fast_charge_to_percent"]),
            _optional_int(row["specs_version"]),
            _optional_datetime(row["effective_from"]),
            _optional_datetime(row["effective_to"]),
            _optional_datetime(row["updated_at"]),
        )
    return len(rows)


async def _sync_car_prices(connection: asyncpg.Connection[Any]) -> int:
    car_ids = {row["vehicle_id"] for row in _rows("vehicles.csv") if row["vehicle_type"] == "CAR"}
    rows = [row for row in _rows("vehicle_prices.csv") if row["vehicle_id"] in car_ids]
    for row in rows:
        await connection.execute(
            """
            INSERT INTO vehicle_prices (
                price_id, vehicle_id, price_type, amount_vnd, currency,
                region_code, status, valid_from, valid_to, created_by,
                updated_by, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
            ON CONFLICT (price_id) DO UPDATE SET
                amount_vnd = EXCLUDED.amount_vnd,
                currency = EXCLUDED.currency,
                region_code = EXCLUDED.region_code,
                status = EXCLUDED.status,
                valid_from = EXCLUDED.valid_from,
                valid_to = EXCLUDED.valid_to,
                updated_by = EXCLUDED.updated_by,
                updated_at = EXCLUDED.updated_at
            """,
            row["price_id"],
            row["vehicle_id"],
            row["price_type"],
            int(row["amount_vnd"]),
            row["currency"],
            row["region_code"],
            row["status"],
            _optional_datetime(row["valid_from"]),
            _optional_datetime(row["valid_to"]),
            row["created_by"] or None,
            row["updated_by"] or None,
            _optional_datetime(row["created_at"]),
            _optional_datetime(row["updated_at"]),
        )
    return len(rows)


async def _sync_car_promotions(connection: asyncpg.Connection[Any]) -> tuple[int, int]:
    promotions = [row for row in _rows("promotions.csv") if row["created_by"] == CRAWLER_CREATED_BY]
    promotion_ids = [row["promotion_id"] for row in promotions]
    links = [row for row in _rows("promotion_vehicles.csv") if row["promotion_id"] in promotion_ids]
    for row in promotions:
        await connection.execute(
            """
            INSERT INTO promotions (
                promotion_id, promotion_code, title, description, promotion_type,
                discount_amount_vnd, discount_percent, region_code,
                eligibility_rules, status, valid_from, valid_to, created_by,
                approved_by, approved_at, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10,
                $11, $12, $13, $14, $15, $16, $17
            )
            ON CONFLICT (promotion_id) DO UPDATE SET
                promotion_code = EXCLUDED.promotion_code,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                promotion_type = EXCLUDED.promotion_type,
                discount_amount_vnd = EXCLUDED.discount_amount_vnd,
                discount_percent = EXCLUDED.discount_percent,
                region_code = EXCLUDED.region_code,
                eligibility_rules = EXCLUDED.eligibility_rules,
                status = EXCLUDED.status,
                valid_from = EXCLUDED.valid_from,
                valid_to = EXCLUDED.valid_to,
                approved_by = EXCLUDED.approved_by,
                approved_at = EXCLUDED.approved_at,
                updated_at = EXCLUDED.updated_at
            """,
            row["promotion_id"],
            row["promotion_code"],
            row["title"],
            row["description"] or None,
            row["promotion_type"],
            _optional_int(row["discount_amount_vnd"]),
            _optional_float(row["discount_percent"]),
            row["region_code"],
            json.dumps(json.loads(row["eligibility_rules"]), ensure_ascii=False),
            row["status"],
            _optional_datetime(row["valid_from"]),
            _optional_datetime(row["valid_to"]),
            row["created_by"],
            row["approved_by"] or None,
            _optional_datetime(row["approved_at"]),
            _optional_datetime(row["created_at"]),
            _optional_datetime(row["updated_at"]),
        )
    await connection.execute("DELETE FROM promotion_vehicles WHERE promotion_id = ANY($1::uuid[])", promotion_ids)
    for row in links:
        await connection.execute(
            """
            INSERT INTO promotion_vehicles (promotion_id, vehicle_id, created_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (promotion_id, vehicle_id) DO NOTHING
            """,
            row["promotion_id"],
            row["vehicle_id"],
            _optional_datetime(row["created_at"]),
        )
    return len(promotions), len(links)


async def sync_database(dsn: str) -> dict[str, int]:
    """Synchronize the verified subset and return affected CSV row counts."""

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            specs = await _sync_vf8_specs(connection)
            prices = await _sync_car_prices(connection)
            promotions, links = await _sync_car_promotions(connection)
    finally:
        await connection.close()
    return {
        "vf8_specs": specs,
        "car_prices": prices,
        "car_promotions": promotions,
        "car_promotion_links": links,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn")
    args = parser.parse_args()
    summary = asyncio.run(sync_database(_database_dsn(args.dsn)))
    for key, count in summary.items():
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()
