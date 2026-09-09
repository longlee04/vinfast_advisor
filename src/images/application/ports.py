"""Application ports for the Image feature."""

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol

from src.images.domain.entities import Image
from src.images.domain.values import ImageId


@dataclass(frozen=True, slots=True)
class StoredImage:
    """Verified metadata calculated while storing a private image."""

    object_key: str
    content_hash: str
    content_type: str
    byte_size: int


class ImageRepository(Protocol):
    """Image metadata persistence capability."""

    async def add(self, image: Image) -> Image: ...
    async def get(self, image_id: ImageId) -> Image | None: ...
    async def list_active(self) -> tuple[Image, ...]: ...
    async def delete(self, image_id: ImageId, actor_id: str, deleted_at: datetime) -> Image | None: ...


class ImageStorage(Protocol):
    """Private binary storage capability used by image application services."""

    async def upload(self, image_id: ImageId, data: BinaryIO, filename: str, content_type: str) -> StoredImage: ...

    async def remove(self, object_key: str) -> None: ...

    async def presign(self, image: Image) -> str: ...
