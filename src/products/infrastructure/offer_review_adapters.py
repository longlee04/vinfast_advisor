"""Adapters cho OfferPolicyPort + OfferAdjustmentLogPort (agents ports).

Products implement bằng structural typing — không import agents; agents chỉ
nhìn qua Protocol trong `src/agents/ports.py`. Trả ``None`` khi hợp lệ / chuỗi
lý do khi vi phạm để không cần chia sẻ exception class giữa hai module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert

from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentSourceKind,
)
from src.products.domain.offer_policy import (
    AdjustmentValue,
    validate_adjustment,
    validate_promotion_active,
)
from src.products.infrastructure.models import OfferAdjustmentLogRow
from src.products.infrastructure.promotion_repository import SqlAlchemyPromotionRepository
from src.products.infrastructure.repositories import SqlAlchemyOfferPolicyRepository


class ProductOfferPolicyAdapter:
    """Validate biên độ điều chỉnh qua domain offer_policy."""

    def __init__(self, session_factory) -> None:
        self._repo = SqlAlchemyOfferPolicyRepository(session_factory)
        self._promotions = SqlAlchemyPromotionRepository(session_factory)

    async def validate_adjustment(self, *, adjustment: OfferAdjustment) -> str | None:
        promotion_type = adjustment.promotion_type
        if not promotion_type:
            return "missing promotion_type"
        policy = await self._repo.get(promotion_type)
        if policy is None:
            return f"no offer policy configured for {promotion_type}"
        value = AdjustmentValue(
            amount_vnd=adjustment.amount_vnd,
            percent=adjustment.percent,
            months=adjustment.months,
            gift_code=adjustment.gift_code,
        )
        try:
            validate_adjustment(policy, value)
        except Exception as error:  # noqa: BLE001
            return str(error)
        return None

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None:
        promotions = await self._promotions.list_active(at)
        promotion = next((p for p in promotions if p.promotion_code == promotion_code), None)
        if promotion is None:
            return f"promotion {promotion_code!r} is not ACTIVE in the current window"
        try:
            validate_promotion_active(promotion.status.value, promotion.valid_to, at)
        except Exception as error:  # noqa: BLE001
            return str(error)
        return None


class ProductOfferAdjustmentLogAdapter:
    """Ghi offer_adjustment_log vào bảng products."""

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def record(
        self,
        *,
        source_kind: OfferAdjustmentSourceKind,
        source_id: UUID,
        review_id: UUID | None,
        advisor_id: str,
        promotion_code: str,
        adjustment_type: str,
        old_value: str | None,
        new_value: str | None,
        reason: str | None,
    ) -> None:
        async with self._factory() as session, session.begin():
            statement = insert(OfferAdjustmentLogRow).values(
                id=str(uuid4()),
                review_id=str(review_id) if review_id is not None else None,
                source_kind=source_kind.value,
                source_id=str(source_id),
                advisor_id=advisor_id,
                promotion_code=promotion_code,
                adjustment_type=adjustment_type,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
                created_at=datetime.now(UTC),
            )
            if source_kind is OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL:
                statement = statement.on_conflict_do_nothing(index_elements=["source_kind", "source_id"])
            await session.execute(statement)
