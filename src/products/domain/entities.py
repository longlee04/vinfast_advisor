"""Entity thuần dữ liệu, 1-1 với 11 bảng ở docs/vehicle-catalog-schema.md mục 4.

`vehicle_documents` không nằm ở đây — bảng đó do module document sở hữu
(src/document/domain/entities.py), product chỉ đọc qua repository riêng.

Không import SQLAlchemy — ORM mapping nằm ở infrastructure/models.py. Validate
nghiệp vụ (CHECK constraint tương đương) thuộc application service ở boundary,
không lặp lại trong entity vì DB đã ràng buộc và đây chỉ là data holder.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .values import (
    BatteryOwnershipModel,
    Currency,
    FeatureDefinitionStatus,
    FeatureFlagStatus,
    FeatureValueType,
    FilterBehavior,
    LicenseRequirement,
    PromotionType,
    RecordLifecycleStatus,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
)


@dataclass(frozen=True, slots=True)
class Vehicle:
    vehicle_id: str
    vehicle_type: VehicleType
    brand: str
    model_name: str
    status: VehicleStatus
    slug: str
    created_at: datetime
    updated_at: datetime
    variant_name: str | None = None
    model_year: int | None = None
    image_url: str | None = None
    detail_url: str | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class Car:
    vehicle_id: str
    specs_version: int
    created_at: datetime
    updated_at: datetime
    body_type: str | None = None
    seat_count: int | None = None
    range_km: Decimal | None = None
    range_cycle: str | None = None
    energy_consumption_kwh_per_100km: Decimal | None = None
    battery_capacity_kwh: Decimal | None = None
    motor_power_kw: Decimal | None = None
    torque_nm: Decimal | None = None
    max_speed_kmh: Decimal | None = None
    acceleration_0_100_seconds: Decimal | None = None
    curb_weight_kg: Decimal | None = None
    gross_weight_kg: Decimal | None = None
    fast_charge_power_kw: Decimal | None = None
    fast_charge_time_minutes: int | None = None
    fast_charge_from_percent: int | None = None
    fast_charge_to_percent: int | None = None
    home_charge_time_minutes: int | None = None
    charging_port: str | None = None
    cargo_volume_standard_l: Decimal | None = None
    cargo_volume_maximum_l: Decimal | None = None
    towing_supported: bool | None = None
    towing_capacity_kg: Decimal | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class Motorbike:
    vehicle_id: str
    specs_version: int
    created_at: datetime
    updated_at: datetime
    motor_power_w: int | None = None
    max_power_w: int | None = None
    torque_nm: Decimal | None = None
    max_speed_kmh: Decimal | None = None
    battery_type: str | None = None
    battery_capacity_kwh: Decimal | None = None
    battery_quantity: int | None = None
    battery_removable: bool | None = None
    battery_swappable: bool | None = None
    energy_consumption_kwh_per_100km: Decimal | None = None
    range_min_km: Decimal | None = None
    range_max_km: Decimal | None = None
    range_cycle: str | None = None
    charging_time_minutes: int | None = None
    charging_method: str | None = None
    curb_weight_kg: Decimal | None = None
    max_load_kg: Decimal | None = None
    seat_height_mm: Decimal | None = None
    wheel_size_front_inch: Decimal | None = None
    wheel_size_rear_inch: Decimal | None = None
    license_requirement: LicenseRequirement | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class VehiclePrice:
    price_id: str
    vehicle_id: str
    price_type: str
    amount_vnd: int
    currency: Currency
    region_code: str
    status: RecordLifecycleStatus
    valid_from: datetime
    created_at: datetime
    updated_at: datetime
    valid_to: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class Promotion:
    promotion_id: str
    promotion_code: str
    title: str
    promotion_type: PromotionType
    region_code: str
    eligibility_rules: dict[str, object]
    status: RecordLifecycleStatus
    valid_from: datetime
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    discount_amount_vnd: int | None = None
    discount_percent: Decimal | None = None
    valid_to: datetime | None = None
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    # Fold #5 (review đợt 5): phân loại quà tặng cho GIFT — CHARGING / WARRANTY /
    # OTHER. T3 migration thêm cột `gift_group` trên bảng promotions.
    gift_group: str | None = None
    # Plan Customer 360 Phase 5A — rào chắn ưu đãi.
    stackable: bool = False
    priority: int = 100
    max_uses: int | None = None
    used_count: int = 0
    requires_advisor_approval: bool = True
    advisor_max_discount_vnd: int | None = None
    source_meta: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PromotionVehicle:
    promotion_id: str
    vehicle_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BatteryPolicy:
    battery_policy_id: str
    vehicle_id: str
    ownership_model: BatteryOwnershipModel
    status: RecordLifecycleStatus
    valid_from: datetime
    version: int
    created_at: datetime
    updated_at: datetime
    monthly_fee_vnd: int | None = None
    purchase_price_vnd: int | None = None
    included_distance_km: Decimal | None = None
    excess_fee_per_km_vnd: int | None = None
    deposit_amount_vnd: int | None = None
    warranty_months: int | None = None
    warranty_distance_km: Decimal | None = None
    valid_to: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_code: str
    name: str
    category: str
    value_type: FeatureValueType
    filter_behavior: FilterBehavior
    status: FeatureDefinitionStatus
    display_order: int
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    vehicle_type: VehicleType | None = None
    unit: str | None = None
    allowed_values: list[object] | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class VehicleFeatureFlag:
    vehicle_id: str
    feature_code: str
    status: FeatureFlagStatus
    verification_status: VerificationStatus
    created_at: datetime
    updated_at: datetime
    value_text: str | None = None
    value_number: Decimal | None = None
    value_boolean: bool | None = None
    confidence: Decimal | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class TcoAssumption:
    assumption_id: str
    vehicle_type: VehicleType
    region_code: str
    assumption_version: int
    electricity_vnd_per_kwh: int
    inspection_first_month: int
    inspection_interval_months: int
    inspection_interval_months_after_7y: int
    horizon_months: int
    status: RecordLifecycleStatus
    valid_from: datetime
    created_at: datetime
    updated_at: datetime
    registration_fee_percent: Decimal | None = None
    registration_fee_flat_vnd: int | None = None
    plate_fee_vnd: int | None = None
    inspection_fee_vnd: int | None = None
    mandatory_insurance_vnd_per_year: int | None = None
    road_fee_vnd_per_year: int | None = None
    maintenance_vnd_per_service: int | None = None
    maintenance_interval_km: Decimal | None = None
    source_note: str | None = None
    valid_to: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureNeedTag:
    feature_code: str
    need_tag: str
    relevance: Decimal
    created_at: datetime
    updated_at: datetime
    note: str | None = None
    created_by: str | None = None


@dataclass(frozen=True, slots=True)
class VehicleShowcaseItem:
    """Marketing content added alongside, never over, the core vehicle catalog."""

    showcase_item_id: str
    vehicle_id: str
    section_key: str
    item_key: str
    title: str
    display_order: int
    source_url: str
    source_retrieved_at: datetime
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    media_url: str | None = None
    media_alt: str | None = None
    status: str = "ACTIVE"
