"""SQLAlchemy ORM models for the Vehicle Catalog (Refactored Schema).

Bám sát schema định nghĩa tại
``migrations/products/versions/d4e5f6a7b8c9_product_schema.py``. Không thêm/bớt
cột — bất kỳ sai lệch nào sẽ làm migration fail.

Lưu ý: ``vehicle_documents`` được document module sở hữu, nhưng repository của
product vẫn cần mapping cho quan hệ n-1, vì thế ORM vẫn khai báo nhưng insert do
document module chịu trách nhiệm. Nếu project chưa có document module chạy,
seed_catalog sẽ tự bỏ qua.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ProductBase(DeclarativeBase):
    """Declarative base cho Product module models."""


# ---------------------------------------------------------------------------
# 1. vehicles (Core Registry)
# ---------------------------------------------------------------------------


class VehicleRow(ProductBase):
    __tablename__ = "vehicles"

    vehicle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    variant_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="DRAFT")
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    car: Mapped[CarSpecRow | None] = relationship(
        "CarSpecRow", back_populates="vehicle", uselist=False, cascade="all, delete-orphan"
    )
    motorbike: Mapped[MotorbikeSpecRow | None] = relationship(
        "MotorbikeSpecRow", back_populates="vehicle", uselist=False, cascade="all, delete-orphan"
    )
    prices: Mapped[list[VehiclePriceRow]] = relationship(
        "VehiclePriceRow", back_populates="vehicle", cascade="all, delete-orphan"
    )
    battery_policies: Mapped[list[BatteryPolicyRow]] = relationship(
        "BatteryPolicyRow", back_populates="vehicle", cascade="all, delete-orphan"
    )
    feature_flags: Mapped[list[VehicleFeatureFlagRow]] = relationship(
        "VehicleFeatureFlagRow", back_populates="vehicle", cascade="all, delete-orphan"
    )
    promotion_links: Mapped[list[PromotionVehicleRow]] = relationship(
        "PromotionVehicleRow", back_populates="vehicle", cascade="all, delete-orphan"
    )
    showcase_items: Mapped[list[VehicleShowcaseItemRow]] = relationship(
        "VehicleShowcaseItemRow", back_populates="vehicle", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')", name="ck_vehicles_type"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED')", name="ck_vehicles_status"),
        UniqueConstraint("slug", name="uq_vehicles_slug"),
        UniqueConstraint(
            "vehicle_type",
            "brand",
            "model_name",
            "variant_name",
            "model_year",
            name="uq_vehicles_identity",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_vehicles_type_status", "vehicle_type", "status"),
    )


# ---------------------------------------------------------------------------
# 2. cars
# ---------------------------------------------------------------------------


class CarSpecRow(ProductBase):
    __tablename__ = "cars"

    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    body_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    range_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    range_cycle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    energy_consumption_kwh_per_100km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    motor_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    torque_nm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    max_speed_kmh: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    acceleration_0_100_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    curb_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    gross_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fast_charge_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    fast_charge_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fast_charge_from_percent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fast_charge_to_percent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    home_charge_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charging_port: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cargo_volume_standard_l: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cargo_volume_maximum_l: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    towing_supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    towing_capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    specs_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="car")

    __table_args__ = (
        CheckConstraint("seat_count IS NULL OR seat_count > 0", name="ck_cars_seats"),
        CheckConstraint("range_km IS NULL OR range_km >= 0", name="ck_cars_range"),
        CheckConstraint(
            "fast_charge_from_percent IS NULL OR fast_charge_to_percent IS NULL "
            "OR fast_charge_to_percent > fast_charge_from_percent",
            name="ck_cars_charge_window",
        ),
        Index("ix_cars_filter_range_seats", "range_km", "seat_count"),
    )


# ---------------------------------------------------------------------------
# 3. motorbikes
# ---------------------------------------------------------------------------


class MotorbikeSpecRow(ProductBase):
    __tablename__ = "motorbikes"

    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    motor_power_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_power_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    torque_nm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_speed_kmh: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    battery_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    battery_quantity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    battery_removable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    battery_swappable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    energy_consumption_kwh_per_100km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    range_min_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    range_max_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    range_cycle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    charging_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charging_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    curb_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_load_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    seat_height_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    wheel_size_front_inch: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    wheel_size_rear_inch: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    license_requirement: Mapped[str | None] = mapped_column(String(32), nullable=True)
    specs_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="motorbike")

    __table_args__ = (
        CheckConstraint(
            "range_min_km IS NULL OR range_max_km IS NULL OR range_max_km >= range_min_km",
            name="ck_motorbikes_range",
        ),
        CheckConstraint(
            "license_requirement IS NULL OR license_requirement IN ('NONE', 'A1', 'A', 'UNKNOWN')",
            name="ck_motorbikes_license",
        ),
        Index("ix_motorbikes_filter_range_load", "range_max_km", "max_load_kg"),
    )


# ---------------------------------------------------------------------------
# 4. vehicle_prices
# ---------------------------------------------------------------------------


class VehiclePriceRow(ProductBase):
    __tablename__ = "vehicle_prices"

    price_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT"),
        nullable=False,
    )
    price_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="VND")
    region_code: Mapped[str] = mapped_column(String(16), nullable=False, server_default="VN")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="prices")

    __table_args__ = (
        CheckConstraint("amount_vnd >= 0", name="ck_vehicle_prices_amount"),
        CheckConstraint("currency = 'VND'", name="ck_vehicle_prices_currency"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="ck_vehicle_prices_status",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_vehicle_prices_period"),
        Index(
            "ix_vehicle_prices_current_filter",
            "vehicle_id",
            "price_type",
            "status",
            "valid_from",
            "valid_to",
        ),
        Index(
            "uq_vehicle_prices_one_active",
            "vehicle_id",
            "price_type",
            "region_code",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )


# ---------------------------------------------------------------------------
# 5. promotions & promotion_vehicles
# ---------------------------------------------------------------------------


class PromotionRow(ProductBase):
    __tablename__ = "promotions"

    promotion_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    promotion_code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_type: Mapped[str] = mapped_column(String(40), nullable=False)
    discount_amount_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    region_code: Mapped[str] = mapped_column(String(16), nullable=False, server_default="VN")
    eligibility_rules: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gift_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Plan Customer 360 Phase 5A (migration c3d4e5f6a7b8).
    stackable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("100"))
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    requires_advisor_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    advisor_max_discount_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_meta: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicles: Mapped[list[PromotionVehicleRow]] = relationship(
        "PromotionVehicleRow", back_populates="promotion", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("promotion_code", name="uq_promotions_code"),
        CheckConstraint(
            "promotion_type IN ('FIXED_DISCOUNT', 'PERCENT_DISCOUNT', 'GIFT', "
            "'FINANCING', 'REGISTRATION_SUPPORT', 'OTHER')",
            name="ck_promotions_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'UNVERIFIED', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="ck_promotions_status",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_promotions_period"),
        CheckConstraint(
            "discount_amount_vnd IS NULL OR discount_amount_vnd >= 0",
            name="ck_promotions_discount",
        ),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="ck_promotions_max_uses"),
        CheckConstraint(
            "used_count >= 0 AND (max_uses IS NULL OR used_count <= max_uses)", name="ck_promotions_used_count"
        ),
        CheckConstraint(
            "advisor_max_discount_vnd IS NULL OR advisor_max_discount_vnd >= 0",
            name="ck_promotions_advisor_max_discount",
        ),
        Index(
            "ix_promotions_active_period",
            "status",
            "region_code",
            "valid_from",
            "valid_to",
        ),
    )


class OfferAdjustmentPolicyRow(ProductBase):
    """ADMIN-configured adjustment boundaries per promotion type."""

    __tablename__ = "offer_adjustment_policies"

    promotion_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    adjust_min_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    adjust_max_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    adjust_min_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    adjust_max_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    financing_months_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    financing_months_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    financing_support_max_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gift_value_max_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    allowed_gift_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    registration_support_max_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    other_max_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OfferAdjustmentLogRow(ProductBase):
    """Audit log for every advisor offer adjustment."""

    __tablename__ = "offer_adjustment_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    review_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    advisor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    promotion_code: Mapped[str] = mapped_column(String(100), nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromotionVehicleRow(ProductBase):
    __tablename__ = "promotion_vehicles"

    promotion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("promotions.promotion_id", ondelete="CASCADE"),
        primary_key=True,
    )
    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    promotion: Mapped[PromotionRow] = relationship("PromotionRow", back_populates="vehicles")
    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="promotion_links")

    __table_args__ = (Index("ix_promotion_vehicles_vehicle", "vehicle_id", "promotion_id"),)


# ---------------------------------------------------------------------------
# 6. battery_policies
# ---------------------------------------------------------------------------


class BatteryPolicyRow(ProductBase):
    __tablename__ = "battery_policies"

    battery_policy_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="RESTRICT"),
        nullable=False,
    )
    ownership_model: Mapped[str] = mapped_column(String(32), nullable=False)
    monthly_fee_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    purchase_price_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    included_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    excess_fee_per_km_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deposit_amount_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="battery_policies")

    __table_args__ = (
        CheckConstraint(
            "ownership_model IN ('INCLUDED', 'PURCHASE', 'SUBSCRIPTION', 'SWAP', 'NOT_APPLICABLE')",
            name="ck_battery_policies_model",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="ck_battery_policies_status",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_battery_policies_period"),
        CheckConstraint(
            "(monthly_fee_vnd IS NULL OR monthly_fee_vnd >= 0) "
            "AND (purchase_price_vnd IS NULL OR purchase_price_vnd >= 0) "
            "AND (deposit_amount_vnd IS NULL OR deposit_amount_vnd >= 0) "
            "AND (excess_fee_per_km_vnd IS NULL OR excess_fee_per_km_vnd >= 0)",
            name="ck_battery_policies_amounts",
        ),
        Index(
            "ix_battery_policies_vehicle_period",
            "vehicle_id",
            "status",
            "valid_from",
            "valid_to",
        ),
    )


# ---------------------------------------------------------------------------
# 7. feature_definitions & vehicle_feature_flags
# ---------------------------------------------------------------------------


class FeatureDefinitionRow(ProductBase):
    __tablename__ = "feature_definitions"

    feature_code: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="BOOLEAN")
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_values: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    filter_behavior: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PREFERENCE")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="ACTIVE")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    flags: Mapped[list[VehicleFeatureFlagRow]] = relationship(
        "VehicleFeatureFlagRow", back_populates="feature_def", cascade="all, delete-orphan"
    )
    need_tags: Mapped[list[FeatureNeedTagRow]] = relationship(
        "FeatureNeedTagRow", back_populates="feature_def", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "vehicle_type IS NULL OR vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_feature_definitions_vehicle_type",
        ),
        CheckConstraint(
            "value_type IN ('BOOLEAN', 'NUMBER', 'TEXT', 'ENUM')",
            name="ck_feature_definitions_value_type",
        ),
        CheckConstraint(
            "filter_behavior IN ('REQUIRED', 'PREFERENCE', 'INFORMATIONAL')",
            name="ck_feature_definitions_filter_behavior",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_feature_definitions_status"),
        CheckConstraint("display_order >= 0", name="ck_feature_definitions_display_order"),
        Index("ix_feature_definitions_type_status", "vehicle_type", "status"),
        Index("ix_feature_definitions_category_status", "category", "status"),
    )


class VehicleFeatureFlagRow(ProductBase):
    __tablename__ = "vehicle_feature_flags"

    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"),
        primary_key=True,
    )
    feature_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("feature_definitions.feature_code", ondelete="RESTRICT"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="feature_flags")
    feature_def: Mapped[FeatureDefinitionRow] = relationship("FeatureDefinitionRow", back_populates="flags")

    __table_args__ = (
        CheckConstraint("status IN ('YES', 'NO', 'UNKNOWN')", name="ck_vehicle_features_status"),
        CheckConstraint(
            "verification_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_vehicle_features_verification",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_vehicle_features_confidence",
        ),
        Index(
            "ix_vehicle_feature_flags_lookup",
            "feature_code",
            "status",
            "vehicle_id",
        ),
    )


# ---------------------------------------------------------------------------
# 8. tco_assumptions & feature_need_tags
# ---------------------------------------------------------------------------


class TcoAssumptionRow(ProductBase):
    __tablename__ = "tco_assumptions"

    assumption_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    region_code: Mapped[str] = mapped_column(String(16), nullable=False, server_default="VN")
    assumption_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    electricity_vnd_per_kwh: Mapped[int] = mapped_column(BigInteger, nullable=False)
    registration_fee_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    registration_fee_flat_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    plate_fee_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inspection_fee_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inspection_first_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    inspection_interval_months: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    inspection_interval_months_after_7y: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    mandatory_insurance_vnd_per_year: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    road_fee_vnd_per_year: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    maintenance_vnd_per_service: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    maintenance_interval_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_tco_assumptions_vehicle_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="ck_tco_assumptions_status",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_tco_assumptions_period"),
        CheckConstraint("horizon_months > 0", name="ck_tco_assumptions_horizon"),
        CheckConstraint(
            "electricity_vnd_per_kwh >= 0 "
            "AND (registration_fee_flat_vnd IS NULL OR registration_fee_flat_vnd >= 0) "
            "AND (plate_fee_vnd IS NULL OR plate_fee_vnd >= 0) "
            "AND (inspection_fee_vnd IS NULL OR inspection_fee_vnd >= 0) "
            "AND (mandatory_insurance_vnd_per_year IS NULL OR mandatory_insurance_vnd_per_year >= 0) "
            "AND (road_fee_vnd_per_year IS NULL OR road_fee_vnd_per_year >= 0) "
            "AND (maintenance_vnd_per_service IS NULL OR maintenance_vnd_per_service >= 0) "
            "AND (maintenance_interval_km IS NULL OR maintenance_interval_km > 0)",
            name="ck_tco_assumptions_amounts",
        ),
        UniqueConstraint("vehicle_type", "region_code", "assumption_version", name="uq_tco_assumptions_version"),
        Index(
            "ix_tco_assumptions_lookup",
            "vehicle_type",
            "region_code",
            "status",
            "valid_from",
            "valid_to",
        ),
    )


class FeatureNeedTagRow(ProductBase):
    __tablename__ = "feature_need_tags"

    feature_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("feature_definitions.feature_code", ondelete="CASCADE"),
        nullable=False,
    )
    need_tag: Mapped[str] = mapped_column(String(40), nullable=False)
    relevance: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, server_default="1.00")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    feature_def: Mapped[FeatureDefinitionRow] = relationship("FeatureDefinitionRow", back_populates="need_tags")

    __table_args__ = (
        PrimaryKeyConstraint("feature_code", "need_tag"),
        CheckConstraint(
            "need_tag = upper(need_tag) AND need_tag ~ '^[A-Z][A-Z0-9_]*$'",
            name="ck_feature_need_tags_tag_format",
        ),
        CheckConstraint("relevance > 0 AND relevance <= 1", name="ck_feature_need_tags_relevance"),
        Index("ix_feature_need_tags_need_tag", "need_tag", text("relevance DESC")),
    )


class VehicleShowcaseItemRow(ProductBase):
    """Source-attributed content used by the public vehicle showcase page."""

    __tablename__ = "vehicle_showcase_items"

    showcase_item_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"),
        nullable=False,
    )
    section_key: Mapped[str] = mapped_column(String(40), nullable=False)
    item_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    vehicle: Mapped[VehicleRow] = relationship("VehicleRow", back_populates="showcase_items")

    __table_args__ = (
        UniqueConstraint("vehicle_id", "item_key", name="uq_vehicle_showcase_item_key"),
        CheckConstraint("display_order >= 0", name="ck_vehicle_showcase_display_order"),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_vehicle_showcase_status"),
        Index(
            "ix_vehicle_showcase_section",
            "vehicle_id",
            "section_key",
            "status",
            "display_order",
        ),
    )


__all__ = [
    "BatteryPolicyRow",
    "CarSpecRow",
    "FeatureDefinitionRow",
    "FeatureNeedTagRow",
    "MotorbikeSpecRow",
    "OfferAdjustmentLogRow",
    "OfferAdjustmentPolicyRow",
    "ProductBase",
    "PromotionRow",
    "PromotionVehicleRow",
    "TcoAssumptionRow",
    "VehicleFeatureFlagRow",
    "VehiclePriceRow",
    "VehicleRow",
    "VehicleShowcaseItemRow",
]
