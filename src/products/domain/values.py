"""Enum value objects for the Product (Vehicle Catalog) module.

Giá trị enum khớp 1-1 với CHECK constraint trong
``migrations/products/versions/d4e5f6a7b8c9_product_schema.py``. Không thêm
giá trị mới nếu chưa được schema cho phép — đây là source of truth.

Việc validate nghiệp vụ (parse chuỗi, sinh id, ...) thuộc application service
ở boundary; module này chỉ khai báo tập hợp giá trị hợp lệ.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# vehicles
# ---------------------------------------------------------------------------


class VehicleType(StrEnum):
    """``ck_vehicles_type`` — vehicles.vehicle_type."""

    CAR = "CAR"
    ELECTRIC_MOTORBIKE = "ELECTRIC_MOTORBIKE"


class VehicleStatus(StrEnum):
    """``ck_vehicles_status`` — vehicles.status."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# vehicle_prices
# ---------------------------------------------------------------------------


class Currency(StrEnum):
    """``ck_vehicle_prices_currency`` — vehicle_prices.currency.

    Schema hiện chỉ cho phép VND. Enum được giữ rộng để không phá public API.
    """

    VND = "VND"


class RecordLifecycleStatus(StrEnum):
    """Trạng thái vòng đời dùng chung cho vehicle_prices, promotions,
    battery_policies, tco_assumptions (``ck_*_status``)."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# motorbikes
# ---------------------------------------------------------------------------


class LicenseRequirement(StrEnum):
    """``ck_motorbikes_license`` — motorbikes.license_requirement."""

    NONE = "NONE"
    A1 = "A1"
    A = "A"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# promotions
# ---------------------------------------------------------------------------


class PromotionType(StrEnum):
    """``ck_promotions_type`` — promotions.promotion_type."""

    FIXED_DISCOUNT = "FIXED_DISCOUNT"
    PERCENT_DISCOUNT = "PERCENT_DISCOUNT"
    GIFT = "GIFT"
    FINANCING = "FINANCING"
    REGISTRATION_SUPPORT = "REGISTRATION_SUPPORT"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# battery_policies
# ---------------------------------------------------------------------------


class BatteryOwnershipModel(StrEnum):
    """``ck_battery_policies_model`` — battery_policies.ownership_model."""

    INCLUDED = "INCLUDED"
    PURCHASE = "PURCHASE"
    SUBSCRIPTION = "SUBSCRIPTION"
    SWAP = "SWAP"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# feature_definitions / vehicle_feature_flags
# ---------------------------------------------------------------------------


class FeatureValueType(StrEnum):
    """``ck_feature_definitions_value_type`` — feature_definitions.value_type."""

    BOOLEAN = "BOOLEAN"
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    ENUM = "ENUM"


class FilterBehavior(StrEnum):
    """``ck_feature_definitions_filter_behavior`` — feature_definitions.filter_behavior."""

    REQUIRED = "REQUIRED"
    PREFERENCE = "PREFERENCE"
    INFORMATIONAL = "INFORMATIONAL"


class FeatureDefinitionStatus(StrEnum):
    """``ck_feature_definitions_status`` — feature_definitions.status."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class FeatureFlagStatus(StrEnum):
    """``ck_vehicle_features_status`` — vehicle_feature_flags.status."""

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(StrEnum):
    """``ck_vehicle_features_verification`` — vehicle_feature_flags.verification_status."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


__all__ = [
    "BatteryOwnershipModel",
    "Currency",
    "FeatureDefinitionStatus",
    "FeatureFlagStatus",
    "FeatureValueType",
    "FilterBehavior",
    "LicenseRequirement",
    "PromotionType",
    "RecordLifecycleStatus",
    "VehicleStatus",
    "VehicleType",
    "VerificationStatus",
]
