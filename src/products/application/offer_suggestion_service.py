"""Use case đề xuất ưu đãi cho một hồ sơ khách (không LLM).

Đọc promotions ACTIVE + match nút thắt → promotion qua rule-map (T5), rồi phân
loại offer_state (T2). Kết quả là EVIDENCE cho advisor — không bắt buộc cấp (D12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.agents.domain.customer_profile import (
    OfferState,
    ProfileSnapshot,
    classify_offer_state,
)
from src.products.domain.entities import Promotion
from src.products.domain.offer_matching import MatchedPromotion, match_bottlenecks_to_promotions


class PromotionRepository(Protocol):
    """Port đọc promotions cho offer suggestion."""

    async def list_active(self, at: datetime) -> list[Promotion]: ...


@dataclass(frozen=True, slots=True)
class OfferSuggestion:
    """Đề xuất ưu đãi cho một hồ sơ: trạng thái + các match."""

    offer_state: OfferState
    matched: list[MatchedPromotion]
    unmet_demand_flag: bool
    unmet_bottleneck: str | None


class OfferSuggestionService:
    """Dựng OfferSuggestion từ hồ sơ + promotions ACTIVE."""

    def __init__(self, repo: PromotionRepository) -> None:
        self._repo = repo

    async def suggest(self, snapshot: ProfileSnapshot, at: datetime) -> OfferSuggestion:
        promotions = await self._repo.list_active(at)
        matched = match_bottlenecks_to_promotions(
            [b.bottleneck for b in snapshot.bottlenecks],
            promotions,
            at,
            customer_context={},
        )
        offer_state = classify_offer_state(snapshot.bottlenecks, matched)
        unmet_demand_flag = offer_state is OfferState.BOTTLENECK_NO_OFFER
        unmet_bottleneck = (
            snapshot.bottlenecks[0].bottleneck.value if unmet_demand_flag and snapshot.bottlenecks else None
        )
        return OfferSuggestion(
            offer_state=offer_state,
            matched=matched,
            unmet_demand_flag=unmet_demand_flag,
            unmet_bottleneck=unmet_bottleneck,
        )
