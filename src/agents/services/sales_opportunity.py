"""Set-based sales opportunity projection from advisor-confirmed signals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.agents.domain.bottleneck_signal import OpportunitySignal
from src.agents.domain.customer_profile import (
    BottleneckEvidence,
    OfferState,
    ProfileSnapshot,
)
from src.agents.domain.pii import redact_pii


class SalesOpportunityRepository(Protocol):
    """Set-based opportunity and slot projection operations."""

    async def list_opportunities(self, since: datetime, limit: int) -> tuple[OpportunitySignal, ...]: ...

    async def load_opportunity_slots(self, session_ids: tuple[UUID, ...]) -> dict[UUID, dict[str, str | Decimal]]: ...


@dataclass(frozen=True, slots=True)
class SalesOpportunity:
    """One active session containing at least two confirmed concerns."""

    session_id: str
    customer_id: str
    bottlenecks: list[str]
    snapshot: ProfileSnapshot
    last_active_at: datetime


class SalesOpportunityService:
    """List recent opportunities using at most query plus slots batch."""

    def __init__(
        self,
        repository: SalesOpportunityRepository,
        *,
        window_hours: int = 24,
    ) -> None:
        self._repository = repository
        self._window_hours = window_hours

    async def list_opportunities(self, at: datetime, limit: int = 50) -> list[SalesOpportunity]:
        signals = await self._repository.list_opportunities(
            since=at - timedelta(hours=self._window_hours),
            limit=limit,
        )
        slots = await self._repository.load_opportunity_slots(tuple(signal.session_id for signal in signals))
        return [
            SalesOpportunity(
                session_id=str(signal.session_id),
                customer_id=signal.customer_id,
                bottlenecks=[label.value for label in signal.labels],
                snapshot=_snapshot(
                    signal,
                    slots.get(signal.session_id, {}),
                ),
                last_active_at=signal.last_active_at,
            )
            for signal in signals
        ]


def _snapshot(
    signal: OpportunitySignal,
    slots: Mapping[str, str | Decimal],
) -> ProfileSnapshot:
    evidence = [
        BottleneckEvidence(
            bottleneck=item.label,
            verbatim_quote=redact_pii(item.evidence_quote),
        )
        for item in signal.evidence
    ]
    color = slots.get("color_preference")
    return ProfileSnapshot(
        needs=[
            name
            for slot_name, name in (
                ("budget_max_vnd", "budget"),
                ("passenger_count", "passenger"),
                ("home_charging", "home_charging"),
                ("monthly_distance", "monthly_distance"),
                ("vehicle_type", "vehicle_type"),
            )
            if slot_name in slots
        ],
        considered_vehicles=[],
        bottlenecks=evidence,
        offer_state=OfferState.BOTTLENECK_NO_OFFER,
        unmet_demand_flag=True,
        unmet_bottleneck=evidence[0].bottleneck.value,
        color_preference=str(color) if color is not None else None,
    )
