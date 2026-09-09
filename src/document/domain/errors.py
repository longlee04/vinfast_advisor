from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .values import DocumentId, ProcessingStatus


class DocumentDomainError(Exception):
    """Base error for document domain rule violations."""


@dataclass(frozen=True, slots=True)
class InvalidDocumentIdError(DocumentDomainError):
    value: str

    def __str__(self) -> str:
        return f"invalid document id: {self.value}"


@dataclass(frozen=True, slots=True)
class InvalidTitleError(DocumentDomainError):
    def __str__(self) -> str:
        return "document title must not be empty"


@dataclass(frozen=True, slots=True)
class UnsupportedStatusTransitionError(DocumentDomainError):
    current: ProcessingStatus
    requested: ProcessingStatus

    def __str__(self) -> str:
        return f"unsupported processing transition: {self.current} -> {self.requested}"


@dataclass(frozen=True, slots=True)
class ArchivedDocumentError(DocumentDomainError):
    document_id: DocumentId

    def __str__(self) -> str:
        return f"archived document cannot be mutated: {self.document_id.value}"


@dataclass(frozen=True, slots=True)
class InvalidPageSizeError(DocumentDomainError):
    page_size: int

    def __str__(self) -> str:
        return f"page size must be between 1 and 100: {self.page_size}"


@dataclass(frozen=True, slots=True)
class InvalidDocumentOrderingError(DocumentDomainError):
    ordering: tuple[str, str, str, str]

    def __str__(self) -> str:
        return f"unsupported document ordering: {self.ordering}"
