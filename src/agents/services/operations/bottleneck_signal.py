"""Staff use cases for bottleneck signal queue and CAS decisions."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from src.agents.domain.bottleneck_signal import (
    BottleneckSignal,
    BottleneckSignalStatus,
    SignalClaimDeniedError,
    SignalVerdict,
)
from src.agents.domain.customer_profile import OfferState
from src.agents.ports import SessionOfferRepository
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentService,
    OfferAdjustmentSource,
    OfferAdjustmentSourceKind,
)
from src.products.application.offer_suggestion_service import OfferSuggestion

DEFAULT_LEASE_MINUTES = 15
OFFER_TTL_DAYS = 7


class BottleneckSignalRepository(Protocol):
    async def list_by_status(
        self, signal_status: BottleneckSignalStatus, *, limit: int, offset: int
    ) -> tuple[BottleneckSignal, ...]: ...

    async def get(self, signal_id: UUID) -> BottleneckSignal: ...

    async def claim(self, signal_id: UUID, advisor_id: str, lease_minutes: int) -> bool: ...

    async def decide(self, signal_id: UUID, advisor_id: str, verdict: SignalVerdict) -> BottleneckSignal: ...


class BottleneckSignalTransaction(Protocol):
    bottleneck_signals: BottleneckSignalRepository
    session_offers: SessionOfferRepository


class BottleneckSignalUnitOfWork(Protocol):
    def transaction(
        self,
    ) -> AbstractAsyncContextManager[BottleneckSignalTransaction]: ...


class SignalDetailSource(Protocol):
    async def suggest_for_signal(self, signal: BottleneckSignal, at: datetime) -> OfferSuggestion: ...

    async def adjustment_policies(self) -> tuple[dict, ...]: ...


class ActiveSessionContext(Protocol):
    async def active_customer_id(self, session_id: UUID) -> str | None: ...


@dataclass(slots=True)
class SignalOfferConflictError(Exception):
    """Signal cannot expose or receive an offer in current context."""

    signal_id: UUID


@dataclass(frozen=True, slots=True)
class BottleneckSignalDetail:
    signal: BottleneckSignal
    offer_state: OfferState = OfferState.NONE_BOTTLENECK
    matched_promotions: tuple[dict, ...] = ()
    adjustment_policies: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class BottleneckSignalOperations:
    """Coordinate staff queue reads and repository-enforced CAS writes."""

    unit_of_work: BottleneckSignalUnitOfWork
    detail_source: SignalDetailSource | None = None
    adjustment_service: OfferAdjustmentService | None = None
    session_context: ActiveSessionContext | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def list_signals(
        self, signal_status: BottleneckSignalStatus, limit: int, offset: int
    ) -> tuple[BottleneckSignal, ...]:
        async with self.unit_of_work.transaction() as transaction:
            return await transaction.bottleneck_signals.list_by_status(signal_status, limit=limit, offset=offset)

    async def detail(self, signal_id: UUID) -> BottleneckSignalDetail:
        async with self.unit_of_work.transaction() as transaction:
            signal = await transaction.bottleneck_signals.get(signal_id)
        if signal.status is not BottleneckSignalStatus.CORRECT or self.detail_source is None:
            return BottleneckSignalDetail(signal=signal)
        suggestion = await self.detail_source.suggest_for_signal(signal, self.now())
        return BottleneckSignalDetail(
            signal=signal,
            offer_state=suggestion.offer_state,
            matched_promotions=tuple(
                {
                    "promotion_code": match.promotion.promotion_code,
                    "promotion_type": match.promotion.promotion_type.value,
                    "gift_group_unclassified": match.gift_group_unclassified,
                }
                for match in suggestion.matched
            ),
            adjustment_policies=await self.detail_source.adjustment_policies(),
        )

    async def submit_offer(self, signal_id: UUID, advisor_id: str, adjustment: OfferAdjustment) -> None:
        async with self.unit_of_work.transaction() as transaction:
            signal = await transaction.bottleneck_signals.get(signal_id)
        if signal.status is not BottleneckSignalStatus.CORRECT:
            raise SignalOfferConflictError(signal_id)
        if self.session_context is None or await self.session_context.active_customer_id(signal.session_id) is None:
            raise SignalOfferConflictError(signal_id)
        if self.adjustment_service is None:
            raise SignalOfferConflictError(signal_id)
        await self.adjustment_service.apply(
            source=OfferAdjustmentSource(OfferAdjustmentSourceKind.BOTTLENECK_SIGNAL, signal_id),
            advisor_id=advisor_id,
            adjustment=adjustment,
            at=self.now(),
        )
        async with self.unit_of_work.transaction() as transaction:
            await transaction.session_offers.insert(
                session_id=signal.session_id,
                source_kind="BOTTLENECK_SIGNAL",
                source_signal_id=signal_id,
                promotion_code=adjustment.promotion_code,
                value_snapshot={
                    "display_name": adjustment.promotion_code,
                    "promotion_type": adjustment.promotion_type,
                    "adjustment_type": adjustment.adjustment_type,
                    "new_value": adjustment.new_value,
                    "amount_vnd": adjustment.amount_vnd,
                    "percent": adjustment.percent,
                    "months": adjustment.months,
                    "gift_code": adjustment.gift_code,
                },
                approved_by=advisor_id,
                expires_at=self.now() + timedelta(days=OFFER_TTL_DAYS),
            )

    async def claim(self, signal_id: UUID, advisor_id: str) -> BottleneckSignal:
        async with self.unit_of_work.transaction() as transaction:
            granted = await transaction.bottleneck_signals.claim(signal_id, advisor_id, DEFAULT_LEASE_MINUTES)
            if not granted:
                raise SignalClaimDeniedError(signal_id, advisor_id)
            return await transaction.bottleneck_signals.get(signal_id)

    async def verdict(self, signal_id: UUID, advisor_id: str, verdict: SignalVerdict) -> BottleneckSignal:
        async with self.unit_of_work.transaction() as transaction:
            return await transaction.bottleneck_signals.decide(signal_id, advisor_id, verdict)
