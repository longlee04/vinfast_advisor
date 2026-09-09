"""Typed request and response schemas for the Image HTTP boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.images.domain.entities import Image


class ImageResponse(BaseModel):
    """Safe image metadata exposed to authenticated callers."""

    model_config = ConfigDict(frozen=True)

    id: str
    filename: str
    content_type: str
    byte_size: int
    created_by: str
    created_at: datetime

    @classmethod
    def from_image(cls, image: Image) -> "ImageResponse":
        """Convert domain metadata without exposing storage implementation fields."""
        return cls(
            id=image.id.value,
            filename=image.filename,
            content_type=image.content_type,
            byte_size=image.byte_size,
            created_by=image.created_by,
            created_at=image.created_at,
        )


class ImageListResponse(BaseModel):
    """Stable list of active images."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ImageResponse, ...]


class ImageDownloadResponse(BaseModel):
    """Short-lived presigned URL for an image."""

    model_config = ConfigDict(frozen=True)

    url: str
