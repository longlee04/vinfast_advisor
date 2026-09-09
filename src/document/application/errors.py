"""Application errors for storage-backed document operations."""

from dataclasses import dataclass


class DocumentApplicationError(Exception):
    """Base error for safe document application failures."""


@dataclass(frozen=True, slots=True)
class DocumentUploadRejectedError(DocumentApplicationError):
    """Raised when upload content violates the fixed ingestion policy."""

    status_code: int

    def __str__(self) -> str:
        return "document upload was rejected"


@dataclass(frozen=True, slots=True)
class DocumentPersistenceError(DocumentApplicationError):
    """Raised by persistence adapters when metadata cannot be committed."""

    def __str__(self) -> str:
        return "document metadata could not be persisted"


@dataclass(frozen=True, slots=True)
class DocumentStorageUnavailableError(DocumentApplicationError):
    """Raised when private object storage cannot complete an operation."""

    status_code: int = 503

    def __str__(self) -> str:
        return "document storage is temporarily unavailable"


class UnsupportedPolicyDocumentError(DocumentApplicationError):
    """Raised when a stored file type is outside the policy-analysis MVP."""


class DocumentTextUnavailableError(DocumentApplicationError):
    """Raised when a supported file contains no meaningful extractable text."""


class DocumentTextTooLargeError(DocumentApplicationError):
    """Raised instead of silently chunking an oversized synchronous request."""


class PolicyAnalyzerUnavailableError(DocumentApplicationError):
    """Raised when the configured LLM cannot return a valid structured result."""


class PolicyCorpusEmptyError(DocumentApplicationError):
    """Raised when a policy has no literal source evidence safe for RAG."""


class PolicySourceUnreviewedError(DocumentApplicationError):
    """Raised when an Admin attempts to publish an unknown/unattributed source."""


class PolicyEmbeddingUnavailableError(DocumentApplicationError):
    """Raised when real, schema-compatible policy embeddings cannot be generated."""


@dataclass(frozen=True, slots=True)
class PolicyVehicleResolutionError(DocumentApplicationError):
    """Raised when one or more reviewed model scopes cannot resolve exactly."""

    unresolved_models: tuple[str, ...]

    def __str__(self) -> str:
        return "policy vehicle scope could not be resolved"
