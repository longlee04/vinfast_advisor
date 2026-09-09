"""Application errors for image operations."""

from dataclasses import dataclass


class ImageApplicationError(Exception):
    """Base error for safe image application failures."""


@dataclass(frozen=True, slots=True)
class ImageUploadRejectedError(ImageApplicationError):
    """Raised when upload content violates the image ingestion policy."""

    status_code: int

    def __str__(self) -> str:
        return "image upload was rejected"


@dataclass(frozen=True, slots=True)
class ImagePersistenceError(ImageApplicationError):
    """Raised by persistence adapters when image metadata cannot be committed."""

    def __str__(self) -> str:
        return "image metadata could not be persisted"


@dataclass(frozen=True, slots=True)
class ImageStorageUnavailableError(ImageApplicationError):
    """Raised when private object storage cannot complete an image operation."""

    status_code: int = 503

    def __str__(self) -> str:
        return "image storage is temporarily unavailable"


class ImageNotFoundError(ImageApplicationError):
    """Raised when a requested image does not exist or has been deleted."""

    def __str__(self) -> str:
        return "image not found"
