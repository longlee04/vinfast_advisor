"""Typed, transport-neutral bottleneck signal domain."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, TypeAlias
from uuid import UUID

from src.agents.domain.customer_profile import Bottleneck

OFFER_SUGGESTION_THRESHOLD: Final[float] = 0.6


class BottleneckSignalStatus(StrEnum):
    """Persisted advisor-verification state."""

    PENDING = "PENDING"
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"


class SignalVerdict(StrEnum):
    """Terminal verdict accepted from current lease holder."""

    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"


class BottleneckDetectionStatus(StrEnum):
    """Detector outcome; unavailable remains outside customer bottleneck labels."""

    DETECTED = "DETECTED"
    NONE = "NONE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class BottleneckDetected:
    """Closed-label bottleneck found in current customer turn."""

    status: BottleneckDetectionStatus
    label: Bottleneck
    evidence_quote: str
    confidence: float = 0.0
    model_name: str = "unspecified"
    prompt_version: str = "bottleneck-detection-v2"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("bottleneck confidence must be between 0 and 1")

    @property
    def allows_offer_suggestion(self) -> bool:
        """Allow automatic offer only for detector confidence at policy threshold.

        Chỉ xét khi thật sự DETECTED. Lượt `NONE`/`UNAVAILABLE` mang confidence
        mặc định 0.0 — lấy con số đó ra chặn là cắt gợi ý ưu đãi của MỌI lượt
        không phát hiện nút thắt, tức đổi hành vi ngoài phạm vi được giao.
        """

        if self.status is not BottleneckDetectionStatus.DETECTED:
            return True
        return self.confidence >= OFFER_SUGGESTION_THRESHOLD

    @property
    def offer_suggestion_withheld(self) -> bool:
        """Mark weak detections for handoff without automatic offer suggestion.

        KHÔNG đặt tên `offer_suggestion_ignored`: cột `review_queue` đã có đúng
        tên đó với nghĩa KHÁC HẲN — tư vấn viên chốt mục duyệt mà không áp ưu đãi
        (`review._should_mark_ignored`). Một bên là máy lúc xếp hàng, một bên là
        người lúc duyệt. Trùng tên là đọc log ra kết luận ngược.
        """

        return not self.allows_offer_suggestion


@dataclass(frozen=True, slots=True)
class BottleneckNone:
    """Detector found no supported bottleneck in current customer turn."""

    status: BottleneckDetectionStatus


@dataclass(frozen=True, slots=True)
class BottleneckUnavailable:
    """Detector could not safely classify current customer turn."""

    status: BottleneckDetectionStatus


BottleneckDetectionResult: TypeAlias = BottleneckDetected | BottleneckNone | BottleneckUnavailable


@dataclass(frozen=True, slots=True)
class SignalInsert:
    """Detection payload inserted beside outcome finalization transaction."""

    session_id: UUID
    client_turn_id: UUID
    anchor_client_turn_id: UUID
    label: Bottleneck
    evidence_quote: str
    model_name: str
    prompt_version: str

    def __post_init__(self) -> None:
        if not self.evidence_quote.strip():
            raise ValueError("signal evidence must not be empty")
        if not self.model_name.strip() or not self.prompt_version.strip():
            raise ValueError("signal provenance must not be empty")


@dataclass(frozen=True, slots=True)
class BottleneckSignal:
    """One persisted bottleneck signal and advisor task state."""

    signal_id: UUID
    session_id: UUID
    client_turn_id: UUID
    anchor_client_turn_id: UUID
    label: Bottleneck
    evidence_quote: str
    model_name: str
    prompt_version: str
    status: BottleneckSignalStatus
    claimed_by: str | None
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    advisor_id: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConfirmedBottleneckEvidence:
    """CORRECT evidence projected in stable customer-turn order."""

    signal_id: UUID
    client_turn_id: UUID
    turn_number: int
    label: Bottleneck
    evidence_quote: str


@dataclass(frozen=True, slots=True)
class OpportunitySignal:
    """Set-based CORRECT signal projection for one active conversation."""

    session_id: UUID
    customer_id: str
    labels: frozenset[Bottleneck]
    evidence: tuple[ConfirmedBottleneckEvidence, ...]
    last_active_at: datetime
    latest_signal_at: datetime
    correct_signal_count: int


@dataclass(slots=True)
class SignalNotFoundError(Exception):
    """Requested signal does not exist."""

    signal_id: UUID

    def __str__(self) -> str:
        return f"bottleneck signal {self.signal_id} not found"


@dataclass(slots=True)
class SignalClaimDeniedError(Exception):
    """Advisor does not hold active lease or signal already terminal."""

    signal_id: UUID
    advisor_id: str

    def __str__(self) -> str:
        return f"advisor {self.advisor_id} cannot decide bottleneck signal {self.signal_id}"
