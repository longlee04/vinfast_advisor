"""Unit tests for the bottleneck → promotion rule matcher."""

from dataclasses import replace
from datetime import UTC, datetime

from src.agents.domain.customer_profile import Bottleneck
from src.products.domain.entities import Promotion
from src.products.domain.offer_matching import match_bottlenecks_to_promotions
from src.products.domain.values import PromotionType, RecordLifecycleStatus

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _promotion(
    promotion_type: PromotionType,
    *,
    status: RecordLifecycleStatus = RecordLifecycleStatus.ACTIVE,
    gift_group: str | None = None,
    eligibility_rules: dict[str, object] | None = None,
) -> Promotion:
    return Promotion(
        promotion_id="p-1",
        promotion_code="PROMO-1",
        title="Promo",
        promotion_type=promotion_type,
        region_code="VN",
        eligibility_rules=eligibility_rules or {},
        status=status,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=None,
        created_at=NOW,
        updated_at=NOW,
        gift_group=gift_group,
    )


class TestMatchBottlenecksToPromotions:
    """Rule-map bottleneck → promotion theo type + gift_group."""

    def test_price_matches_financing(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING)]
        matches = match_bottlenecks_to_promotions([Bottleneck.PRICE], promotions, NOW)
        assert len(matches) == 1
        assert matches[0].promotion.promotion_type is PromotionType.FINANCING

    def test_charging_matches_gift_correct_group(self) -> None:
        promotions = [_promotion(PromotionType.GIFT, gift_group="CHARGING")]
        matches = match_bottlenecks_to_promotions([Bottleneck.CHARGING], promotions, NOW)
        assert len(matches) == 1
        assert matches[0].promotion.promotion_type is PromotionType.GIFT
        assert matches[0].gift_group_unclassified is False

    def test_charging_does_not_match_gift_wrong_group(self) -> None:
        promotions = [_promotion(PromotionType.GIFT, gift_group="WARRANTY")]
        matches = match_bottlenecks_to_promotions([Bottleneck.CHARGING], promotions, NOW)
        assert matches == []

    def test_charging_matches_unclassified_gift_with_flag(self) -> None:
        promotions = [_promotion(PromotionType.GIFT, gift_group=None)]
        matches = match_bottlenecks_to_promotions([Bottleneck.CHARGING], promotions, NOW)
        assert len(matches) == 1
        assert matches[0].gift_group_unclassified is True

    def test_charging_does_not_match_fixed_discount(self) -> None:
        promotions = [_promotion(PromotionType.FIXED_DISCOUNT)]
        matches = match_bottlenecks_to_promotions([Bottleneck.CHARGING], promotions, NOW)
        assert matches == []

    def test_expired_promotion_is_skipped(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING, status=RecordLifecycleStatus.EXPIRED)]
        matches = match_bottlenecks_to_promotions([Bottleneck.PRICE], promotions, NOW)
        assert matches == []

    def test_past_valid_to_is_skipped(self) -> None:
        promotion = replace(
            _promotion(PromotionType.FINANCING),
            valid_to=datetime(2026, 5, 1, tzinfo=UTC),
        )
        matches = match_bottlenecks_to_promotions([Bottleneck.PRICE], [promotion], NOW)
        assert matches == []

    def test_eligibility_province_mismatch_is_skipped(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING, eligibility_rules={"province": "HN"})]
        matches = match_bottlenecks_to_promotions(
            [Bottleneck.PRICE],
            promotions,
            NOW,
            customer_context={"province": "HCM"},
        )
        assert matches == []

    def test_eligibility_province_match_passes(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING, eligibility_rules={"province": "HN"})]
        matches = match_bottlenecks_to_promotions(
            [Bottleneck.PRICE],
            promotions,
            NOW,
            customer_context={"province": "HN"},
        )
        assert len(matches) == 1

    def test_no_eligibility_rules_matches_any_context(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING)]
        matches = match_bottlenecks_to_promotions(
            [Bottleneck.PRICE], promotions, NOW, customer_context={"province": "HCM"}
        )
        assert len(matches) == 1

    def test_empty_bottlenecks_returns_empty(self) -> None:
        promotions = [_promotion(PromotionType.FINANCING)]
        matches = match_bottlenecks_to_promotions([], promotions, NOW)
        assert matches == []

    def test_battery_matches_warranty_gift(self) -> None:
        promotions = [_promotion(PromotionType.GIFT, gift_group="WARRANTY")]
        matches = match_bottlenecks_to_promotions([Bottleneck.BATTERY], promotions, NOW)
        assert len(matches) == 1
        assert matches[0].promotion.promotion_type is PromotionType.GIFT

    def test_range_matches_other_type(self) -> None:
        promotions = [_promotion(PromotionType.OTHER)]
        matches = match_bottlenecks_to_promotions([Bottleneck.RANGE], promotions, NOW)
        assert len(matches) == 1
        assert matches[0].promotion.promotion_type is PromotionType.OTHER
