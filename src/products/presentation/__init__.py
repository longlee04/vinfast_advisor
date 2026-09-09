"""Pydantic schemas cho Vehicle Catalog API (Standard Envelope Format)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Standard Envelopes
# ---------------------------------------------------------------------------


class MetaOut(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class PaginationOut(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class StandardSuccessResponse(BaseModel):
    data: Any
    meta: MetaOut = Field(default_factory=MetaOut)


class StandardListResponse(BaseModel):
    data: list[Any]
    pagination: PaginationOut
    meta: MetaOut = Field(default_factory=MetaOut)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StandardErrorResponse(BaseModel):
    error: ErrorDetail
    meta: MetaOut = Field(default_factory=MetaOut)


# ---------------------------------------------------------------------------
# Vehicle Detail Data DTOs (schema mới)
# ---------------------------------------------------------------------------


class VehiclePriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price_id: str
    price_type: str
    amount_vnd: int
    currency: str
    region_code: str
    status: str
    valid_from: Any
    valid_to: Any | None = None


class BatteryPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    battery_policy_id: str
    ownership_model: str
    status: str
    version: int
    monthly_fee_vnd: int | None = None
    purchase_price_vnd: int | None = None
    valid_from: Any
    valid_to: Any | None = None


class VehicleFeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature_code: str
    name: str
    status: str
    verification_status: str
    value_text: str | None = None
    value_number: float | None = None
    value_boolean: bool | None = None


class PromotionLinkOut(BaseModel):
    promotion_id: str
    vehicle_id: str


class VehicleShowcaseItemOut(BaseModel):
    showcase_item_id: str
    section_key: str
    item_key: str
    title: str
    description: str | None = None
    media_url: str | None = None
    media_alt: str | None = None
    display_order: int
    source_url: str
    source_retrieved_at: Any


class VehicleSummaryOut(BaseModel):
    """Subset dùng cho listing — chỉ thông tin core."""

    vehicle_id: str
    vehicle_type: str
    brand: str
    model_name: str
    variant_name: str | None = None
    model_year: int | None = None
    status: str
    slug: str
    image_url: str | None = None
    detail_url: str | None = None


class VehicleDetailOut(BaseModel):
    """Aggregate detail trả về cho Customer/Admin."""

    vehicle: VehicleSummaryOut
    specs: dict[str, Any] = Field(default_factory=dict)
    prices: list[VehiclePriceOut] = Field(default_factory=list)
    battery_policies: list[BatteryPolicyOut] = Field(default_factory=list)
    feature_flags: list[VehicleFeatureFlagOut] = Field(default_factory=list)
    promotions: list[PromotionLinkOut] = Field(default_factory=list)
    showcase_items: list[VehicleShowcaseItemOut] = Field(default_factory=list)


class VehiclePriceIn(BaseModel):
    price_type: str = Field(..., min_length=1, max_length=32)
    amount_vnd: int = Field(..., ge=0)
    # DB co CHECK (currency = 'VND') va cot CHAR(3) — chan gia tri khac ngay o
    # tang validation thay vi de loi CHECK constraint roi xuong thanh 500.
    currency: Literal["VND"] = "VND"


class VehicleCreate(BaseModel):
    brand: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1, max_length=150)
    variant_name: str | None = Field(default=None, max_length=150)
    model_year: int | None = None
    slug: str | None = Field(default=None, max_length=220)
    vehicle_type: str = Field(default="CAR", max_length=32)
    status: str = Field(default="ACTIVE", max_length=32)
    image_url: str | None = None
    detail_url: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    prices: list[dict[str, Any]] = Field(default_factory=list)


class VehicleUpdate(BaseModel):
    """Partial update — moi field optional, field khong gui thi giu nguyen."""

    brand: str | None = Field(default=None, min_length=1, max_length=100)
    model_name: str | None = Field(default=None, min_length=1, max_length=150)
    variant_name: str | None = Field(default=None, max_length=150)
    model_year: int | None = None
    slug: str | None = Field(default=None, max_length=220)
    vehicle_type: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    image_url: str | None = None
    detail_url: str | None = None


class VehiclePriceUpdate(BaseModel):
    price_type: str | None = None
    amount_vnd: int | None = Field(default=None, ge=0)
    currency: str | None = None
    region_code: str | None = None
    status: str | None = None
    valid_from: Any | None = None
    valid_to: Any | None = None


class VehicleSpecsUpdate(BaseModel):
    specs: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdate(BaseModel):
    status: str | None = None
    verification_status: str | None = None
    value_text: str | None = None
    value_number: float | None = None
    value_boolean: bool | None = None
    confidence: float | None = None


class FeatureFlagOut(BaseModel):
    vehicle_id: str
    feature_code: str
    status: str
    verification_status: str
    vehicle_name: str
    feature_name: str
    confidence: float | None = None
    updated_by: str | None = None


class FeatureFlagReview(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")


# ---------------------------------------------------------------------------
# TCO (Total Cost of Ownership) Out DTOs
# ---------------------------------------------------------------------------


class TcoBreakdownOut(BaseModel):
    vehicle_price_vnd: int
    price_type: str
    registration_fee_vnd: int
    plate_fee_vnd: int
    inspection_fee_vnd: int
    inspection_count: int
    insurance_vnd: int
    road_fee_vnd: int
    electricity_vnd: int
    maintenance_vnd: int
    maintenance_count: int
    total_km: int
    total_upfront_vnd: int
    total_ownership_vnd: int


class TcoAssumptionsOut(BaseModel):
    #: Khu vực lệ phí biển số đã dùng để tính. Trả về cho khách đối chiếu: hai
    #: khu vực chênh nhau 100 lần nên phải nói rõ con số này thuộc vùng nào.
    region_code: str
    assumption_version: int
    electricity_vnd_per_kwh: int
    registration_fee_percent: str
    horizon_months: int
    source_note: str


class TcoConsumptionOut(BaseModel):
    kwh_per_100km: str
    source: str


class TcoOut(BaseModel):
    breakdown: TcoBreakdownOut
    assumptions: TcoAssumptionsOut
    consumption: TcoConsumptionOut


class OfferAdjustmentPolicyIn(BaseModel):
    """Payload create/update một offer_adjustment_policy (ADMIN)."""

    promotion_type: str | None = None
    adjust_min_vnd: int | None = None
    adjust_max_vnd: int | None = None
    adjust_min_percent: Decimal | None = None
    adjust_max_percent: Decimal | None = None
    financing_months_min: int | None = None
    financing_months_max: int | None = None
    financing_support_max_vnd: int | None = None
    gift_value_max_vnd: int | None = None
    allowed_gift_codes: list[str] | None = None
    registration_support_max_vnd: int | None = None
    other_max_vnd: int | None = None


class OfferAdjustmentPolicyOut(BaseModel):
    promotion_type: str
    adjust_min_vnd: int | None = None
    adjust_max_vnd: int | None = None
    adjust_min_percent: Decimal | None = None
    adjust_max_percent: Decimal | None = None
    financing_months_min: int | None = None
    financing_months_max: int | None = None
    financing_support_max_vnd: int | None = None
    gift_value_max_vnd: int | None = None
    allowed_gift_codes: list[str] | None = None
    registration_support_max_vnd: int | None = None
    other_max_vnd: int | None = None


__all__ = [
    "BatteryPolicyOut",
    "ErrorDetail",
    "FeatureFlagOut",
    "FeatureFlagReview",
    "FeatureFlagUpdate",
    "MetaOut",
    "OfferAdjustmentPolicyIn",
    "OfferAdjustmentPolicyOut",
    "PaginatedResponse",
    "PaginationOut",
    "PromotionLinkOut",
    "StandardErrorResponse",
    "StandardListResponse",
    "StandardSuccessResponse",
    "TcoAssumptionsOut",
    "TcoBreakdownOut",
    "TcoConsumptionOut",
    "TcoOut",
    "VehicleCreate",
    "VehicleDetailOut",
    "VehicleFeatureFlagOut",
    "VehiclePriceIn",
    "VehiclePriceOut",
    "VehiclePriceUpdate",
    "VehicleSpecsUpdate",
    "VehicleSummaryOut",
    "VehicleShowcaseItemOut",
    "VehicleUpdate",
]
