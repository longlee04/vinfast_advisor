"""Shared offer-adjustment validation and typed audit orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class OfferAdjustmentOutOfBoundsError(Exception):
    """Adjustment violates configured product policy."""


class PromotionExpiredError(Exception):
    """Promotion cannot be granted at submission time."""


class OfferAdjustmentSourceKind(StrEnum):
    """Supported audit owners without cross-module foreign keys."""

    CONTENT_REVIEW = "CONTENT_REVIEW"
    BOTTLENECK_SIGNAL = "BOTTLENECK_SIGNAL"


@dataclass(frozen=True, slots=True)
class OfferAdjustmentSource:
    kind: OfferAdjustmentSourceKind
    source_id: UUID

    @property
    def review_id(self) -> UUID | None:
        match self.kind:
            case OfferAdjustmentSourceKind.CONTENT_REVIEW:
                return self.source_id
            case OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL:
                return None


@dataclass(frozen=True, slots=True)
class OfferAdjustment:
    promotion_code: str
    promotion_type: str
    adjustment_type: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    amount_vnd: int | None = None
    percent: str | None = None
    months: int | None = None
    gift_code: str | None = None


class OfferAdjustmentPolicy(Protocol):
    async def validate_adjustment(self, *, adjustment: OfferAdjustment) -> str | None: ...

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None: ...


class OfferAdjustmentAuditLog(Protocol):
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
    ) -> None: ...


class OfferAdjustmentService:
    """Validate current policy and promotion before writing one typed audit."""

    def __init__(self, *, policy: OfferAdjustmentPolicy, audit_log: OfferAdjustmentAuditLog) -> None:
        self._policy = policy
        self._audit_log = audit_log

    async def apply(
        self,
        *,
        source: OfferAdjustmentSource,
        advisor_id: str,
        adjustment: OfferAdjustment,
        at: datetime,
    ) -> None:
        adjustment_error = await self._policy.validate_adjustment(adjustment=adjustment)
        if adjustment_error:
            raise OfferAdjustmentOutOfBoundsError(adjustment_error)
        promotion_error = await self._policy.validate_promotion_active(
            promotion_code=adjustment.promotion_code,
            at=at,
        )
        if promotion_error:
            raise PromotionExpiredError(promotion_error)
        await self._audit_log.record(
            source_kind=source.kind,
            source_id=source.source_id,
            review_id=source.review_id,
            advisor_id=advisor_id,
            promotion_code=adjustment.promotion_code,
            adjustment_type=adjustment.adjustment_type,
            old_value=adjustment.old_value,
            new_value=adjustment.new_value,
            reason=adjustment.reason,
        )
