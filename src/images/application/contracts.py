"""Image application use cases."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO

from src.images.application.errors import (
    ImageNotFoundError,
    ImagePersistenceError,
    ImageStorageUnavailableError,
)
from src.images.application.ports import ImageRepository, ImageStorage
from src.images.domain.entities import Image
from src.images.domain.values import ImageId


@dataclass(frozen=True, slots=True)
class UploadImageCommand:
    """Typed application input for a single client-provided image upload stream."""

    filename: str
    content_type: str
    data: BinaryIO
    actor_id: str


@dataclass(frozen=True, slots=True)
class UploadImage:
    """Coordinates object upload then metadata persistence with compensation."""

    repository: ImageRepository
    storage: ImageStorage

    async def execute(self, command: UploadImageCommand) -> Image:
        """Upload one image, persist its calculated metadata, or compensate."""
        provisional = Image.create(
            filename=command.filename,
            content_type=command.content_type,
            content_hash="",
            byte_size=0,
            object_key="",
            created_by=command.actor_id,
        )
        stored = await self.storage.upload(
            provisional.id,
            command.data,
            command.filename,
            command.content_type,
        )
        image = Image.create(
            filename=command.filename,
            content_type=stored.content_type,
            content_hash=stored.content_hash,
            byte_size=stored.byte_size,
            object_key=stored.object_key,
            created_by=command.actor_id,
        )
        try:
            return await self.repository.add(image)
        except ImagePersistenceError:
            await self._compensate(stored.object_key)
            raise
        except Exception as error:
            await self._compensate(stored.object_key)
            raise ImagePersistenceError() from error

    async def _compensate(self, object_key: str) -> None:
        """Attempt cleanup while preserving the database failure as the outcome."""
        try:
            await self.storage.remove(object_key)
        except ImageStorageUnavailableError:
            return


@dataclass(frozen=True, slots=True)
class ListImages:
    """List active images ordered by creation time descending."""

    repository: ImageRepository

    async def execute(self) -> tuple[Image, ...]:
        return await self.repository.list_active()


@dataclass(frozen=True, slots=True)
class DetailImage:
    """Return image metadata when it exists and has not been deleted."""

    repository: ImageRepository

    async def execute(self, image_id: ImageId) -> Image:
        image = await self.repository.get(image_id)
        if image is None or image.deleted_at is not None:
            raise ImageNotFoundError()
        return image


@dataclass(frozen=True, slots=True)
class DownloadImage:
    """Return a short-lived presigned URL for an active image."""

    repository: ImageRepository
    storage: ImageStorage

    async def execute(self, image_id: ImageId) -> str:
        image = await self.repository.get(image_id)
        if image is None or image.deleted_at is not None:
            raise ImageNotFoundError()
        return await self.storage.presign(image)


@dataclass(frozen=True, slots=True)
class DeleteImage:
    """Soft-delete an image and attempt to remove its stored bytes."""

    repository: ImageRepository
    storage: ImageStorage

    async def execute(self, image_id: ImageId, actor_id: str) -> Image:
        deleted = await self.repository.delete(image_id, actor_id, datetime.now(UTC))
        if deleted is None:
            raise ImageNotFoundError()
        try:
            await self.storage.remove(deleted.object_key)
        except ImageStorageUnavailableError:
            pass
        return deleted
