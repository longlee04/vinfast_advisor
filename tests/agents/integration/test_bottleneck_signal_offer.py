"""Confirmed bottleneck signal offer picker and submission contracts."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.agents.domain.bottleneck_signal import BottleneckSignal, BottleneckSignalStatus
from src.agents.domain.customer_profile import Bottleneck, OfferState
from src.agents.services.operations.bottleneck_signal import (
    BottleneckSignalOperations,
    SignalOfferConflictError,
)
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentOutOfBoundsError,
    OfferAdjustmentSourceKind,
    PromotionExpiredError,
)

NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
SIGNAL_ID = UUID("60000000-0000-0000-0000-000000000001")
SESSION_ID = UUID("60000000-0000-0000-0000-000000000002")


def _signal(status: BottleneckSignalStatus) -> BottleneckSignal:
    return BottleneckSignal(
        signal_id=SIGNAL_ID,
        session_id=SESSION_ID,
        client_turn_id=uuid4(),
        anchor_client_turn_id=uuid4(),
        label=Bottleneck.PRICE,
        evidence_quote="Giá vượt ngân sách",
        model_name="internal",
        prompt_version="internal",
        status=status,
        claimed_by=None,
        claimed_at=None,
        lease_expires_at=None,
        advisor_id="advisor-1" if status is BottleneckSignalStatus.CORRECT else None,
        decided_at=NOW if status is BottleneckSignalStatus.CORRECT else None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def __init__(self, status: BottleneckSignalStatus) -> None:
        self.signal = _signal(status)

    async def get(self, signal_id: UUID) -> BottleneckSignal:
        assert signal_id == SIGNAL_ID
        return self.signal


class FakeTransaction:
    def __init__(self, repository: FakeRepository) -> None:
        self.bottleneck_signals = repository
        self.session_offers = _FakeOfferRepository()


class _FakeOfferRepository:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def insert(self, **kwargs) -> None:
        self.inserted.append(kwargs)


class FakeContextManager:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.transaction_value = transaction

    async def __aenter__(self) -> FakeTransaction:
        return self.transaction_value

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeUnitOfWork:
    def __init__(self, status: BottleneckSignalStatus) -> None:
        self.repository = FakeRepository(status)

    def transaction(self) -> FakeContextManager:
        return FakeContextManager(FakeTransaction(self.repository))


class FakeSuggestion:
    offer_state = OfferState.BOTTLENECK_OFFER_AVAILABLE
    matched = ()
    unmet_demand_flag = False
    unmet_bottleneck = None


class FakeDetailSource:
    def __init__(self) -> None:
        self.suggested_labels: list[tuple[Bottleneck, ...]] = []

    async def suggest_for_signal(self, signal: BottleneckSignal, at: datetime) -> FakeSuggestion:
        self.suggested_labels.append((signal.label,))
        return FakeSuggestion()

    async def adjustment_policies(self) -> tuple[dict[str, str], ...]:
        return ({"promotion_type": "FIXED_DISCOUNT"},)


class FakeSessionContext:
    def __init__(self, active: bool = True) -> None:
        self.active = active

    async def active_customer_id(self, session_id: UUID) -> str | None:
        assert session_id == SESSION_ID
        return "customer-1" if self.active else None


class FakeAdjustmentService:
    def __init__(self) -> None:
        self.calls: list[tuple[OfferAdjustmentSourceKind, UUID, str]] = []
        self.error: Exception | None = None

    async def apply(self, *, source, advisor_id: str, adjustment: OfferAdjustment, at: datetime) -> None:
        if self.error is not None:
            raise self.error
        call = (source.kind, source.source_id, adjustment.promotion_code)
        if call not in self.calls:
            self.calls.append(call)


@pytest.mark.asyncio
async def test_detail_suggests_only_for_correct_signal() -> None:
    # Given
    source = FakeDetailSource()
    correct = BottleneckSignalOperations(
        FakeUnitOfWork(BottleneckSignalStatus.CORRECT), detail_source=source, now=lambda: NOW
    )
    pending = BottleneckSignalOperations(
        FakeUnitOfWork(BottleneckSignalStatus.PENDING), detail_source=source, now=lambda: NOW
    )

    # When
    correct_detail = await correct.detail(SIGNAL_ID)
    pending_detail = await pending.detail(SIGNAL_ID)

    # Then
    assert correct_detail.offer_state is OfferState.BOTTLENECK_OFFER_AVAILABLE
    assert correct_detail.adjustment_policies == ({"promotion_type": "FIXED_DISCOUNT"},)
    assert pending_detail.matched_promotions == ()
    assert pending_detail.adjustment_policies == ()
    assert source.suggested_labels == [(Bottleneck.PRICE,)]


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_status", [BottleneckSignalStatus.PENDING, BottleneckSignalStatus.INCORRECT])
async def test_offer_rejects_unconfirmed_signal(signal_status: BottleneckSignalStatus) -> None:
    # Given
    adjustment_service = FakeAdjustmentService()
    operations = BottleneckSignalOperations(
        FakeUnitOfWork(signal_status),
        adjustment_service=adjustment_service,
        session_context=FakeSessionContext(),
        now=lambda: NOW,
    )

    # When / Then
    with pytest.raises(SignalOfferConflictError):
        await operations.submit_offer(SIGNAL_ID, "advisor-1", _adjustment())
    assert adjustment_service.calls == []


@pytest.mark.asyncio
async def test_offer_requires_active_customer_session() -> None:
    # Given
    service = FakeAdjustmentService()
    operations = BottleneckSignalOperations(
        FakeUnitOfWork(BottleneckSignalStatus.CORRECT),
        adjustment_service=service,
        session_context=FakeSessionContext(active=False),
        now=lambda: NOW,
    )

    # When / Then
    with pytest.raises(SignalOfferConflictError):
        await operations.submit_offer(SIGNAL_ID, "advisor-1", _adjustment())
    assert service.calls == []


@pytest.mark.asyncio
async def test_offer_uses_typed_signal_source_and_repeat_is_idempotent() -> None:
    # Given
    service = FakeAdjustmentService()
    operations = BottleneckSignalOperations(
        FakeUnitOfWork(BottleneckSignalStatus.CORRECT),
        adjustment_service=service,
        session_context=FakeSessionContext(),
        now=lambda: NOW,
    )

    # When
    await operations.submit_offer(SIGNAL_ID, "advisor-1", _adjustment())
    await operations.submit_offer(SIGNAL_ID, "advisor-1", _adjustment())

    # Then
    assert service.calls == [(OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL, SIGNAL_ID, "PRICE-10")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [OfferAdjustmentOutOfBoundsError("too high"), PromotionExpiredError("expired")],
)
async def test_offer_preserves_shared_service_validation_errors(error: Exception) -> None:
    # Given
    service = FakeAdjustmentService()
    service.error = error
    operations = BottleneckSignalOperations(
        FakeUnitOfWork(BottleneckSignalStatus.CORRECT),
        adjustment_service=service,
        session_context=FakeSessionContext(),
        now=lambda: NOW,
    )

    # When / Then
    with pytest.raises(type(error)):
        await operations.submit_offer(SIGNAL_ID, "advisor-1", _adjustment())


def _adjustment() -> OfferAdjustment:
    return OfferAdjustment(
        promotion_code="PRICE-10",
        promotion_type="FIXED_DISCOUNT",
        adjustment_type="VND",
        amount_vnd=10_000_000,
    )
