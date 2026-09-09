"""Seed catalog (product module) tables from data-p150/catalog/*.csv into Postgres.

Usage:
    uv run python scripts/seed_catalog_data.py [--dsn postgresql://...] [--truncate]

Insert order follows FK dependency: vehicles -> cars/motorbikes -> vehicle_prices
-> promotions -> promotion_vehicles -> battery_policies -> feature_definitions
-> vehicle_feature_flags -> feature_need_tags -> tco_assumptions -> vehicle_documents
(vehicle_documents belongs to the document module but is included here since the
CSV export lives alongside the rest of the catalog data).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
from datetime import datetime
from pathlib import Path

import asyncpg

DATA_DIR = Path(__file__).resolve().parent.parent / "data-p150" / "catalog"

DEFAULT_DSN = "postgresql://p150_auth:p150_local_dev@localhost:5432/p150_auth"


def parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.strip().lower() == "true"


def parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_ts(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_text(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


# Each table: (csv_name, insert_column_order, {column: parser}, conflict_pk_columns)
TABLES: list[tuple[str, list[str], dict[str, callable], list[str]]] = [
    (
        "vehicles",
        [
            "vehicle_id",
            "vehicle_type",
            "brand",
            "model_name",
            "variant_name",
            "model_year",
            "status",
            "slug",
            "image_url",
            "detail_url",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ],
        {"model_year": parse_int, "created_at": parse_ts, "updated_at": parse_ts},
        ["vehicle_id"],
    ),
    (
        "cars",
        [
            "vehicle_id",
            "body_type",
            "seat_count",
            "range_km",
            "range_cycle",
            "energy_consumption_kwh_per_100km",
            "battery_capacity_kwh",
            "motor_power_kw",
            "torque_nm",
            "max_speed_kmh",
            "acceleration_0_100_seconds",
            "curb_weight_kg",
            "gross_weight_kg",
            "fast_charge_power_kw",
            "fast_charge_time_minutes",
            "fast_charge_from_percent",
            "fast_charge_to_percent",
            "home_charge_time_minutes",
            "charging_port",
            "cargo_volume_standard_l",
            "cargo_volume_maximum_l",
            "towing_supported",
            "towing_capacity_kg",
            "specs_version",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        ],
        {
            "seat_count": parse_int,
            "range_km": parse_float,
            "energy_consumption_kwh_per_100km": parse_float,
            "battery_capacity_kwh": parse_float,
            "motor_power_kw": parse_float,
            "torque_nm": parse_float,
            "max_speed_kmh": parse_float,
            "acceleration_0_100_seconds": parse_float,
            "curb_weight_kg": parse_float,
            "gross_weight_kg": parse_float,
            "fast_charge_power_kw": parse_float,
            "fast_charge_time_minutes": parse_int,
            "fast_charge_from_percent": parse_int,
            "fast_charge_to_percent": parse_int,
            "home_charge_time_minutes": parse_int,
            "cargo_volume_standard_l": parse_float,
            "cargo_volume_maximum_l": parse_float,
            "towing_supported": parse_bool,
            "towing_capacity_kg": parse_float,
            "specs_version": parse_int,
            "effective_from": parse_ts,
            "effective_to": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["vehicle_id"],
    ),
    (
        "motorbikes",
        [
            "vehicle_id",
            "motor_power_w",
            "max_power_w",
            "torque_nm",
            "max_speed_kmh",
            "battery_type",
            "battery_capacity_kwh",
            "battery_quantity",
            "battery_removable",
            "battery_swappable",
            "energy_consumption_kwh_per_100km",
            "range_min_km",
            "range_max_km",
            "range_cycle",
            "charging_time_minutes",
            "charging_method",
            "curb_weight_kg",
            "max_load_kg",
            "seat_height_mm",
            "wheel_size_front_inch",
            "wheel_size_rear_inch",
            "license_requirement",
            "specs_version",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        ],
        {
            "motor_power_w": parse_int,
            "max_power_w": parse_int,
            "torque_nm": parse_float,
            "max_speed_kmh": parse_float,
            "battery_capacity_kwh": parse_float,
            "battery_quantity": parse_int,
            "battery_removable": parse_bool,
            "battery_swappable": parse_bool,
            "energy_consumption_kwh_per_100km": parse_float,
            "range_min_km": parse_float,
            "range_max_km": parse_float,
            "charging_time_minutes": parse_int,
            "curb_weight_kg": parse_float,
            "max_load_kg": parse_float,
            "seat_height_mm": parse_float,
            "wheel_size_front_inch": parse_float,
            "wheel_size_rear_inch": parse_float,
            "specs_version": parse_int,
            "effective_from": parse_ts,
            "effective_to": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["vehicle_id"],
    ),
    (
        "vehicle_prices",
        [
            "price_id",
            "vehicle_id",
            "price_type",
            "amount_vnd",
            "currency",
            "region_code",
            "status",
            "valid_from",
            "valid_to",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        {
            "amount_vnd": parse_int,
            "valid_from": parse_ts,
            "valid_to": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["price_id"],
    ),
    (
        "promotions",
        [
            "promotion_id",
            "promotion_code",
            "title",
            "description",
            "promotion_type",
            "discount_amount_vnd",
            "discount_percent",
            "region_code",
            "eligibility_rules",
            "status",
            "valid_from",
            "valid_to",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ],
        {
            "discount_amount_vnd": parse_int,
            "discount_percent": parse_float,
            "valid_from": parse_ts,
            "valid_to": parse_ts,
            "approved_at": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["promotion_id"],
    ),
    (
        "promotion_vehicles",
        ["promotion_id", "vehicle_id", "created_at"],
        {"created_at": parse_ts},
        ["promotion_id", "vehicle_id"],
    ),
    (
        "battery_policies",
        [
            "battery_policy_id",
            "vehicle_id",
            "ownership_model",
            "monthly_fee_vnd",
            "purchase_price_vnd",
            "included_distance_km",
            "excess_fee_per_km_vnd",
            "deposit_amount_vnd",
            "warranty_months",
            "warranty_distance_km",
            "status",
            "valid_from",
            "valid_to",
            "version",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        {
            "monthly_fee_vnd": parse_int,
            "purchase_price_vnd": parse_int,
            "included_distance_km": parse_float,
            "excess_fee_per_km_vnd": parse_int,
            "deposit_amount_vnd": parse_int,
            "warranty_months": parse_int,
            "warranty_distance_km": parse_float,
            "valid_from": parse_ts,
            "valid_to": parse_ts,
            "version": parse_int,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["battery_policy_id"],
    ),
    (
        "feature_definitions",
        [
            "feature_code",
            "name",
            "description",
            "vehicle_type",
            "category",
            "value_type",
            "unit",
            "allowed_values",
            "filter_behavior",
            "status",
            "display_order",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ],
        {
            "display_order": parse_int,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["feature_code"],
    ),
    (
        "vehicle_feature_flags",
        [
            "vehicle_id",
            "feature_code",
            "status",
            "value_text",
            "value_number",
            "value_boolean",
            "verification_status",
            "confidence",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        {
            "value_number": parse_float,
            "value_boolean": parse_bool,
            "confidence": parse_float,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["vehicle_id", "feature_code"],
    ),
    (
        "feature_need_tags",
        ["feature_code", "need_tag", "relevance", "note", "created_by", "created_at", "updated_at"],
        {"relevance": parse_float, "created_at": parse_ts, "updated_at": parse_ts},
        ["feature_code", "need_tag"],
    ),
    (
        "tco_assumptions",
        [
            "assumption_id",
            "vehicle_type",
            "region_code",
            "assumption_version",
            "electricity_vnd_per_kwh",
            "registration_fee_percent",
            "registration_fee_flat_vnd",
            "plate_fee_vnd",
            "inspection_fee_vnd",
            "mandatory_insurance_vnd_per_year",
            "road_fee_vnd_per_year",
            "maintenance_vnd_per_service",
            "maintenance_interval_km",
            "horizon_months",
            "source_note",
            "status",
            "valid_from",
            "valid_to",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "inspection_first_month",
            "inspection_interval_months",
            "inspection_interval_months_after_7y",
        ],
        {
            "assumption_version": parse_int,
            "electricity_vnd_per_kwh": parse_int,
            "registration_fee_percent": parse_float,
            "registration_fee_flat_vnd": parse_int,
            "plate_fee_vnd": parse_int,
            "inspection_fee_vnd": parse_int,
            "mandatory_insurance_vnd_per_year": parse_int,
            "road_fee_vnd_per_year": parse_int,
            "maintenance_vnd_per_service": parse_int,
            "maintenance_interval_km": parse_float,
            "horizon_months": parse_int,
            "valid_from": parse_ts,
            "valid_to": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
            "inspection_first_month": parse_int,
            "inspection_interval_months": parse_int,
            "inspection_interval_months_after_7y": parse_int,
        },
        ["assumption_id"],
    ),
    (
        "vehicle_documents",
        [
            "document_id",
            "vehicle_id",
            "source_document_id",
            "source_content_hash",
            "source_revision",
            "document_type",
            "title",
            "content",
            "chunk_index",
            "section_title",
            "page_number",
            "source_url",
            "embedding_model",
            "embedding_version",
            "status",
            "valid_from",
            "valid_to",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ],
        {
            "chunk_index": parse_int,
            "page_number": parse_int,
            "valid_from": parse_ts,
            "valid_to": parse_ts,
            "approved_at": parse_ts,
            "created_at": parse_ts,
            "updated_at": parse_ts,
        },
        ["document_id"],
    ),
]

JSONB_COLUMNS = {"allowed_values", "eligibility_rules"}


def load_rows(table: str, columns: list[str], parsers: dict[str, callable]) -> list[tuple]:
    path = DATA_DIR / f"{table}.csv"
    rows: list[tuple] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            values = []
            for col in columns:
                raw_val = raw.get(col)
                if col in JSONB_COLUMNS:
                    values.append(parse_text(raw_val))
                    continue
                parser = parsers.get(col, parse_text)
                values.append(parser(raw_val))
            rows.append(tuple(values))
    return rows


def build_insert_sql(table: str, columns: list[str], conflict_cols: list[str]) -> str:
    col_list = ", ".join(columns)
    placeholders = []
    for i, col in enumerate(columns, start=1):
        if col in JSONB_COLUMNS:
            placeholders.append(f"${i}::jsonb")
        else:
            placeholders.append(f"${i}")
    values_list = ", ".join(placeholders)
    conflict = ", ".join(conflict_cols)
    return f"INSERT INTO {table} ({col_list}) VALUES ({values_list}) ON CONFLICT ({conflict}) DO NOTHING"


async def seed(dsn: str, truncate: bool) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        if truncate:
            table_names = ", ".join(t[0] for t in reversed(TABLES))
            await conn.execute(f"TRUNCATE {table_names} CASCADE")
            print(f"Truncated: {table_names}")

        async with conn.transaction():
            for table, columns, parsers, conflict_cols in TABLES:
                rows = load_rows(table, columns, parsers)
                if not rows:
                    print(f"{table}: 0 rows, skip")
                    continue
                sql = build_insert_sql(table, columns, conflict_cols)
                await conn.executemany(sql, rows)
                print(f"{table}: inserted {len(rows)} rows")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default="",
        help="Postgres DSN (sync, no +asyncpg driver prefix)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all target tables (CASCADE) before inserting",
    )
    args = parser.parse_args()
    dsn = (
        args.dsn
        or os.environ.get("PRODUCT_DATABASE_URL_SYNC")
        or os.environ.get("PRODUCT_DATABASE_URL")
        or os.environ.get("AUTH_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DSN
    )
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    asyncio.run(seed(dsn, args.truncate))


if __name__ == "__main__":
    main()
