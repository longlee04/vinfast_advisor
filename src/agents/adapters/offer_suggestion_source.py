"""A5/T8: adapter đề xuất ưu đãi — uỷ quyền cho OfferSuggestionService của products.

Không tính match ở đây: `src/products/domain/offer_matching.py` là rule-map chuẩn
duy nhất. Adapter chỉ bọc service products và ánh xạ `OfferSuggestion` sang dạng
agents dùng được.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from src.agents.domain.bottleneck_signal import BottleneckSignal
from src.agents.domain.customer_profile import (
    BottleneckEvidence,
    OfferState,
    ProfileSnapshot,
)
from src.agents.models import ConversationSessionRow
from src.products.application.offer_suggestion_service import OfferSuggestionService
from src.products.infrastructure.promotion_repository import SqlAlchemyPromotionRepository
from src.products.infrastructure.repositories import SqlAlchemyOfferPolicyRepository


class OfferSuggestionDataSource:
    """Adapter từ OfferSuggestionService (products) qua OfferSuggestionPort."""

    def __init__(self, session_factory) -> None:
        self._factory = session_factory
        self._service = OfferSuggestionService(SqlAlchemyPromotionRepository(session_factory))
        self._policies = SqlAlchemyOfferPolicyRepository(session_factory)

    async def suggest(self, snapshot: ProfileSnapshot, at: datetime):
        return await self._service.suggest(snapshot, at)

    async def suggest_for_signal(self, signal: BottleneckSignal, at: datetime):
        snapshot = ProfileSnapshot(
            offer_state=OfferState.BOTTLENECK_NO_OFFER,
            bottlenecks=[
                BottleneckEvidence(
                    bottleneck=signal.label,
                    verbatim_quote=signal.evidence_quote,
                )
            ],
        )
        return await self._service.suggest(snapshot, at)

    async def adjustment_policies(self) -> tuple[dict, ...]:
        policies = await self._policies.list()
        return tuple(policy.model_dump(mode="json") for policy in policies)

    async def active_customer_id(self, session_id: UUID) -> str | None:
        async with self._factory() as session:
            return await session.scalar(
                select(ConversationSessionRow.customer_id).where(
                    ConversationSessionRow.session_id == session_id,
                    ConversationSessionRow.status == "ACTIVE",
                )
            )
