"""Deterministic customer profile projection from slots and confirmed signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.agents.domain.bottleneck_signal import ConfirmedBottleneckEvidence
from src.agents.domain.customer_profile import (
    BottleneckEvidence,
    OfferState,
    ProfileSnapshot,
    classify_offer_state,
)

_SLOT_NEEDS: dict[str, str] = {
    "budget_max_vnd": "budget",
    "passenger_count": "passenger",
    "home_charging": "home_charging",
    "monthly_distance": "monthly_distance",
    "vehicle_type": "vehicle_type",
}


class ProfileSnapshotService:
    """Build immutable customer profiles from typed confirmed state."""

    def build(
        self,
        *,
        slots: Mapping[str, object],
        confirmed_evidence: Sequence[ConfirmedBottleneckEvidence],
    ) -> ProfileSnapshot:
        """Project slots and ordered CORRECT evidence without transcript inference."""
        needs = [name for key, name in _SLOT_NEEDS.items() if slots.get(key) is not None]
        color_preference = slots.get("color_preference")
        return self.overlay(
            ProfileSnapshot(
                needs=needs,
                considered_vehicles=[],
                offer_state=OfferState.NONE_BOTTLENECK,
                color_preference=(str(color_preference) if color_preference is not None else None),
            ),
            confirmed_evidence,
        )

    def overlay(
        self,
        snapshot: ProfileSnapshot,
        confirmed_evidence: Sequence[ConfirmedBottleneckEvidence],
    ) -> ProfileSnapshot:
        """Copy snapshot with current confirmed evidence and reset offer projection."""
        bottlenecks = [
            BottleneckEvidence(
                bottleneck=evidence.label,
                verbatim_quote=evidence.evidence_quote,
            )
            for evidence in confirmed_evidence
        ]
        offer_state = classify_offer_state(bottlenecks, ())
        unmet_demand_flag = offer_state is OfferState.BOTTLENECK_NO_OFFER
        return snapshot.model_copy(
            update={
                "bottlenecks": bottlenecks,
                "matched_promotions": [],
                "offer_state": offer_state,
                "unmet_demand_flag": unmet_demand_flag,
                "unmet_bottleneck": (bottlenecks[0].bottleneck.value if unmet_demand_flag else None),
            }
        )
