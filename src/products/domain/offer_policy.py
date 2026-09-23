"""Offer adjustment policy domain: per-type boundaries and validation.

Pure Python — no SQLAlchemy/FastAPI imports. The concrete policy rows live in
the products module; agents only depends on the validation contract through a
port implemented here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.products.domain.errors import ProductDomainError
from src.products.domain.values import PromotionType


class AdjustmentOutOfBoundsError(ProductDomainError):
    """Raised when an adjustment exceeds the configured policy boundary."""


class PromotionExpiredError(ProductDomainError):
    """Raised when a promotion is not ACTIVE or is past its validity window."""


class AdjustmentValue(BaseModel):
    """One advisor adjustment attempt, loosely typed by promotion type.

    Exactly the fields relevant to the target promotion type should be set;
    unrelated fields stay ``None``.
    """

    amount_vnd: int | None = None
    percent: Decimal | None = None
    months: int | None = None
    gift_code: str | None = None


class OfferAdjustmentPolicy(BaseModel):
    """ADMIN-configured boundaries for one promotion type."""

    promotion_type: PromotionType
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


def validate_adjustment(policy: OfferAdjustmentPolicy, value: AdjustmentValue) -> None:
    """Raise ``AdjustmentOutOfBoundsError`` when the adjustment exceeds the policy."""

    _validate_money(policy, value)
    _validate_percent(policy, value)
    _validate_months(policy, value)
    _validate_gift_code(policy, value)


def validate_promotion_active(status: str, valid_to: datetime | None, at: datetime) -> None:
    """Raise ``PromotionExpiredError`` when the promotion cannot be granted now."""

    if status != "ACTIVE":
        raise PromotionExpiredError(f"promotion status is {status!r}, not ACTIVE")
    if valid_to is not None and valid_to < at:
        raise PromotionExpiredError("promotion valid_to is before the current time")


def validate_policy_bounds(policy: OfferAdjustmentPolicy) -> None:
    """Raise when a policy's own boundaries are invalid (min >= max, negative).

    Runs at ADMIN create/update time so a misconfigured policy cannot lock an
    advisor out or allow an absurd value.
    """

    pairs: tuple[tuple[int | None, int | None, str], ...] = (
        (policy.adjust_min_vnd, policy.adjust_max_vnd, "VND"),
        (policy.financing_months_min, policy.financing_months_max, "months"),
    )
    for lower, upper, dimension in pairs:
        if lower is not None and lower < 0:
            raise AdjustmentOutOfBoundsError(f"{dimension} lower bound cannot be negative")
        if upper is not None and upper < 0:
            raise AdjustmentOutOfBoundsError(f"{dimension} upper bound cannot be negative")
        if lower is not None and upper is not None and lower > upper:
            raise AdjustmentOutOfBoundsError(f"{dimension} min {lower} cannot exceed max {upper}")

    if (
        policy.adjust_min_percent is not None
        and policy.adjust_max_percent is not None
        and policy.adjust_min_percent > policy.adjust_max_percent
    ):
        raise AdjustmentOutOfBoundsError(
            f"percent min {policy.adjust_min_percent} cannot exceed max {policy.adjust_max_percent}"
        )
    if policy.adjust_min_percent is not None and policy.adjust_min_percent < 0:
        raise AdjustmentOutOfBoundsError("percent lower bound cannot be negative")


def _validate_money(policy: OfferAdjustmentPolicy, value: AdjustmentValue) -> None:
    if value.amount_vnd is None:
        return
    lower = {
        PromotionType.FIXED_DISCOUNT: policy.adjust_min_vnd,
        PromotionType.PERCENT_DISCOUNT: None,
        PromotionType.GIFT: None,
        PromotionType.FINANCING: None,
        PromotionType.REGISTRATION_SUPPORT: 0,
        PromotionType.OTHER: 0,
    }[policy.promotion_type]
    upper = {
        PromotionType.FIXED_DISCOUNT: policy.adjust_max_vnd,
        PromotionType.PERCENT_DISCOUNT: None,
        PromotionType.GIFT: policy.gift_value_max_vnd,
        PromotionType.FINANCING: policy.financing_support_max_vnd,
        PromotionType.REGISTRATION_SUPPORT: policy.registration_support_max_vnd,
        PromotionType.OTHER: policy.other_max_vnd,
    }[policy.promotion_type]
    if lower is not None and value.amount_vnd < lower:
        raise AdjustmentOutOfBoundsError(f"amount {value.amount_vnd} below minimum {lower} for {policy.promotion_type}")
    if upper is not None and value.amount_vnd > upper:
        raise AdjustmentOutOfBoundsError(f"amount {value.amount_vnd} above maximum {upper} for {policy.promotion_type}")


def _validate_percent(policy: OfferAdjustmentPolicy, value: AdjustmentValue) -> None:
    if value.percent is None:
        return
    if policy.promotion_type != PromotionType.PERCENT_DISCOUNT:
        raise AdjustmentOutOfBoundsError(f"percent adjustment not allowed for {policy.promotion_type}")
    if policy.adjust_min_percent is not None and value.percent < policy.adjust_min_percent:
        raise AdjustmentOutOfBoundsError(f"percent {value.percent} below minimum {policy.adjust_min_percent}")
    if policy.adjust_max_percent is not None and value.percent > policy.adjust_max_percent:
        raise AdjustmentOutOfBoundsError(f"percent {value.percent} above maximum {policy.adjust_max_percent}")


def _validate_months(policy: OfferAdjustmentPolicy, value: AdjustmentValue) -> None:
    if value.months is None:
        return
    if policy.promotion_type != PromotionType.FINANCING:
        raise AdjustmentOutOfBoundsError(f"months adjustment not allowed for {policy.promotion_type}")
    if policy.financing_months_min is not None and value.months < policy.financing_months_min:
        raise AdjustmentOutOfBoundsError(f"months {value.months} below minimum {policy.financing_months_min}")
    if policy.financing_months_max is not None and value.months > policy.financing_months_max:
        raise AdjustmentOutOfBoundsError(f"months {value.months} above maximum {policy.financing_months_max}")


def _validate_gift_code(policy: OfferAdjustmentPolicy, value: AdjustmentValue) -> None:
    if value.gift_code is None or policy.allowed_gift_codes is None:
        return
    if value.gift_code not in policy.allowed_gift_codes:
        raise AdjustmentOutOfBoundsError(
            f"gift code {value.gift_code!r} not in allowed list {policy.allowed_gift_codes}"
        )
