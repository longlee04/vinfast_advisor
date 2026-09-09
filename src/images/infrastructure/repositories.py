"""Async SQLAlchemy repository for Image metadata."""

from datetime import UTC, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.images.domain.entities import Image
from src.images.domain.values import ImageId
from src.images.infrastructure.models import ImageRow


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def _to_entity(row: ImageRow) -> Image:
    return Image(
        id=ImageId(row.id),
        filename=row.filename,
        content_type=row.content_type,
        content_hash=row.content_hash,
        byte_size=row.byte_size,
        object_key=row.object_key,
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        deleted_by=row.deleted_by,
        deleted_at=_utc(row.deleted_at) if row.deleted_at else None,
    )


class SqlAlchemyImageRepository:
    """Image metadata access without byte loading."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, image: Image) -> Image:
        await self._session.execute(
            insert(ImageRow).values(
                id=image.id.value,
                filename=image.filename,
                content_type=image.content_type,
                byte_size=image.byte_size,
                content_hash=image.content_hash,
                object_key=image.object_key,
                created_by=image.created_by,
                created_at=_utc(image.created_at),
                deleted_by=image.deleted_by,
                deleted_at=_utc(image.deleted_at) if image.deleted_at else None,
            )
        )
        return image

    async def get(self, image_id: ImageId) -> Image | None:
        row = await self._session.get(ImageRow, image_id.value)
        return _to_entity(row) if row else None

    async def list_active(self) -> tuple[Image, ...]:
        result = await self._session.execute(
            select(ImageRow).where(ImageRow.deleted_at.is_(None)).order_by(ImageRow.created_at.desc())
        )
        return tuple(_to_entity(row) for row in result.scalars())

    async def delete(self, image_id: ImageId, actor_id: str, deleted_at: datetime) -> Image | None:
        row = await self._session.get(ImageRow, image_id.value)
        if row is None or row.deleted_at is not None:
            return None
        moment = _utc(deleted_at)
        await self._session.execute(
            update(ImageRow)
            .where(ImageRow.id == image_id.value, ImageRow.deleted_at.is_(None))
            .values(deleted_at=moment, deleted_by=actor_id)
        )
        return _to_entity(await self._session.get(ImageRow, image_id.value))
