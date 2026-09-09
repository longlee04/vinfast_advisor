"""Applicability and versioning rules for reviewed policy scopes."""

from datetime import date

import pytest

from src.document.domain.policy_notifications import PolicyTopic, PolicyType
from src.document.domain.policy_scopes import (
    BatteryChemistry,
    EligibilityBasis,
    InvalidPolicyScopeError,
    PolicyComponent,
    PolicyScope,
    PolicyScopeId,
    PolicyScopeStatus,
    PolicyUsageType,
    PolicyVehicleType,
)


def _scope(**overrides: object) -> PolicyScope:
    values: dict[str, object] = {
        "id": PolicyScopeId("00000000-0000-0000-0000-000000000501"),
        "notification_id": "00000000-0000-0000-0000-000000000401",
        "source_document_id": "00000000-0000-0000-0000-000000000301",
        "policy_type": PolicyType.WARRANTY_POLICY,
        "topic": PolicyTopic.BATTERY_WARRANTY,
        "vehicle_type": PolicyVehicleType.MOTORBIKE,
        "component": PolicyComponent.LFP_BATTERY,
        "battery_chemistry": BatteryChemistry.LFP,
        "usage_type": PolicyUsageType.ANY,
        "eligibility_basis": EligibilityBasis.INVOICE_DATE,
        "eligibility_from": date(2025, 8, 16),
        "affected_models": ("Feliz S",),
        "resolved_vehicle_ids": ("00000000-0000-0000-0000-000000000701",),
        "evidence_quotes": ("Pin LFP duoc bao hanh 8 nam.",),
        "status": PolicyScopeStatus.DRAFT,
    }
    values.update(overrides)
    return PolicyScope(**values)  # type: ignore[arg-type]


def test_scope_rejects_an_inverted_eligibility_range() -> None:
    with pytest.raises(InvalidPolicyScopeError, match="eligibility range"):
        _scope(
            eligibility_from=date(2025, 8, 16),
            eligibility_to=date(2025, 8, 14),
        )


def test_scope_rejects_dates_without_an_eligibility_basis() -> None:
    with pytest.raises(InvalidPolicyScopeError, match="eligibility basis"):
        _scope(eligibility_basis=EligibilityBasis.NONE)


def test_old_and_new_revisions_can_coexist_for_disjoint_cohorts() -> None:
    old = _scope(
        id=PolicyScopeId("00000000-0000-0000-0000-000000000502"),
        eligibility_from=None,
        eligibility_to=date(2025, 8, 14),
        is_current_default=False,
    )
    new = _scope(is_current_default=True)

    assert old.overlaps_cohort(new) is False
    assert old.applies_to(date(2025, 8, 14)) is True
    assert new.applies_to(date(2025, 8, 16)) is True


def test_unreviewed_boundary_date_fails_closed() -> None:
    old = _scope(
        eligibility_from=None,
        eligibility_to=date(2025, 8, 14),
        is_current_default=False,
    )
    new = _scope(eligibility_from=date(2025, 8, 16))

    assert old.applies_to(date(2025, 8, 15)) is False
    assert new.applies_to(date(2025, 8, 15)) is False


def test_active_scope_requires_source_evidence_and_resolved_vehicle() -> None:
    with pytest.raises(InvalidPolicyScopeError, match="resolved vehicle"):
        _scope(status=PolicyScopeStatus.ACTIVE, resolved_vehicle_ids=())
    with pytest.raises(InvalidPolicyScopeError, match="literal evidence"):
        _scope(status=PolicyScopeStatus.ACTIVE, evidence_quotes=())
