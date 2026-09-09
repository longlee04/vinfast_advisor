"""CSV import utilities for the Product module.

Đọc các file CSV trong ``data-p150/catalog/`` và trả về domain entities theo
đúng schema mới (entities 1-1 với bảng). Helpers cố tình giữ framework-free để
có thể dùng cho seed script lẫn test.

Dataset nằm trong repo (thư mục crawl/data bị .gitignore chặn nên không dùng
làm nguồn được). Nếu CSV thay đổi cột, cập nhật mapper tương ứng.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.products.domain.entities import (
    BatteryPolicy,
    Car,
    FeatureDefinition,
    FeatureNeedTag,
    Motorbike,
    Promotion,
    PromotionVehicle,
    TcoAssumption,
    Vehicle,
    VehicleFeatureFlag,
    VehiclePrice,
    VehicleShowcaseItem,
)
from src.products.domain.values import (
    BatteryOwnershipModel,
    Currency,
    FeatureDefinitionStatus,
    FeatureFlagStatus,
    FeatureValueType,
    FilterBehavior,
    PromotionType,
    RecordLifecycleStatus,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data-p150" / "catalog"

VEHICLES_CSV = _DATA_DIR / "vehicles.csv"
CARS_CSV = _DATA_DIR / "cars.csv"
MOTORBIKES_CSV = _DATA_DIR / "motorbikes.csv"
VEHICLE_PRICES_CSV = _DATA_DIR / "vehicle_prices.csv"
PROMOTIONS_CSV = _DATA_DIR / "promotions.csv"
PROMOTION_VEHICLES_CSV = _DATA_DIR / "promotion_vehicles.csv"
BATTERY_POLICIES_CSV = _DATA_DIR / "battery_policies.csv"
FEATURE_DEFINITIONS_CSV = _DATA_DIR / "feature_definitions.csv"
VEHICLE_FEATURE_FLAGS_CSV = _DATA_DIR / "vehicle_feature_flags.csv"
TCO_ASSUMPTIONS_CSV = _DATA_DIR / "tco_assumptions.csv"
FEATURE_NEED_TAGS_CSV = _DATA_DIR / "feature_need_tags.csv"
VEHICLE_SHOWCASE_ITEMS_CSV = _DATA_DIR / "vehicle_showcase_items.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opt_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _opt_int(value: str | None) -> int | None:
    dec = _opt_decimal(value)
    if dec is None:
        return None
    return int(dec)


def _opt_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_dt(value: str | None) -> datetime | None:
    text = _opt_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_bool(value: str | None) -> bool | None:
    text = _opt_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in ("true", "t", "1", "yes"):
        return True
    if lowered in ("false", "f", "0", "no"):
        return False
    return None


def _parse_json_object(value: str | None) -> dict[str, object]:
    text = _opt_text(value)
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("eligibility_rules must contain valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError("eligibility_rules must contain a JSON object")
    return parsed


def _enum_or(value: str | None, enum_cls: type, default):
    """Parse một enum từ chuỗi, fallback về ``default`` nếu giá trị không hợp lệ."""
    text = _opt_text(value)
    if text is None:
        return default
    try:
        return enum_cls(text)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_vehicles(csv_path: Path = VEHICLES_CSV) -> Iterator[Vehicle]:
    """Yield Vehicle entities từ ``vehicles.csv``."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield Vehicle(
                vehicle_id=row["vehicle_id"],
                vehicle_type=_enum_or(row.get("vehicle_type"), VehicleType, VehicleType.CAR),
                brand=row.get("brand") or "",
                model_name=row.get("model_name") or "",
                status=_enum_or(row.get("status"), VehicleStatus, VehicleStatus.ACTIVE),
                slug=row.get("slug") or "",
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                variant_name=_opt_text(row.get("variant_name")),
                model_year=_opt_int(row.get("model_year")),
                image_url=_opt_text(row.get("image_url")),
                detail_url=_opt_text(row.get("detail_url")),
                created_by=_opt_text(row.get("created_by")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_cars(csv_path: Path = CARS_CSV) -> Iterator[Car]:
    """Yield Car entities từ ``cars.csv``."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield Car(
                vehicle_id=row["vehicle_id"],
                specs_version=_opt_int(row.get("specs_version")) or 1,
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                body_type=_opt_text(row.get("body_type")),
                seat_count=_opt_int(row.get("seat_count")),
                range_km=_opt_decimal(row.get("range_km")),
                range_cycle=_opt_text(row.get("range_cycle")),
                energy_consumption_kwh_per_100km=_opt_decimal(row.get("energy_consumption_kwh_per_100km")),
                battery_capacity_kwh=_opt_decimal(row.get("battery_capacity_kwh")),
                motor_power_kw=_opt_decimal(row.get("motor_power_kw")),
                torque_nm=_opt_decimal(row.get("torque_nm")),
                max_speed_kmh=_opt_decimal(row.get("max_speed_kmh")),
                acceleration_0_100_seconds=_opt_decimal(row.get("acceleration_0_100_seconds")),
                curb_weight_kg=_opt_decimal(row.get("curb_weight_kg")),
                gross_weight_kg=_opt_decimal(row.get("gross_weight_kg")),
                fast_charge_power_kw=_opt_decimal(row.get("fast_charge_power_kw")),
                fast_charge_time_minutes=_opt_int(row.get("fast_charge_time_minutes")),
                fast_charge_from_percent=_opt_int(row.get("fast_charge_from_percent")),
                fast_charge_to_percent=_opt_int(row.get("fast_charge_to_percent")),
                home_charge_time_minutes=_opt_int(row.get("home_charge_time_minutes")),
                charging_port=_opt_text(row.get("charging_port")),
                cargo_volume_standard_l=_opt_decimal(row.get("cargo_volume_standard_l")),
                cargo_volume_maximum_l=_opt_decimal(row.get("cargo_volume_maximum_l")),
                towing_supported=_parse_bool(row.get("towing_supported")),
                towing_capacity_kg=_opt_decimal(row.get("towing_capacity_kg")),
                effective_from=_parse_dt(row.get("effective_from")),
                effective_to=_parse_dt(row.get("effective_to")),
            )


def load_motorbikes(csv_path: Path = MOTORBIKES_CSV) -> Iterator[Motorbike]:
    """Yield Motorbike entities từ ``motorbikes.csv``."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield Motorbike(
                vehicle_id=row["vehicle_id"],
                specs_version=_opt_int(row.get("specs_version")) or 1,
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                motor_power_w=_opt_int(row.get("motor_power_w")),
                max_power_w=_opt_int(row.get("max_power_w")),
                torque_nm=_opt_decimal(row.get("torque_nm")),
                max_speed_kmh=_opt_decimal(row.get("max_speed_kmh")),
                battery_type=_opt_text(row.get("battery_type")),
                battery_capacity_kwh=_opt_decimal(row.get("battery_capacity_kwh")),
                battery_quantity=_opt_int(row.get("battery_quantity")),
                battery_removable=_parse_bool(row.get("battery_removable")),
                battery_swappable=_parse_bool(row.get("battery_swappable")),
                energy_consumption_kwh_per_100km=_opt_decimal(row.get("energy_consumption_kwh_per_100km")),
                range_min_km=_opt_decimal(row.get("range_min_km")),
                range_max_km=_opt_decimal(row.get("range_max_km")),
                range_cycle=_opt_text(row.get("range_cycle")),
                charging_time_minutes=_opt_int(row.get("charging_time_minutes")),
                charging_method=_opt_text(row.get("charging_method")),
                curb_weight_kg=_opt_decimal(row.get("curb_weight_kg")),
                max_load_kg=_opt_decimal(row.get("max_load_kg")),
                seat_height_mm=_opt_decimal(row.get("seat_height_mm")),
                wheel_size_front_inch=_opt_decimal(row.get("wheel_size_front_inch")),
                wheel_size_rear_inch=_opt_decimal(row.get("wheel_size_rear_inch")),
                license_requirement=None,
                effective_from=_parse_dt(row.get("effective_from")),
                effective_to=_parse_dt(row.get("effective_to")),
            )


def load_vehicle_prices(csv_path: Path = VEHICLE_PRICES_CSV) -> Iterator[VehiclePrice]:
    """Yield VehiclePrice entities từ ``vehicle_prices.csv``."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield VehiclePrice(
                price_id=row["price_id"],
                vehicle_id=row["vehicle_id"],
                price_type=row.get("price_type") or "STARTING_PRICE",
                amount_vnd=_opt_int(row.get("amount_vnd")) or 0,
                currency=Currency.VND,
                region_code=row.get("region_code") or "VN",
                status=_enum_or(row.get("status"), RecordLifecycleStatus, RecordLifecycleStatus.ACTIVE),
                valid_from=_parse_dt(row.get("valid_from")) or datetime.now(),
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                valid_to=_parse_dt(row.get("valid_to")),
                created_by=_opt_text(row.get("created_by")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_promotions(csv_path: Path = PROMOTIONS_CSV) -> Iterator[Promotion]:
    """Yield Promotion entities từ ``promotions.csv``."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield Promotion(
                promotion_id=row["promotion_id"],
                promotion_code=row.get("promotion_code") or "",
                title=row.get("title") or "",
                promotion_type=_enum_or(row.get("promotion_type"), PromotionType, PromotionType.PERCENT_DISCOUNT),
                region_code=row.get("region_code") or "VN",
                eligibility_rules=_parse_json_object(row.get("eligibility_rules")),
                status=_enum_or(row.get("status"), RecordLifecycleStatus, RecordLifecycleStatus.ACTIVE),
                valid_from=_parse_dt(row.get("valid_from")) or datetime.now(),
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                description=_opt_text(row.get("description")),
                discount_amount_vnd=_opt_int(row.get("discount_amount_vnd")),
                discount_percent=_opt_decimal(row.get("discount_percent")),
                valid_to=_parse_dt(row.get("valid_to")),
                created_by=_opt_text(row.get("created_by")),
                approved_by=_opt_text(row.get("approved_by")),
                approved_at=_parse_dt(row.get("approved_at")),
            )


def load_promotion_vehicles(csv_path: Path = PROMOTION_VEHICLES_CSV) -> Iterator[PromotionVehicle]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield PromotionVehicle(
                promotion_id=row["promotion_id"],
                vehicle_id=row["vehicle_id"],
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
            )


def load_battery_policies(csv_path: Path = BATTERY_POLICIES_CSV) -> Iterator[BatteryPolicy]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield BatteryPolicy(
                battery_policy_id=row["battery_policy_id"],
                vehicle_id=row["vehicle_id"],
                ownership_model=_enum_or(
                    row.get("ownership_model"),
                    BatteryOwnershipModel,
                    BatteryOwnershipModel.NOT_APPLICABLE,
                ),
                status=_enum_or(row.get("status"), RecordLifecycleStatus, RecordLifecycleStatus.ACTIVE),
                valid_from=_parse_dt(row.get("valid_from")) or datetime.now(),
                version=_opt_int(row.get("version")) or 1,
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                monthly_fee_vnd=_opt_int(row.get("monthly_fee_vnd")),
                purchase_price_vnd=_opt_int(row.get("purchase_price_vnd")),
                included_distance_km=_opt_decimal(row.get("included_distance_km")),
                excess_fee_per_km_vnd=_opt_int(row.get("excess_fee_per_km_vnd")),
                deposit_amount_vnd=_opt_int(row.get("deposit_amount_vnd")),
                warranty_months=_opt_int(row.get("warranty_months")),
                warranty_distance_km=_opt_decimal(row.get("warranty_distance_km")),
                valid_to=_parse_dt(row.get("valid_to")),
                created_by=_opt_text(row.get("created_by")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_feature_definitions(
    csv_path: Path = FEATURE_DEFINITIONS_CSV,
) -> Iterator[FeatureDefinition]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield FeatureDefinition(
                feature_code=row["feature_code"],
                name=row.get("name") or row["feature_code"],
                category=row.get("category") or "GENERAL",
                value_type=_enum_or(row.get("value_type"), FeatureValueType, FeatureValueType.BOOLEAN),
                filter_behavior=_enum_or(row.get("filter_behavior"), FilterBehavior, FilterBehavior.PREFERENCE),
                status=_enum_or(
                    row.get("status"),
                    FeatureDefinitionStatus,
                    FeatureDefinitionStatus.ACTIVE,
                ),
                display_order=_opt_int(row.get("display_order")) or 0,
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                description=_opt_text(row.get("description")),
                # BUG có sẵn, lộ ra 2026-08-25 khi thêm mười một tính năng CHỈ CÓ
                # trên ô tô: cột `vehicle_type` của CSV bị vứt đi, mọi định nghĩa
                # vào DB với `NULL`. Mà `catalog_reader.active_feature_codes` coi
                # `NULL` là "dùng chung cả hai nhánh", nên câu hỏi lượt 2 cho xe
                # máy điện được phép gợi ý "cửa sổ trời toàn cảnh", "móc kéo moóc".
                # Đúng loại lỗi Sếp đã báo một lần ở nhánh bảng cứng (xem docstring
                # `prompts/feature_askable`), chỉ khác là nhánh DB chưa ai vá.
                vehicle_type=_enum_or(row.get("vehicle_type"), VehicleType, None),
                unit=_opt_text(row.get("unit")),
                allowed_values=None,
                created_by=_opt_text(row.get("created_by")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_vehicle_feature_flags(
    csv_path: Path = VEHICLE_FEATURE_FLAGS_CSV,
) -> Iterator[VehicleFeatureFlag]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield VehicleFeatureFlag(
                vehicle_id=row["vehicle_id"],
                feature_code=row["feature_code"],
                status=_enum_or(row.get("status"), FeatureFlagStatus, FeatureFlagStatus.UNKNOWN),
                verification_status=_enum_or(
                    row.get("verification_status"),
                    VerificationStatus,
                    VerificationStatus.PENDING,
                ),
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                value_text=_opt_text(row.get("value_text")),
                value_number=_opt_decimal(row.get("value_number")),
                value_boolean=_parse_bool(row.get("value_boolean")),
                confidence=_opt_decimal(row.get("confidence")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_tco_assumptions(csv_path: Path = TCO_ASSUMPTIONS_CSV) -> Iterator[TcoAssumption]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield TcoAssumption(
                assumption_id=row["assumption_id"],
                vehicle_type=_enum_or(row.get("vehicle_type"), VehicleType, VehicleType.CAR),
                region_code=_opt_text(row.get("region_code")) or "VN",
                assumption_version=_opt_int(row.get("assumption_version")) or 1,
                electricity_vnd_per_kwh=_opt_int(row.get("electricity_vnd_per_kwh")) or 0,
                inspection_first_month=_opt_int(row.get("inspection_first_month")) or 0,
                inspection_interval_months=_opt_int(row.get("inspection_interval_months")) or 0,
                inspection_interval_months_after_7y=(_opt_int(row.get("inspection_interval_months_after_7y")) or 0),
                horizon_months=_opt_int(row.get("horizon_months")) or 60,
                status=_enum_or(row.get("status"), RecordLifecycleStatus, RecordLifecycleStatus.DRAFT),
                valid_from=_parse_dt(row.get("valid_from")) or datetime.now(),
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                registration_fee_percent=_opt_decimal(row.get("registration_fee_percent")),
                registration_fee_flat_vnd=_opt_int(row.get("registration_fee_flat_vnd")),
                plate_fee_vnd=_opt_int(row.get("plate_fee_vnd")),
                inspection_fee_vnd=_opt_int(row.get("inspection_fee_vnd")),
                mandatory_insurance_vnd_per_year=_opt_int(row.get("mandatory_insurance_vnd_per_year")),
                road_fee_vnd_per_year=_opt_int(row.get("road_fee_vnd_per_year")),
                maintenance_vnd_per_service=_opt_int(row.get("maintenance_vnd_per_service")),
                maintenance_interval_km=_opt_decimal(row.get("maintenance_interval_km")),
                source_note=_opt_text(row.get("source_note")),
                valid_to=_parse_dt(row.get("valid_to")),
                created_by=_opt_text(row.get("created_by")),
                updated_by=_opt_text(row.get("updated_by")),
            )


def load_feature_need_tags(csv_path: Path = FEATURE_NEED_TAGS_CSV) -> Iterator[FeatureNeedTag]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield FeatureNeedTag(
                feature_code=row["feature_code"],
                need_tag=row["need_tag"].strip().upper(),
                relevance=_opt_decimal(row.get("relevance")) or Decimal("1.00"),
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
                note=_opt_text(row.get("note")),
                created_by=_opt_text(row.get("created_by")),
            )


def load_vehicle_showcase_items(
    csv_path: Path = VEHICLE_SHOWCASE_ITEMS_CSV,
) -> Iterator[VehicleShowcaseItem]:
    """Yield additive, source-attributed presentation content."""

    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            yield VehicleShowcaseItem(
                showcase_item_id=row["showcase_item_id"],
                vehicle_id=row["vehicle_id"],
                section_key=row["section_key"],
                item_key=row["item_key"],
                title=row["title"],
                description=_opt_text(row.get("description")),
                media_url=_opt_text(row.get("media_url")),
                media_alt=_opt_text(row.get("media_alt")),
                display_order=_opt_int(row.get("display_order")) or 0,
                source_url=row["source_url"],
                source_retrieved_at=_parse_dt(row.get("source_retrieved_at")) or datetime.now(),
                status=_opt_text(row.get("status")) or "ACTIVE",
                created_at=_parse_dt(row.get("created_at")) or datetime.now(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.now(),
            )


@dataclass(frozen=True, slots=True)
class CatalogDataset:
    """Bundle toàn bộ entity load từ thư mục CSV."""

    vehicles: list[Vehicle]
    cars: list[Car]
    motorbikes: list[Motorbike]
    prices: list[VehiclePrice]
    promotions: list[Promotion]
    promotion_vehicles: list[PromotionVehicle]
    battery_policies: list[BatteryPolicy]
    feature_definitions: list[FeatureDefinition]
    feature_flags: list[VehicleFeatureFlag]
    tco_assumptions: list[TcoAssumption]
    feature_need_tags: list[FeatureNeedTag]
    showcase_items: list[VehicleShowcaseItem]


def load_all(data_dir: Path | None = None) -> CatalogDataset:
    base = data_dir or _DATA_DIR
    return CatalogDataset(
        vehicles=list(load_vehicles(base / "vehicles.csv")),
        cars=list(load_cars(base / "cars.csv")),
        motorbikes=list(load_motorbikes(base / "motorbikes.csv")),
        prices=list(load_vehicle_prices(base / "vehicle_prices.csv")),
        promotions=list(load_promotions(base / "promotions.csv")),
        promotion_vehicles=list(load_promotion_vehicles(base / "promotion_vehicles.csv")),
        battery_policies=list(load_battery_policies(base / "battery_policies.csv")),
        feature_definitions=list(load_feature_definitions(base / "feature_definitions.csv")),
        feature_flags=list(load_vehicle_feature_flags(base / "vehicle_feature_flags.csv")),
        tco_assumptions=list(load_tco_assumptions(base / "tco_assumptions.csv")),
        feature_need_tags=list(load_feature_need_tags(base / "feature_need_tags.csv")),
        showcase_items=list(load_vehicle_showcase_items(base / "vehicle_showcase_items.csv")),
    )


__all__ = [
    "BATTERY_POLICIES_CSV",
    "CARS_CSV",
    "CatalogDataset",
    "FEATURE_DEFINITIONS_CSV",
    "FEATURE_NEED_TAGS_CSV",
    "MOTORBIKES_CSV",
    "PROMOTIONS_CSV",
    "PROMOTION_VEHICLES_CSV",
    "TCO_ASSUMPTIONS_CSV",
    "VEHICLES_CSV",
    "VEHICLE_FEATURE_FLAGS_CSV",
    "VEHICLE_PRICES_CSV",
    "VEHICLE_SHOWCASE_ITEMS_CSV",
    "load_all",
    "load_battery_policies",
    "load_cars",
    "load_feature_definitions",
    "load_feature_need_tags",
    "load_motorbikes",
    "load_promotion_vehicles",
    "load_promotions",
    "load_tco_assumptions",
    "load_vehicle_feature_flags",
    "load_vehicle_prices",
    "load_vehicle_showcase_items",
    "load_vehicles",
]
