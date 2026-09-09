from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from .errors import InvalidDocumentIdError, UnsupportedStatusTransitionError


@dataclass(frozen=True, slots=True)
class DocumentId:
    value: str

    def __post_init__(self) -> None:
        try:
            UUID(self.value)
        except ValueError as error:
            raise InvalidDocumentIdError(self.value) from error


class ApprovalStatus(StrEnum):
    DRAFT = "draft"


class SourceAuthority(StrEnum):
    """Review level of the original policy source."""

    OFFICIAL = "OFFICIAL"
    INTERNAL_APPROVED = "INTERNAL_APPROVED"
    UNKNOWN = "UNKNOWN"


class VehicleDocumentStatus(StrEnum):
    """Trạng thái RAG chunk trong `vehicle_documents` — khác `ApprovalStatus` ở trên,
    vốn dùng cho file người dùng tải lên (`documents`)."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class ProcessingStatus(StrEnum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def ensure_processing_transition(current: ProcessingStatus, requested: ProcessingStatus) -> None:
    transitions = {
        ProcessingStatus.NOT_STARTED: {ProcessingStatus.QUEUED},
        ProcessingStatus.QUEUED: {ProcessingStatus.PROCESSING, ProcessingStatus.FAILED},
        ProcessingStatus.PROCESSING: {ProcessingStatus.COMPLETED, ProcessingStatus.FAILED},
        ProcessingStatus.COMPLETED: set(),
        ProcessingStatus.FAILED: {ProcessingStatus.QUEUED},
    }
    if requested not in transitions[current]:
        raise UnsupportedStatusTransitionError(current, requested)
