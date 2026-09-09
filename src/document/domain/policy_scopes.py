"""Reviewed applicability scopes for versioned customer policies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from src.document.domain.policy_notifications import PolicyTopic, PolicyType


class PolicyVehicleType(StrEnum):
    """Catalog family to which a policy applies."""

    CAR = "CAR"
    MOTORBIKE = "MOTORBIKE"
    OTHER = "OTHER"


class PolicyComponent(StrEnum):
    """Physical or commercial component governed by a scope."""

    VEHICLE = "VEHICLE"
    HIGH_VOLTAGE_BATTERY = "HIGH_VOLTAGE_BATTERY"
    LFP_BATTERY = "LFP_BATTERY"
    NON_LFP_BATTERY = "NON_LFP_BATTERY"
    BATTERY_12V = "BATTERY_12V"
    SPARE_PART = "SPARE_PART"
    ACCESSORY = "ACCESSORY"
    BATTERY_SERVICE = "BATTERY_SERVICE"


class BatteryChemistry(StrEnum):
    """Reviewed battery chemistry; unknown data must not match these values."""

    LFP = "LFP"
    LITHIUM_ION = "LITHIUM_ION"
    LEAD_ACID = "LEAD_ACID"
    OTHER_REVIEWED = "OTHER_REVIEWED"


class BatteryOwnershipModel(StrEnum):
    """Customer relationship to a policy-covered battery."""

    INCLUDED = "INCLUDED"
    PURCHASE = "PURCHASE"
    SUBSCRIPTION = "SUBSCRIPTION"
    SWAP = "SWAP"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PolicyUsageType(StrEnum):
    """Permitted vehicle usage cohort."""

    STANDARD = "STANDARD"
    COMMERCIAL = "COMMERCIAL"
    ANY = "ANY"


class EligibilityBasis(StrEnum):
    """Customer date that decides which historical revision applies."""

    INVOICE_DATE = "INVOICE_DATE"
    WARRANTY_ACTIVATION_DATE = "WARRANTY_ACTIVATION_DATE"
    CONTRACT_ACTIVATION_DATE = "CONTRACT_ACTIVATION_DATE"
    PURCHASE_DATE = "PURCHASE_DATE"
    NONE = "NONE"


class PolicyScopeStatus(StrEnum):
    """Human-controlled evidence lifecycle."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class PolicyConflictResolution(StrEnum):
    """Explicit Admin decision when a published scope overlaps another revision."""

    COEXIST_BY_COHORT = "COEXIST_BY_COHORT"
    SUPERSEDE_DEFAULT = "SUPERSEDE_DEFAULT"
    CANCEL = "CANCEL"


class InvalidPolicyScopeError(ValueError):
    """Raised when applicability metadata could cause an unsafe answer."""


@dataclass(frozen=True, slots=True)
class PolicyScopeId:
    """Validated policy scope identifier."""

    value: str

    def __post_init__(self) -> None:
        try:
            UUID(self.value)
        except ValueError as error:
            raise InvalidPolicyScopeError("invalid scope id") from error


@dataclass(frozen=True, slots=True)
class PolicyScope:
    """One reviewed applicability rule backed by literal source evidence."""

    id: PolicyScopeId
    notification_id: str
    source_document_id: str
    policy_type: PolicyType
    topic: PolicyTopic
    vehicle_type: PolicyVehicleType
    component: PolicyComponent
    usage_type: PolicyUsageType
    eligibility_basis: EligibilityBasis
    affected_models: tuple[str, ...]
    resolved_vehicle_ids: tuple[str, ...]
    evidence_quotes: tuple[str, ...]
    status: PolicyScopeStatus = PolicyScopeStatus.DRAFT
    battery_chemistry: BatteryChemistry | None = None
    ownership_model: BatteryOwnershipModel | None = None
    policy_active_from: date | None = None
    policy_active_to: date | None = None
    eligibility_from: date | None = None
    eligibility_to: date | None = None
    is_current_default: bool = False
    supersedes_scope_id: str | None = None
    created_by: str | None = None
    approved_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_range(self.policy_active_from, self.policy_active_to, "policy active range")
        _validate_range(self.eligibility_from, self.eligibility_to, "eligibility range")
        if self.eligibility_basis is EligibilityBasis.NONE and (
            self.eligibility_from is not None or self.eligibility_to is not None
        ):
            raise InvalidPolicyScopeError("eligibility basis is required when cohort dates exist")
        if self.status is PolicyScopeStatus.ACTIVE:
            if not self.resolved_vehicle_ids:
                raise InvalidPolicyScopeError("active scope requires a resolved vehicle")
            if not any(quote.strip() for quote in self.evidence_quotes):
                raise InvalidPolicyScopeError("active scope requires literal evidence")

    @classmethod
    def create_draft(
        cls,
        *,
        notification_id: str,
        source_document_id: str,
        policy_type: PolicyType,
        topic: PolicyTopic,
        vehicle_type: PolicyVehicleType,
        component: PolicyComponent,
        usage_type: PolicyUsageType,
        eligibility_basis: EligibilityBasis,
        affected_models: tuple[str, ...],
        evidence_quotes: tuple[str, ...],
        actor_id: str,
        battery_chemistry: BatteryChemistry | None = None,
        ownership_model: BatteryOwnershipModel | None = None,
        policy_active_from: date | None = None,
        policy_active_to: date | None = None,
        eligibility_from: date | None = None,
        eligibility_to: date | None = None,
        is_current_default: bool = False,
    ) -> PolicyScope:
        """Create a non-customer-visible scope proposed for Admin review."""
        now = datetime.now(UTC)
        return cls(
            id=PolicyScopeId(str(uuid4())),
            notification_id=notification_id,
            source_document_id=source_document_id,
            policy_type=policy_type,
            topic=topic,
            vehicle_type=vehicle_type,
            component=component,
            battery_chemistry=battery_chemistry,
            ownership_model=ownership_model,
            usage_type=usage_type,
            eligibility_basis=eligibility_basis,
            policy_active_from=policy_active_from,
            policy_active_to=policy_active_to,
            eligibility_from=eligibility_from,
            eligibility_to=eligibility_to,
            is_current_default=is_current_default,
            affected_models=affected_models,
            resolved_vehicle_ids=(),
            evidence_quotes=evidence_quotes,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )

    def with_resolved_vehicles(self, vehicle_ids: tuple[str, ...]) -> PolicyScope:
        """Attach exact catalog identities while retaining DRAFT status."""
        return replace(self, resolved_vehicle_ids=vehicle_ids, updated_at=datetime.now(UTC))

    def edit_applicability(
        self,
        *,
        ownership_model: BatteryOwnershipModel | None,
        usage_type: PolicyUsageType,
        policy_active_from: date | None,
        policy_active_to: date | None,
        eligibility_basis: EligibilityBasis,
        eligibility_from: date | None,
        eligibility_to: date | None,
        is_current_default: bool,
    ) -> PolicyScope:
        """Edit cohort fields while source evidence/model binding remains immutable."""
        if self.status is not PolicyScopeStatus.DRAFT:
            raise InvalidPolicyScopeError("active policy scope is immutable")
        return replace(
            self,
            ownership_model=ownership_model,
            usage_type=usage_type,
            policy_active_from=policy_active_from,
            policy_active_to=policy_active_to,
            eligibility_basis=eligibility_basis,
            eligibility_from=eligibility_from,
            eligibility_to=eligibility_to,
            is_current_default=is_current_default,
            updated_at=datetime.now(UTC),
        )

    def activate(self, actor_id: str, moment: datetime | None = None) -> PolicyScope:
        """Activate only a complete, reviewed scope."""
        if self.policy_type is PolicyType.UNKNOWN or self.topic is PolicyTopic.UNKNOWN:
            raise InvalidPolicyScopeError("unknown policy scope cannot be activated")
        approved_at = moment or datetime.now(UTC)
        return replace(
            self,
            status=PolicyScopeStatus.ACTIVE,
            approved_by=actor_id,
            approved_at=approved_at,
            updated_at=approved_at,
        )

    def applies_to(self, eligibility_date: date | None) -> bool:
        """Return whether a known customer date belongs to this scope's cohort."""
        if self.eligibility_basis is EligibilityBasis.NONE:
            return eligibility_date is None
        if eligibility_date is None:
            return self.is_current_default
        if self.eligibility_from is not None and eligibility_date < self.eligibility_from:
            return False
        return self.eligibility_to is None or eligibility_date <= self.eligibility_to

    def overlaps_cohort(self, other: PolicyScope) -> bool:
        """Detect overlap only when both scopes govern the same applicability key."""
        if self.applicability_key != other.applicability_key:
            return False
        return self.cohort_period_overlaps(other)

    def cohort_period_overlaps(self, other: PolicyScope) -> bool:
        """Compare only date ranges after the caller matched applicability fields."""
        return _ranges_overlap(
            self.eligibility_from,
            self.eligibility_to,
            other.eligibility_from,
            other.eligibility_to,
        )

    @property
    def applicability_key(self) -> tuple[object, ...]:
        """Fields that must match before two revisions can conflict."""
        return (
            self.policy_type,
            self.topic,
            self.vehicle_type,
            self.component,
            self.battery_chemistry,
            self.ownership_model,
            self.usage_type,
            tuple(sorted(self.resolved_vehicle_ids)),
        )


def _validate_range(start: date | None, end: date | None, label: str) -> None:
    if start is not None and end is not None and end < start:
        raise InvalidPolicyScopeError(f"{label} is invalid")


def _ranges_overlap(
    left_start: date | None,
    left_end: date | None,
    right_start: date | None,
    right_end: date | None,
) -> bool:
    earliest_end = min(value for value in (left_end, right_end) if value is not None) if (
        left_end is not None or right_end is not None
    ) else None
    latest_start = max(value for value in (left_start, right_start) if value is not None) if (
        left_start is not None or right_start is not None
    ) else None
    return earliest_end is None or latest_start is None or latest_start <= earliest_end
