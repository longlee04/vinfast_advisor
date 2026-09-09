"""Seed script — nạp dữ liệu từ CSV refactor vào DB theo schema mới.

Idempotent: chạy nhiều lần vẫn an toàn (dùng ``INSERT ... ON CONFLICT DO NOTHING``
cho parent rows; relations được kiểm tra trước khi insert).
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.products.infrastructure.csv_import import load_all
from src.products.infrastructure.models import (
    BatteryPolicyRow,
    CarSpecRow,
    FeatureDefinitionRow,
    FeatureNeedTagRow,
    MotorbikeSpecRow,
    PromotionRow,
    PromotionVehicleRow,
    TcoAssumptionRow,
    VehicleFeatureFlagRow,
    VehiclePriceRow,
    VehicleRow,
    VehicleShowcaseItemRow,
)


def _resolve_database_url() -> str:
    url = os.environ.get(
        "PRODUCT_DATABASE_URL",
        os.environ.get("AUTH_DATABASE_URL", "postgresql+asyncpg://p150_auth:p150_local_dev@postgres:5432/p150_auth"),
    )
    try:
        socket.gethostbyname("postgres")
    except socket.gaierror:
        url = url.replace("postgres:", "localhost:")
    return url


async def _seed(session: AsyncSession) -> dict[str, int]:
    dataset = load_all()
    counts: dict[str, int] = {}

    # 1) vehicles
    rows = [
        {
            "vehicle_id": v.vehicle_id,
            "vehicle_type": v.vehicle_type.value,
            "brand": v.brand,
            "model_name": v.model_name,
            "variant_name": v.variant_name,
            "model_year": v.model_year,
            "status": v.status.value,
            "slug": v.slug,
            "image_url": v.image_url,
            "detail_url": v.detail_url,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
            "created_by": v.created_by,
            "updated_by": v.updated_by,
        }
        for v in dataset.vehicles
    ]
    if rows:
        stmt = pg_insert(VehicleRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["vehicle_id"])
        await session.execute(stmt)
        counts["vehicles"] = len(rows)

    # 2) cars
    rows = [
        {
            "vehicle_id": c.vehicle_id,
            "body_type": c.body_type,
            "seat_count": c.seat_count,
            "range_km": c.range_km,
            "range_cycle": c.range_cycle,
            "energy_consumption_kwh_per_100km": c.energy_consumption_kwh_per_100km,
            "battery_capacity_kwh": c.battery_capacity_kwh,
            "motor_power_kw": c.motor_power_kw,
            "torque_nm": c.torque_nm,
            "max_speed_kmh": c.max_speed_kmh,
            "acceleration_0_100_seconds": c.acceleration_0_100_seconds,
            "curb_weight_kg": c.curb_weight_kg,
            "gross_weight_kg": c.gross_weight_kg,
            "fast_charge_power_kw": c.fast_charge_power_kw,
            "fast_charge_time_minutes": c.fast_charge_time_minutes,
            "fast_charge_from_percent": c.fast_charge_from_percent,
            "fast_charge_to_percent": c.fast_charge_to_percent,
            "home_charge_time_minutes": c.home_charge_time_minutes,
            "charging_port": c.charging_port,
            "cargo_volume_standard_l": c.cargo_volume_standard_l,
            "cargo_volume_maximum_l": c.cargo_volume_maximum_l,
            "towing_supported": c.towing_supported,
            "towing_capacity_kg": c.towing_capacity_kg,
            "specs_version": c.specs_version,
            "effective_from": c.effective_from,
            "effective_to": c.effective_to,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in dataset.cars
    ]
    if rows:
        stmt = pg_insert(CarSpecRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["vehicle_id"])
        await session.execute(stmt)
        counts["cars"] = len(rows)

    # 3) motorbikes
    rows = [
        {
            "vehicle_id": m.vehicle_id,
            "motor_power_w": m.motor_power_w,
            "max_power_w": m.max_power_w,
            "torque_nm": m.torque_nm,
            "max_speed_kmh": m.max_speed_kmh,
            "battery_type": m.battery_type,
            "battery_capacity_kwh": m.battery_capacity_kwh,
            "battery_quantity": m.battery_quantity,
            "battery_removable": m.battery_removable,
            "battery_swappable": m.battery_swappable,
            "energy_consumption_kwh_per_100km": m.energy_consumption_kwh_per_100km,
            "range_min_km": m.range_min_km,
            "range_max_km": m.range_max_km,
            "range_cycle": m.range_cycle,
            "charging_time_minutes": m.charging_time_minutes,
            "charging_method": m.charging_method,
            "curb_weight_kg": m.curb_weight_kg,
            "max_load_kg": m.max_load_kg,
            "seat_height_mm": m.seat_height_mm,
            "wheel_size_front_inch": m.wheel_size_front_inch,
            "wheel_size_rear_inch": m.wheel_size_rear_inch,
            "license_requirement": m.license_requirement.value if m.license_requirement else None,
            "specs_version": m.specs_version,
            "effective_from": m.effective_from,
            "effective_to": m.effective_to,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }
        for m in dataset.motorbikes
    ]
    if rows:
        stmt = pg_insert(MotorbikeSpecRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["vehicle_id"])
        await session.execute(stmt)
        counts["motorbikes"] = len(rows)

    # 4) vehicle_prices
    rows = [
        {
            "price_id": p.price_id,
            "vehicle_id": p.vehicle_id,
            "price_type": p.price_type,
            "amount_vnd": p.amount_vnd,
            "currency": p.currency.value,
            "region_code": p.region_code,
            "status": p.status.value,
            "valid_from": p.valid_from,
            "valid_to": p.valid_to,
            "created_by": p.created_by,
            "updated_by": p.updated_by,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in dataset.prices
    ]
    if rows:
        stmt = pg_insert(VehiclePriceRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["price_id"])
        await session.execute(stmt)
        counts["vehicle_prices"] = len(rows)

    # 5) promotions
    rows = [
        {
            "promotion_id": p.promotion_id,
            "promotion_code": p.promotion_code,
            "title": p.title,
            "description": p.description,
            "promotion_type": p.promotion_type.value,
            "discount_amount_vnd": p.discount_amount_vnd,
            "discount_percent": p.discount_percent,
            "region_code": p.region_code,
            "eligibility_rules": p.eligibility_rules,
            "status": p.status.value,
            "valid_from": p.valid_from,
            "valid_to": p.valid_to,
            "created_by": p.created_by,
            "approved_by": p.approved_by,
            "approved_at": p.approved_at,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in dataset.promotions
    ]
    if rows:
        stmt = pg_insert(PromotionRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["promotion_id"])
        await session.execute(stmt)
        counts["promotions"] = len(rows)

    # 6) promotion_vehicles
    rows = [
        {
            "promotion_id": pv.promotion_id,
            "vehicle_id": pv.vehicle_id,
            "created_at": pv.created_at,
        }
        for pv in dataset.promotion_vehicles
    ]
    if rows:
        stmt = pg_insert(PromotionVehicleRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["promotion_id", "vehicle_id"])
        await session.execute(stmt)
        counts["promotion_vehicles"] = len(rows)

    # 7) battery_policies
    rows = [
        {
            "battery_policy_id": bp.battery_policy_id,
            "vehicle_id": bp.vehicle_id,
            "ownership_model": bp.ownership_model.value,
            "monthly_fee_vnd": bp.monthly_fee_vnd,
            "purchase_price_vnd": bp.purchase_price_vnd,
            "included_distance_km": bp.included_distance_km,
            "excess_fee_per_km_vnd": bp.excess_fee_per_km_vnd,
            "deposit_amount_vnd": bp.deposit_amount_vnd,
            "warranty_months": bp.warranty_months,
            "warranty_distance_km": bp.warranty_distance_km,
            "status": bp.status.value,
            "valid_from": bp.valid_from,
            "valid_to": bp.valid_to,
            "version": bp.version,
            "created_by": bp.created_by,
            "updated_by": bp.updated_by,
            "created_at": bp.created_at,
            "updated_at": bp.updated_at,
        }
        for bp in dataset.battery_policies
    ]
    if rows:
        stmt = pg_insert(BatteryPolicyRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["battery_policy_id"])
        await session.execute(stmt)
        counts["battery_policies"] = len(rows)

    # 8) feature_definitions
    rows = [
        {
            "feature_code": fd.feature_code,
            "name": fd.name,
            "description": fd.description,
            "vehicle_type": fd.vehicle_type.value if fd.vehicle_type else None,
            "category": fd.category,
            "value_type": fd.value_type.value,
            "unit": fd.unit,
            "allowed_values": fd.allowed_values,
            "filter_behavior": fd.filter_behavior.value,
            "status": fd.status.value,
            "display_order": fd.display_order,
            "created_at": fd.created_at,
            "updated_at": fd.updated_at,
            "created_by": fd.created_by,
            "updated_by": fd.updated_by,
        }
        for fd in dataset.feature_definitions
    ]
    if rows:
        stmt = pg_insert(FeatureDefinitionRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["feature_code"])
        await session.execute(stmt)
        counts["feature_definitions"] = len(rows)

    # 9) vehicle_feature_flags
    rows = [
        {
            "vehicle_id": f.vehicle_id,
            "feature_code": f.feature_code,
            "status": f.status.value,
            "value_text": f.value_text,
            "value_number": f.value_number,
            "value_boolean": f.value_boolean,
            "verification_status": f.verification_status.value,
            "confidence": f.confidence,
            "updated_by": f.updated_by,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
        }
        for f in dataset.feature_flags
    ]
    if rows:
        stmt = pg_insert(VehicleFeatureFlagRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["vehicle_id", "feature_code"])
        await session.execute(stmt)
        counts["vehicle_feature_flags"] = len(rows)

    # 10) feature_need_tags — phai sau feature_definitions (FK CASCADE)
    rows = [
        {
            "feature_code": t.feature_code,
            "need_tag": t.need_tag,
            "relevance": t.relevance,
            "note": t.note,
            "created_by": t.created_by,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in dataset.feature_need_tags
    ]
    if rows:
        stmt = pg_insert(FeatureNeedTagRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["feature_code", "need_tag"])
        await session.execute(stmt)
        counts["feature_need_tags"] = len(rows)

    # 11) tco_assumptions — doc lap, khong FK sang bang nao
    rows = [
        {
            "assumption_id": a.assumption_id,
            "vehicle_type": a.vehicle_type.value,
            "region_code": a.region_code,
            "assumption_version": a.assumption_version,
            "electricity_vnd_per_kwh": a.electricity_vnd_per_kwh,
            "inspection_first_month": a.inspection_first_month,
            "inspection_interval_months": a.inspection_interval_months,
            "inspection_interval_months_after_7y": a.inspection_interval_months_after_7y,
            "registration_fee_percent": a.registration_fee_percent,
            "registration_fee_flat_vnd": a.registration_fee_flat_vnd,
            "plate_fee_vnd": a.plate_fee_vnd,
            "inspection_fee_vnd": a.inspection_fee_vnd,
            "mandatory_insurance_vnd_per_year": a.mandatory_insurance_vnd_per_year,
            "road_fee_vnd_per_year": a.road_fee_vnd_per_year,
            "maintenance_vnd_per_service": a.maintenance_vnd_per_service,
            "maintenance_interval_km": a.maintenance_interval_km,
            "horizon_months": a.horizon_months,
            "source_note": a.source_note,
            "status": a.status.value,
            "valid_from": a.valid_from,
            "valid_to": a.valid_to,
            "created_by": a.created_by,
            "updated_by": a.updated_by,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
        for a in dataset.tco_assumptions
    ]
    if rows:
        stmt = pg_insert(TcoAssumptionRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["assumption_id"])
        await session.execute(stmt)
        counts["tco_assumptions"] = len(rows)

    # 12) source-attributed showcase content — additive and never updates old rows
    rows = [
        {
            "showcase_item_id": item.showcase_item_id,
            "vehicle_id": item.vehicle_id,
            "section_key": item.section_key,
            "item_key": item.item_key,
            "title": item.title,
            "description": item.description,
            "media_url": item.media_url,
            "media_alt": item.media_alt,
            "display_order": item.display_order,
            "source_url": item.source_url,
            "source_retrieved_at": item.source_retrieved_at,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in dataset.showcase_items
    ]
    if rows:
        stmt = pg_insert(VehicleShowcaseItemRow).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["showcase_item_id"])
        await session.execute(stmt)
        counts["vehicle_showcase_items"] = len(rows)

    return counts


async def seed_database() -> dict[str, int]:
    url = _resolve_database_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session, session.begin():
            counts = await _seed(session)
    finally:
        await engine.dispose()
    return counts


if __name__ == "__main__":
    started = datetime.now(UTC)
    summary = asyncio.run(seed_database())
    print("✅ Catalog seeded")
    for table, n in summary.items():
        print(f"  {table:<22} {n}")
    print(f"⏱  Elapsed: {(datetime.now(UTC) - started).total_seconds():.2f}s")
