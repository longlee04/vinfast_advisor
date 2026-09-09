"""create product (catalog) schema

`vehicle_documents` không nằm ở đây — bảng đó thuộc module document
(migrations/document/versions/d0cument0002_vehicle_documents.py).

Revision ID: d4e5f6a7b8c9
Revises:
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "vehicles",
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_type", sa.String(32), nullable=False),
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(150), nullable=False),
        sa.Column("variant_name", sa.String(150), nullable=True),
        sa.Column("model_year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("detail_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("vehicle_id"),
        sa.CheckConstraint("vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')", name="ck_vehicles_type"),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED')", name="ck_vehicles_status"),
        sa.UniqueConstraint("slug", name="uq_vehicles_slug"),
        sa.UniqueConstraint(
            "vehicle_type", "brand", "model_name", "variant_name", "model_year",
            name="uq_vehicles_identity",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_vehicles_type_status", "vehicles", ["vehicle_type", "status"])

    op.create_table(
        "cars",
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("body_type", sa.String(50), nullable=True),
        sa.Column("seat_count", sa.Integer(), nullable=True),
        sa.Column("range_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("range_cycle", sa.String(32), nullable=True),
        sa.Column("energy_consumption_kwh_per_100km", sa.Numeric(10, 3), nullable=True),
        sa.Column("battery_capacity_kwh", sa.Numeric(10, 3), nullable=True),
        sa.Column("motor_power_kw", sa.Numeric(10, 3), nullable=True),
        sa.Column("torque_nm", sa.Numeric(10, 3), nullable=True),
        sa.Column("max_speed_kmh", sa.Numeric(10, 2), nullable=True),
        sa.Column("acceleration_0_100_seconds", sa.Numeric(10, 2), nullable=True),
        sa.Column("curb_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("gross_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("fast_charge_power_kw", sa.Numeric(10, 3), nullable=True),
        sa.Column("fast_charge_time_minutes", sa.Integer(), nullable=True),
        sa.Column("fast_charge_from_percent", sa.SmallInteger(), nullable=True),
        sa.Column("fast_charge_to_percent", sa.SmallInteger(), nullable=True),
        sa.Column("home_charge_time_minutes", sa.Integer(), nullable=True),
        sa.Column("charging_port", sa.String(50), nullable=True),
        sa.Column("cargo_volume_standard_l", sa.Numeric(10, 2), nullable=True),
        sa.Column("cargo_volume_maximum_l", sa.Numeric(10, 2), nullable=True),
        sa.Column("towing_supported", sa.Boolean(), nullable=True),
        sa.Column("towing_capacity_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("specs_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("vehicle_id"),
        sa.CheckConstraint("seat_count IS NULL OR seat_count > 0", name="ck_cars_seats"),
        sa.CheckConstraint("range_km IS NULL OR range_km >= 0", name="ck_cars_range"),
        sa.CheckConstraint(
            "fast_charge_from_percent IS NULL OR fast_charge_to_percent IS NULL "
            "OR fast_charge_to_percent > fast_charge_from_percent",
            name="ck_cars_charge_window",
        ),
    )
    op.create_index("ix_cars_filter_range_seats", "cars", ["range_km", "seat_count"])

    op.create_table(
        "motorbikes",
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("motor_power_w", sa.Integer(), nullable=True),
        sa.Column("max_power_w", sa.Integer(), nullable=True),
        sa.Column("torque_nm", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_speed_kmh", sa.Numeric(10, 2), nullable=True),
        sa.Column("battery_type", sa.String(50), nullable=True),
        sa.Column("battery_capacity_kwh", sa.Numeric(10, 3), nullable=True),
        sa.Column("battery_quantity", sa.SmallInteger(), nullable=True),
        sa.Column("battery_removable", sa.Boolean(), nullable=True),
        sa.Column("battery_swappable", sa.Boolean(), nullable=True),
        sa.Column("energy_consumption_kwh_per_100km", sa.Numeric(10, 3), nullable=True),
        sa.Column("range_min_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("range_max_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("range_cycle", sa.String(32), nullable=True),
        sa.Column("charging_time_minutes", sa.Integer(), nullable=True),
        sa.Column("charging_method", sa.String(50), nullable=True),
        sa.Column("curb_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_load_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("seat_height_mm", sa.Numeric(10, 2), nullable=True),
        sa.Column("wheel_size_front_inch", sa.Numeric(5, 2), nullable=True),
        sa.Column("wheel_size_rear_inch", sa.Numeric(5, 2), nullable=True),
        sa.Column("license_requirement", sa.String(32), nullable=True),
        sa.Column("specs_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("vehicle_id"),
        sa.CheckConstraint(
            "range_min_km IS NULL OR range_max_km IS NULL OR range_max_km >= range_min_km",
            name="ck_motorbikes_range",
        ),
        sa.CheckConstraint(
            "license_requirement IS NULL OR license_requirement IN ('NONE', 'A1', 'A', 'UNKNOWN')",
            name="ck_motorbikes_license",
        ),
    )
    op.create_index("ix_motorbikes_filter_range_load", "motorbikes", ["range_max_km", "max_load_kg"])

    op.create_table(
        "vehicle_prices",
        sa.Column("price_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("price_type", sa.String(40), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="VND"),
        sa.Column("region_code", sa.String(16), nullable=False, server_default="VN"),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("price_id"),
        sa.CheckConstraint("amount_vnd >= 0", name="ck_vehicle_prices_amount"),
        sa.CheckConstraint("currency = 'VND'", name="ck_vehicle_prices_currency"),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')", name="ck_vehicle_prices_status"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_vehicle_prices_period"),
    )
    op.create_index(
        "ix_vehicle_prices_current_filter",
        "vehicle_prices",
        ["vehicle_id", "price_type", "status", "valid_from", "valid_to"],
    )
    op.create_index(
        "uq_vehicle_prices_one_active",
        "vehicle_prices",
        ["vehicle_id", "price_type", "region_code"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "promotions",
        sa.Column("promotion_id", UUID(as_uuid=False), nullable=False),
        sa.Column("promotion_code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("promotion_type", sa.String(40), nullable=False),
        sa.Column("discount_amount_vnd", sa.BigInteger(), nullable=True),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("region_code", sa.String(16), nullable=False, server_default="VN"),
        sa.Column("eligibility_rules", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("promotion_id"),
        sa.UniqueConstraint("promotion_code", name="uq_promotions_code"),
        sa.CheckConstraint(
            "promotion_type IN ('FIXED_DISCOUNT', 'PERCENT_DISCOUNT', 'GIFT', "
            "'FINANCING', 'REGISTRATION_SUPPORT', 'OTHER')",
            name="ck_promotions_type",
        ),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')", name="ck_promotions_status"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_promotions_period"),
        sa.CheckConstraint(
            "discount_amount_vnd IS NULL OR discount_amount_vnd >= 0", name="ck_promotions_discount"
        ),
    )
    op.create_index(
        "ix_promotions_active_period", "promotions", ["status", "region_code", "valid_from", "valid_to"]
    )

    op.create_table(
        "promotion_vehicles",
        sa.Column("promotion_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["promotion_id"], ["promotions.promotion_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("promotion_id", "vehicle_id"),
    )
    op.create_index("ix_promotion_vehicles_vehicle", "promotion_vehicles", ["vehicle_id", "promotion_id"])

    op.create_table(
        "battery_policies",
        sa.Column("battery_policy_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("ownership_model", sa.String(32), nullable=False),
        sa.Column("monthly_fee_vnd", sa.BigInteger(), nullable=True),
        sa.Column("purchase_price_vnd", sa.BigInteger(), nullable=True),
        sa.Column("included_distance_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("excess_fee_per_km_vnd", sa.BigInteger(), nullable=True),
        sa.Column("deposit_amount_vnd", sa.BigInteger(), nullable=True),
        sa.Column("warranty_months", sa.Integer(), nullable=True),
        sa.Column("warranty_distance_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("battery_policy_id"),
        sa.CheckConstraint(
            "ownership_model IN ('INCLUDED', 'PURCHASE', 'SUBSCRIPTION', 'SWAP', 'NOT_APPLICABLE')",
            name="ck_battery_policies_model",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')", name="ck_battery_policies_status"
        ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_battery_policies_period"),
        sa.CheckConstraint(
            "(monthly_fee_vnd IS NULL OR monthly_fee_vnd >= 0) "
            "AND (purchase_price_vnd IS NULL OR purchase_price_vnd >= 0) "
            "AND (deposit_amount_vnd IS NULL OR deposit_amount_vnd >= 0) "
            "AND (excess_fee_per_km_vnd IS NULL OR excess_fee_per_km_vnd >= 0)",
            name="ck_battery_policies_amounts",
        ),
    )
    op.create_index(
        "ix_battery_policies_vehicle_period",
        "battery_policies",
        ["vehicle_id", "status", "valid_from", "valid_to"],
    )

    op.create_table(
        "feature_definitions",
        sa.Column("feature_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vehicle_type", sa.String(32), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False, server_default="BOOLEAN"),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("allowed_values", JSONB, nullable=True),
        sa.Column("filter_behavior", sa.String(32), nullable=False, server_default="PREFERENCE"),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("feature_code"),
        sa.CheckConstraint(
            "vehicle_type IS NULL OR vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_feature_definitions_vehicle_type",
        ),
        sa.CheckConstraint(
            "value_type IN ('BOOLEAN', 'NUMBER', 'TEXT', 'ENUM')", name="ck_feature_definitions_value_type"
        ),
        sa.CheckConstraint(
            "filter_behavior IN ('REQUIRED', 'PREFERENCE', 'INFORMATIONAL')",
            name="ck_feature_definitions_filter_behavior",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_feature_definitions_status"),
        sa.CheckConstraint("display_order >= 0", name="ck_feature_definitions_display_order"),
    )
    op.create_index("ix_feature_definitions_type_status", "feature_definitions", ["vehicle_type", "status"])
    op.create_index("ix_feature_definitions_category_status", "feature_definitions", ["category", "status"])

    op.create_table(
        "vehicle_feature_flags",
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("feature_code", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(14, 3), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("verification_status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.vehicle_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_code"], ["feature_definitions.feature_code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("vehicle_id", "feature_code"),
        sa.CheckConstraint("status IN ('YES', 'NO', 'UNKNOWN')", name="ck_vehicle_features_status"),
        sa.CheckConstraint(
            "verification_status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_vehicle_features_verification"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_vehicle_features_confidence"
        ),
    )
    op.create_index(
        "ix_vehicle_feature_flags_lookup", "vehicle_feature_flags", ["feature_code", "status", "vehicle_id"]
    )

    op.create_table(
        "tco_assumptions",
        sa.Column("assumption_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_type", sa.String(32), nullable=False),
        sa.Column("region_code", sa.String(16), nullable=False, server_default="VN"),
        sa.Column("assumption_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("electricity_vnd_per_kwh", sa.BigInteger(), nullable=False),
        sa.Column("registration_fee_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("registration_fee_flat_vnd", sa.BigInteger(), nullable=True),
        sa.Column("plate_fee_vnd", sa.BigInteger(), nullable=True),
        sa.Column("inspection_fee_vnd", sa.BigInteger(), nullable=True),
        sa.Column("mandatory_insurance_vnd_per_year", sa.BigInteger(), nullable=True),
        sa.Column("road_fee_vnd_per_year", sa.BigInteger(), nullable=True),
        sa.Column("maintenance_vnd_per_service", sa.BigInteger(), nullable=True),
        sa.Column("maintenance_interval_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("assumption_id"),
        sa.CheckConstraint("vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')", name="ck_tco_assumptions_vehicle_type"),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')", name="ck_tco_assumptions_status"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_tco_assumptions_period"),
        sa.CheckConstraint("horizon_months > 0", name="ck_tco_assumptions_horizon"),
        sa.CheckConstraint(
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
        sa.UniqueConstraint(
            "vehicle_type", "region_code", "assumption_version", name="uq_tco_assumptions_version"
        ),
    )
    op.create_index(
        "ix_tco_assumptions_lookup",
        "tco_assumptions",
        ["vehicle_type", "region_code", "status", "valid_from", "valid_to"],
    )

    op.create_table(
        "feature_need_tags",
        sa.Column("feature_code", sa.String(100), nullable=False),
        sa.Column("need_tag", sa.String(40), nullable=False),
        sa.Column("relevance", sa.Numeric(3, 2), nullable=False, server_default="1.00"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_code"], ["feature_definitions.feature_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feature_code", "need_tag"),
        sa.CheckConstraint(
            "need_tag = upper(need_tag) AND need_tag ~ '^[A-Z][A-Z0-9_]*$'",
            name="ck_feature_need_tags_tag_format",
        ),
        sa.CheckConstraint("relevance > 0 AND relevance <= 1", name="ck_feature_need_tags_relevance"),
    )
    op.create_index(
        "ix_feature_need_tags_need_tag", "feature_need_tags", ["need_tag", sa.text("relevance DESC")]
    )


def downgrade() -> None:
    op.drop_table("feature_need_tags")
    op.drop_table("tco_assumptions")
    op.drop_table("vehicle_feature_flags")
    op.drop_table("feature_definitions")
    op.drop_table("battery_policies")
    op.drop_table("promotion_vehicles")
    op.drop_table("promotions")
    op.drop_table("vehicle_prices")
    op.drop_table("motorbikes")
    op.drop_table("cars")
    op.drop_table("vehicles")