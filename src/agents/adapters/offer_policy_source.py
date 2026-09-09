"""Adapters cho OfferPolicyPort + OfferAdjustmentLogPort (uỷ quyền products)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentSourceKind,
)
from src.products.infrastructure.offer_review_adapters import (
    ProductOfferAdjustmentLogAdapter,
    ProductOfferPolicyAdapter,
)
from src.products.infrastructure.repositories import SqlAlchemyOfferPolicyRepository


class OfferPolicyDataSource:
    """Adapter từ products qua OfferPolicyPort."""

    def __init__(self, session_factory) -> None:
        self._adapter = ProductOfferPolicyAdapter(session_factory)
        self._policies = SqlAlchemyOfferPolicyRepository(session_factory)

    async def validate_adjustment(self, *, adjustment: OfferAdjustment) -> str | None:
        return await self._adapter.validate_adjustment(adjustment=adjustment)

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None:
        return await self._adapter.validate_promotion_active(promotion_code=promotion_code, at=at)

    async def list_policies(self) -> list[dict]:
        """Biên độ ADMIN cấu hình, phẳng thành dict để gửi thẳng qua HTTP."""
        policies = await self._policies.list()
        return [_policy_payload(policy) for policy in policies]


def _policy_payload(policy: object) -> dict:
    dumper = getattr(policy, "model_dump", None)
    payload = dumper(mode="json") if callable(dumper) else dict(policy)  # type: ignore[arg-type]
    return payload


class OfferAdjustmentLogDataSource:
    """Adapter từ products qua OfferAdjustmentLogPort."""

    def __init__(self, session_factory) -> None:
        self._adapter = ProductOfferAdjustmentLogAdapter(session_factory)

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
        await self._adapter.record(
            source_kind=source_kind,
            source_id=source_id,
            review_id=review_id,
            advisor_id=advisor_id,
            promotion_code=promotion_code,
            adjustment_type=adjustment_type,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
