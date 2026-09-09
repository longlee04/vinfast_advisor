"""Tests for shared offer-adjustment validation and typed audit sources."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentOutOfBoundsError,
    OfferAdjustmentService,
    OfferAdjustmentSource,
    OfferAdjustmentSourceKind,
    PromotionExpiredError,
)

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


class FakePolicy:
    def __init__(self) -> None:
        self.adjustment_error: str | None = None
        self.promotion_error: str | None = None
        self.calls: list[str] = []

    async def validate_adjustment(self, *, adjustment: OfferAdjustment) -> str | None:
        self.calls.append("adjustment")
        return self.adjustment_error

    async def validate_promotion_active(self, *, promotion_code: str, at: datetime) -> str | None:
        self.calls.append("promotion")
        return self.promotion_error


class FakeAuditLog:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **fields: object) -> None:
        self.records.append(fields)


def _adjustment() -> OfferAdjustment:
    return OfferAdjustment(
        promotion_code="FIN-1",
        promotion_type="FINANCING",
        adjustment_type="VND",
        new_value="10000000",
    )


@pytest.mark.asyncio
async def test_content_source_validates_then_records_typed_audit() -> None:
    # Given
    policy = FakePolicy()
    audit = FakeAuditLog()
    source_id = uuid4()
    service = OfferAdjustmentService(policy=policy, audit_log=audit)

    # When
    await service.apply(
        source=OfferAdjustmentSource(OfferAdjustmentSourceKind.CONTENT_REVIEW, source_id),
        advisor_id="advisor-a",
        adjustment=_adjustment(),
        at=NOW,
    )

    # Then
    assert policy.calls == ["adjustment", "promotion"]
    assert audit.records == [
        {
            "source_kind": OfferAdjustmentSourceKind.CONTENT_REVIEW,
            "source_id": source_id,
            "review_id": source_id,
            "advisor_id": "advisor-a",
            "promotion_code": "FIN-1",
            "adjustment_type": "VND",
            "old_value": None,
            "new_value": "10000000",
            "reason": None,
        }
    ]


@pytest.mark.asyncio
async def test_signal_source_records_without_fake_review_id() -> None:
    # Given
    audit = FakeAuditLog()
    source_id = uuid4()
    service = OfferAdjustmentService(policy=FakePolicy(), audit_log=audit)

    # When
    await service.apply(
        source=OfferAdjustmentSource(OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL, source_id),
        advisor_id="advisor-a",
        adjustment=_adjustment(),
        at=NOW,
    )

    # Then
    assert audit.records[0]["source_id"] == source_id
    assert audit.records[0]["review_id"] is None


@pytest.mark.asyncio
async def test_out_of_bounds_does_not_record() -> None:
    # Given
    policy = FakePolicy()
    policy.adjustment_error = "amount above maximum"
    audit = FakeAuditLog()
    service = OfferAdjustmentService(policy=policy, audit_log=audit)

    # When / Then
    with pytest.raises(OfferAdjustmentOutOfBoundsError):
        await service.apply(
            source=OfferAdjustmentSource(OfferAdjustmentSourceKind.CONTENT_REVIEW, uuid4()),
            advisor_id="advisor-a",
            adjustment=_adjustment(),
            at=NOW,
        )
    assert audit.records == []


@pytest.mark.asyncio
async def test_expired_promotion_does_not_record() -> None:
    # Given
    policy = FakePolicy()
    policy.promotion_error = "promotion expired"
    audit = FakeAuditLog()
    service = OfferAdjustmentService(policy=policy, audit_log=audit)

    # When / Then
    with pytest.raises(PromotionExpiredError):
        await service.apply(
            source=OfferAdjustmentSource(OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL, uuid4()),
            advisor_id="advisor-a",
            adjustment=_adjustment(),
            at=NOW,
        )
    assert audit.records == []
