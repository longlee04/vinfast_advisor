"""Domain model and invariants for controlled policy notifications."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.document.domain.values import DocumentId

if TYPE_CHECKING:
    from src.document.domain.policy_scopes import PolicyScope


class PolicyType(StrEnum):
    """Closed policy classification taxonomy."""

    BATTERY_POLICY = "battery_policy"
    WARRANTY_POLICY = "warranty_policy"
    PRICE_POLICY = "price_policy"
    PROMOTION_POLICY = "promotion_policy"
    OTHER_POLICY = "other_policy"
    UNKNOWN = "unknown"


class PolicyTopic(StrEnum):
    """Closed primary and secondary topic taxonomy."""

    BATTERY_RENTAL = "battery_rental"
    BATTERY_PURCHASE = "battery_purchase"
    BATTERY_USAGE = "battery_usage"
    BATTERY_REPLACEMENT = "battery_replacement"
    BATTERY_SWAP = "battery_swap"
    BATTERY_CHARGING = "battery_charging"
    BATTERY_COMPENSATION = "battery_compensation"
    BATTERY_CONTRACT = "battery_contract"
    VEHICLE_WARRANTY = "vehicle_warranty"
    BATTERY_WARRANTY = "battery_warranty"
    SPARE_PART_WARRANTY = "spare_part_warranty"
    VEHICLE_PRICE = "vehicle_price"
    PROMOTION = "promotion"
    OTHER = "other"
    UNKNOWN = "unknown"


class PolicyNotificationStatus(StrEnum):
    """Human review states supported by the MVP."""

    DRAFT = "draft"
    PUBLISHED = "published"


class PolicyNotificationError(Exception):
    """Base domain error for policy notifications."""


class PolicyNotificationConflictError(PolicyNotificationError):
    """Raised when an immutable or duplicate workflow is requested."""


class InvalidPolicyNotificationError(PolicyNotificationError):
    """Raised when editable customer copy is empty or inconsistent."""


@dataclass(frozen=True, slots=True)
class PolicyNotificationId:
    """Validated policy notification identifier."""

    value: str

    def __post_init__(self) -> None:
        try:
            UUID(self.value)
        except ValueError as error:
            raise InvalidPolicyNotificationError("invalid notification id") from error


@dataclass(frozen=True, slots=True)
class PolicyFact:
    """One structured fact extracted from the controlled source."""

    label: str
    value: str
    evidence: str


@dataclass(frozen=True, slots=True)
class PolicyEvidence:
    """Verbatim source evidence supporting the structured analysis."""

    quote: str
    section: str | None = None


_TOPIC_POLICY_TYPES = {
    PolicyTopic.BATTERY_WARRANTY: PolicyType.WARRANTY_POLICY,
    PolicyTopic.VEHICLE_WARRANTY: PolicyType.WARRANTY_POLICY,
    PolicyTopic.SPARE_PART_WARRANTY: PolicyType.WARRANTY_POLICY,
    PolicyTopic.BATTERY_RENTAL: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_PURCHASE: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_USAGE: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_REPLACEMENT: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_SWAP: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_CHARGING: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_COMPENSATION: PolicyType.BATTERY_POLICY,
    PolicyTopic.BATTERY_CONTRACT: PolicyType.BATTERY_POLICY,
    PolicyTopic.VEHICLE_PRICE: PolicyType.PRICE_POLICY,
    PolicyTopic.PROMOTION: PolicyType.PROMOTION_POLICY,
}


def normalized_policy_type(policy_type: PolicyType, topic: PolicyTopic) -> PolicyType:
    """Correct closed-taxonomy contradictions deterministically."""
    return _TOPIC_POLICY_TYPES.get(topic, policy_type)


@dataclass(frozen=True, slots=True)
class PolicyNotification:
    """Persisted AI analysis and human-reviewed notification copy."""

    id: PolicyNotificationId
    source_document_id: DocumentId
    policy_type: PolicyType
    topic: PolicyTopic
    secondary_topics: tuple[PolicyTopic, ...]
    affected_models: tuple[str, ...]
    effective_from: date | None
    effective_to: date | None
    facts: tuple[PolicyFact, ...]
    evidence: tuple[PolicyEvidence, ...]
    ai_confidence: float
    title: str
    content: str
    status: PolicyNotificationStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    published_by: str | None = None
    published_at: datetime | None = None
    scopes: tuple[PolicyScope, ...] = ()

    @classmethod
    def create_draft(
        cls,
        *,
        source_document_id: DocumentId,
        policy_type: PolicyType,
        topic: PolicyTopic,
        secondary_topics: tuple[PolicyTopic, ...],
        affected_models: tuple[str, ...],
        effective_from: date | None,
        effective_to: date | None,
        facts: tuple[PolicyFact, ...],
        evidence: tuple[PolicyEvidence, ...],
        ai_confidence: float,
        title: str,
        content: str,
        actor_id: str,
    ) -> PolicyNotification:
        """Create an AI-produced draft; this constructor cannot publish."""
        _validate_copy(title, content)
        if not 0.0 <= ai_confidence <= 1.0:
            raise InvalidPolicyNotificationError("confidence must be between zero and one")
        now = datetime.now(UTC)
        return cls(
            id=PolicyNotificationId(str(uuid4())),
            source_document_id=source_document_id,
            policy_type=normalized_policy_type(policy_type, topic),
            topic=topic,
            secondary_topics=secondary_topics,
            affected_models=affected_models,
            effective_from=effective_from,
            effective_to=effective_to,
            facts=facts,
            evidence=evidence,
            ai_confidence=ai_confidence,
            title=title.strip(),
            content=content.strip(),
            status=PolicyNotificationStatus.DRAFT,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )

    def edit(self, *, title: str, content: str, edited_at: datetime | None = None) -> PolicyNotification:
        """Replace only human-editable copy while the aggregate is a draft."""
        if self.status is PolicyNotificationStatus.PUBLISHED:
            raise PolicyNotificationConflictError("published notification is immutable")
        _validate_copy(title, content)
        return replace(
            self,
            title=title.strip(),
            content=content.strip(),
            updated_at=edited_at or datetime.now(UTC),
        )

    def with_scopes(self, scopes: tuple[PolicyScope, ...]) -> PolicyNotification:
        """Attach analyzer-proposed scopes before the draft is persisted."""
        if self.status is PolicyNotificationStatus.PUBLISHED:
            raise PolicyNotificationConflictError("published notification is immutable")
        return replace(self, scopes=scopes, updated_at=datetime.now(UTC))

    def publish(self, actor_id: str, published_at: datetime | None = None) -> PolicyNotification:
        """Publish explicitly and idempotently under a human actor."""
        if self.status is PolicyNotificationStatus.PUBLISHED:
            return self
        moment = published_at or datetime.now(UTC)
        return replace(
            self,
            status=PolicyNotificationStatus.PUBLISHED,
            published_by=actor_id,
            published_at=moment,
            updated_at=moment,
        )


def _validate_copy(title: str, content: str) -> None:
    if not title.strip() or not content.strip():
        raise InvalidPolicyNotificationError("title and content are required")
