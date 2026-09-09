"""Synchronize officially verified motorbike specs and prices into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data-p150" / "catalog"
VERIFIED_VEHICLE_IDS = {
    "973e909c-5461-5ca2-b6ee-9fa78cf03780",  # Kinet
    "48143671-050b-5388-a3b9-3c99bcf62f4f",  # Flazz Max
    "c54c10de-36d1-5aaa-b49b-3a53e5876956",  # Amio S
    "3c13690f-0b7c-55df-a6a5-786de0e00a6a",  # Evo Grand Lite
    "5e379762-e8fb-528b-bce0-de2100bc1662",  # Amio
    "f0ee5858-35de-5616-b445-de8af6c83de6",  # Vero X
    "f9bf70f8-4f49-5d1b-b08a-2ac7f19a61f6",  # DrgnFly
}
VERIFIED_PRICE_IDS = {
    "9fef4586-ef39-45df-973d-58ec67b33ea0",
    "ce069779-989c-465c-a74b-8f38b083848c",
    "2befcc08-f38c-5b10-93cb-02e8413091b7",
    "0318a198-ef34-55a5-b32d-0e1901bea942",
    "2c256ce1-fedd-554f-962e-6144bda21b3d",
    "0c90a6ca-ac09-5040-8b27-6d74c6754521",
    "220da410-8700-5cae-b372-834feca50c0f",
}


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional_number(value: str) -> float | None:
    return float(value) if value else None


def _optional_int(value: str) -> int | None:
    return int(float(value)) if value else None


def _optional_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _optional_bool(value: str) -> bool | None:
    return {"true": True, "false": False}.get(value.lower()) if value else None


def _database_dsn(explicit: str | None) -> str:
    load_dotenv(ROOT / ".env")
    raw = (
        explicit
        or os.environ.get("PRODUCT_DATABASE_URL_SYNC")
        or os.environ.get("PRODUCT_DATABASE_URL")
        or os.environ.get("AUTH_DATABASE_URL")
    )
    if not raw:
        raise RuntimeError("PRODUCT_DATABASE_URL_SYNC, PRODUCT_DATABASE_URL, or AUTH_DATABASE_URL is required")
    return raw.replace("postgresql+asyncpg://", "postgresql://")


async def _sync_specs(connection: asyncpg.Connection[Any]) -> int:
    rows = [row for row in _rows("motorbikes.csv") if row["vehicle_id"] in VERIFIED_VEHICLE_IDS]
    columns = [name for name in rows[0] if name != "vehicle_id"]
    for row in rows:
        values: list[object] = []
        for column in columns:
            value = row[column]
            if column in {"battery_removable", "battery_swappable"}:
                values.append(_optional_bool(value))
            elif column in {"battery_quantity", "charging_time_minutes", "specs_version"}:
                values.append(_optional_int(value))
            elif column in {"effective_from", "effective_to", "created_at", "updated_at"}:
                values.append(_optional_datetime(value))
            elif column in {"battery_type", "range_cycle", "charging_method", "license_requirement"}:
                values.append(value or None)
            else:
                values.append(_optional_number(value))
        assignments = ", ".join(f"{name} = ${index}" for index, name in enumerate(columns, 2))
        await connection.execute(
            f"UPDATE motorbikes SET {assignments} WHERE vehicle_id = $1",  # noqa: S608
            row["vehicle_id"],
            *values,
        )
    return len(rows)


async def _sync_prices(connection: asyncpg.Connection[Any]) -> int:
    rows = [row for row in _rows("vehicle_prices.csv") if row["price_id"] in VERIFIED_PRICE_IDS]
    for row in rows:
        await connection.execute(
            """
            INSERT INTO vehicle_prices (
                price_id, vehicle_id, price_type, amount_vnd, currency, region_code,
                status, valid_from, valid_to, created_by, updated_by, created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            ON CONFLICT (price_id) DO UPDATE SET
                amount_vnd = EXCLUDED.amount_vnd, status = EXCLUDED.status,
                valid_from = EXCLUDED.valid_from, valid_to = EXCLUDED.valid_to,
                updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
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


async def sync_database(dsn: str) -> dict[str, int]:
    """Apply only the reviewed motorbike subset in one transaction."""

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            return {
                "motorbike_specs": await _sync_specs(connection),
                "motorbike_prices": await _sync_prices(connection),
            }
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn")
    args = parser.parse_args()
    for key, count in asyncio.run(sync_database(_database_dsn(args.dsn))).items():
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()
