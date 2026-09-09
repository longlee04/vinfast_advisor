"""Image domain entity."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from .errors import InvalidFilenameError
from .values import ImageId


@dataclass(frozen=True, slots=True)
class Image:
    """A privately stored user-uploaded image asset."""

    id: ImageId
    filename: str
    content_hash: str
    content_type: str
    byte_size: int
    object_key: str
    created_by: str
    created_at: datetime
    deleted_at: datetime | None = None
    deleted_by: str | None = None

    @classmethod
    def create(
        cls,
        filename: str,
        content_type: str,
        content_hash: str,
        byte_size: int,
        object_key: str,
        created_by: str,
    ) -> "Image":
        """Create a new uploaded image entity."""
        if not filename.strip():
            raise InvalidFilenameError()
        now = datetime.now(UTC)
        return cls(
            id=ImageId(str(uuid4())),
            filename=filename,
            content_type=content_type,
            content_hash=content_hash,
            byte_size=byte_size,
            object_key=object_key,
            created_by=created_by,
            created_at=now,
        )

    def delete(self, actor_id: str, deleted_at: datetime) -> "Image":
        """Soft-delete the image."""
        if self.deleted_at is not None:
            return self
        return replace(self, deleted_at=deleted_at, deleted_by=actor_id)
