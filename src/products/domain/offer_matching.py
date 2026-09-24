"""Rule-based match từ customer bottleneck → promotion (không LLM).

Pure Python — chỉ đọc `Promotion` entity và `Bottleneck` (agents domain). Map theo
gift_group cho GIFT (fold #5): khách lo chỗ sạc nhận GIFT nhóm CHARGING, khách lo
pin nhận GIFT nhóm WARRANTY — không lẫn hai loại.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from src.agents.domain.customer_profile import Bottleneck
from src.products.domain.eligibility_rules import Eligibility, evaluate
from src.products.domain.entities import Promotion
from src.products.domain.values import PromotionType

_GIFT_GROUP_BY_BOTTLENECK: dict[Bottleneck, str] = {
    Bottleneck.CHARGING: "CHARGING",
    Bottleneck.BATTERY: "WARRANTY",
    Bottleneck.RANGE: "CHARGING",
}

_PROMOTION_TYPES_BY_BOTTLENECK: dict[Bottleneck, frozenset[PromotionType]] = {
    Bottleneck.PRICE: frozenset(
        {
            PromotionType.FIXED_DISCOUNT,
            PromotionType.PERCENT_DISCOUNT,
            PromotionType.REGISTRATION_SUPPORT,
            PromotionType.FINANCING,
        }
    ),
    Bottleneck.CHARGING: frozenset({PromotionType.GIFT}),
    Bottleneck.BATTERY: frozenset({PromotionType.GIFT}),
    Bottleneck.RANGE: frozenset({PromotionType.GIFT, PromotionType.OTHER}),
}


@dataclass(frozen=True, slots=True)
class MatchedPromotion:
    """Một promotion khớp một bottleneck, kèm cờ phân loại quà."""

    promotion: Promotion
    bottleneck: Bottleneck
    gift_group_unclassified: bool = False


def _is_active(promotion: Promotion, at: datetime) -> bool:
    if promotion.status.value != "ACTIVE":
        return False
    if promotion.valid_from > at:
        return False
    if promotion.valid_to is not None and promotion.valid_to < at:
        return False
    return True


def _eligibility_matches(promotion: Promotion, customer_context: Mapping[str, object]) -> bool:
    rules = promotion.eligibility_rules
    if not rules:
        return True
    expected_province = rules.get("province")
    if expected_province is None:
        return True
    return customer_context.get("province") == expected_province


def _rules_engine_matches(promotion: Promotion, customer_context: Mapping[str, object]) -> bool:
    """Bộ đánh giá DSL (plan Customer 360 §5.5): luật sai cú pháp/metadata crawler → LOẠI.

    Thiếu thông tin (NEED_INFO) vẫn giữ: TVV thấy ưu đãi và biết phải hỏi thêm.
    """

    return evaluate(promotion.eligibility_rules, customer_context).status not in {
        Eligibility.INELIGIBLE,
        Eligibility.INVALID_RULE,
    }


def match_bottlenecks_to_promotions(
    bottlenecks: Sequence[Bottleneck],
    promotions: Sequence[Promotion],
    at: datetime,
    customer_context: Mapping[str, object] | None = None,
    *,
    rules_engine: bool = False,
) -> list[MatchedPromotion]:
    """Trả promotions khớp từng bottleneck theo rule-map.

    Lọc promotion ACTIVE + trong khung thời gian + eligibility_rules (province)
    khớp context khách. GIFT phải khớp gift_group theo bottleneck; GIFT chưa gắn
    nhóm (``gift_group is None``) vẫn match với cờ ``gift_group_unclassified=True``
    để advisor biết chưa phân loại.
    """

    context = customer_context or {}
    matched: list[MatchedPromotion] = []
    # Cờ `offer_rules_engine` TẮT → đúng hành vi cũ (chỉ đọc khoá `province`).
    matches = _rules_engine_matches if rules_engine else _eligibility_matches
    active = [p for p in promotions if _is_active(p, at) and matches(p, context)]
    for bottleneck in bottlenecks:
        allowed_types = _PROMOTION_TYPES_BY_BOTTLENECK[bottleneck]
        for promotion in active:
            if promotion.promotion_type not in allowed_types:
                continue
            if promotion.promotion_type is PromotionType.GIFT:
                wanted_group = _GIFT_GROUP_BY_BOTTLENECK.get(bottleneck)
                if promotion.gift_group is None:
                    matched.append(
                        MatchedPromotion(
                            promotion=promotion,
                            bottleneck=bottleneck,
                            gift_group_unclassified=True,
                        )
                    )
                elif wanted_group is not None and promotion.gift_group == wanted_group:
                    matched.append(MatchedPromotion(promotion=promotion, bottleneck=bottleneck))
                continue
            matched.append(MatchedPromotion(promotion=promotion, bottleneck=bottleneck))
    return matched
