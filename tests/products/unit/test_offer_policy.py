"""Unit tests for the offer adjustment policy domain."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.products.domain.errors import ProductDomainError
from src.products.domain.offer_policy import (
    AdjustmentOutOfBoundsError,
    AdjustmentValue,
    OfferAdjustmentPolicy,
    PromotionExpiredError,
    validate_adjustment,
    validate_policy_bounds,
    validate_promotion_active,
)
from src.products.domain.values import PromotionType


def _policy(promotion_type: PromotionType, **overrides: object) -> OfferAdjustmentPolicy:
    defaults: dict[str, object] = {"promotion_type": promotion_type}
    defaults.update(overrides)
    return OfferAdjustmentPolicy(**defaults)


class TestValidateAdjustment:
    """Adjustment must stay inside the per-type boundaries."""

    def test_fixed_discount_within_boundary_passes(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        validate_adjustment(policy, AdjustmentValue(amount_vnd=5_000_000))

    def test_fixed_discount_above_maximum_raises(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=10_000_001))

    def test_fixed_discount_below_minimum_raises(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=-1))

    def test_percent_discount_within_boundary_passes(self) -> None:
        policy = _policy(
            PromotionType.PERCENT_DISCOUNT, adjust_min_percent=Decimal("0"), adjust_max_percent=Decimal("5")
        )
        validate_adjustment(policy, AdjustmentValue(percent=Decimal("3.5")))

    def test_percent_discount_above_maximum_raises(self) -> None:
        policy = _policy(
            PromotionType.PERCENT_DISCOUNT, adjust_min_percent=Decimal("0"), adjust_max_percent=Decimal("5")
        )
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(percent=Decimal("5.1")))

    def test_financing_months_within_boundary_passes(self) -> None:
        policy = _policy(
            PromotionType.FINANCING,
            financing_months_min=6,
            financing_months_max=36,
            financing_support_max_vnd=20_000_000,
        )
        validate_adjustment(policy, AdjustmentValue(months=24, amount_vnd=10_000_000))

    def test_financing_months_above_maximum_raises(self) -> None:
        policy = _policy(
            PromotionType.FINANCING,
            financing_months_min=6,
            financing_months_max=36,
            financing_support_max_vnd=20_000_000,
        )
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(months=37))

    def test_financing_support_above_maximum_raises(self) -> None:
        policy = _policy(
            PromotionType.FINANCING,
            financing_months_min=6,
            financing_months_max=36,
            financing_support_max_vnd=20_000_000,
        )
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(months=12, amount_vnd=20_000_001))

    def test_gift_value_within_boundary_passes(self) -> None:
        policy = _policy(PromotionType.GIFT, gift_value_max_vnd=3_000_000, allowed_gift_codes=None)
        validate_adjustment(policy, AdjustmentValue(amount_vnd=3_000_000))

    def test_gift_value_above_maximum_raises(self) -> None:
        policy = _policy(PromotionType.GIFT, gift_value_max_vnd=3_000_000, allowed_gift_codes=None)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=3_000_001))

    def test_gift_code_not_allowed_raises(self) -> None:
        policy = _policy(PromotionType.GIFT, gift_value_max_vnd=3_000_000, allowed_gift_codes=["G1"])
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(gift_code="G2"))

    def test_gift_code_allowed_passes(self) -> None:
        policy = _policy(PromotionType.GIFT, gift_value_max_vnd=3_000_000, allowed_gift_codes=["G1"])
        validate_adjustment(policy, AdjustmentValue(gift_code="G1"))

    def test_registration_support_within_boundary_passes(self) -> None:
        policy = _policy(PromotionType.REGISTRATION_SUPPORT, registration_support_max_vnd=5_000_000)
        validate_adjustment(policy, AdjustmentValue(amount_vnd=5_000_000))

    def test_registration_support_above_maximum_raises(self) -> None:
        policy = _policy(PromotionType.REGISTRATION_SUPPORT, registration_support_max_vnd=5_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=5_000_001))

    def test_other_within_boundary_passes(self) -> None:
        policy = _policy(PromotionType.OTHER, other_max_vnd=5_000_000)
        validate_adjustment(policy, AdjustmentValue(amount_vnd=5_000_000))

    def test_other_above_maximum_raises(self) -> None:
        policy = _policy(PromotionType.OTHER, other_max_vnd=5_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=5_000_001))

    def test_percent_adjustment_rejected_for_non_percent_type(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_adjustment(policy, AdjustmentValue(percent=Decimal("2")))

    def test_error_is_domain_error(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        with pytest.raises(ProductDomainError):
            validate_adjustment(policy, AdjustmentValue(amount_vnd=99_000_000))


class TestValidatePromotionActive:
    """Re-validation before granting an offer."""

    def test_active_promotion_within_window_passes(self) -> None:
        now = datetime.now(UTC)
        validate_promotion_active("ACTIVE", valid_to=None, at=now)

    def test_inactive_promotion_raises(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(PromotionExpiredError):
            validate_promotion_active("EXPIRED", valid_to=None, at=now)

    def test_past_valid_to_raises(self) -> None:
        now = datetime.now(UTC)
        past = datetime(2020, 1, 1, tzinfo=UTC)
        with pytest.raises(PromotionExpiredError):
            validate_promotion_active("ACTIVE", valid_to=past, at=now)


class TestValidatePolicyBounds:
    """Admin-configured policy boundaries must be sane on create/update."""

    def test_sane_boundaries_pass(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=0, adjust_max_vnd=10_000_000)
        validate_policy_bounds(policy)

    def test_min_above_max_raises(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=10_000_000, adjust_max_vnd=0)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_policy_bounds(policy)

    def test_negative_bound_raises(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=-1, adjust_max_vnd=10_000_000)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_policy_bounds(policy)

    def test_financing_min_above_max_raises(self) -> None:
        policy = _policy(PromotionType.FINANCING, financing_months_min=36, financing_months_max=6)
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_policy_bounds(policy)

    def test_percent_min_above_max_raises(self) -> None:
        policy = _policy(
            PromotionType.PERCENT_DISCOUNT,
            adjust_min_percent=Decimal("5"),
            adjust_max_percent=Decimal("0"),
        )
        with pytest.raises(AdjustmentOutOfBoundsError):
            validate_policy_bounds(policy)

    def test_error_is_domain_error(self) -> None:
        policy = _policy(PromotionType.FIXED_DISCOUNT, adjust_min_vnd=5, adjust_max_vnd=0)
        with pytest.raises(ProductDomainError):
            validate_policy_bounds(policy)
