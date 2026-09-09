"""SQLAlchemy persistence model for the Image feature."""

from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.document.infrastructure.models import DocumentBase

IDENTIFIER_LENGTH: Final[int] = 64
FILENAME_LENGTH: Final[int] = 512
OBJECT_KEY_LENGTH: Final[int] = 1024
CONTENT_TYPE_LENGTH: Final[int] = 100
HASH_LENGTH: Final[int] = 128


class ImageRow(DocumentBase):
    """Mutable ORM row for uploaded image metadata."""

    __tablename__ = "images"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    filename: Mapped[str] = mapped_column(String(FILENAME_LENGTH), nullable=False)
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_LENGTH), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    object_key: Mapped[str] = mapped_column(String(OBJECT_KEY_LENGTH), nullable=False)
    created_by: Mapped[str] = mapped_column(String(IDENTIFIER_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_by: Mapped[str | None] = mapped_column(String(IDENTIFIER_LENGTH), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_images_active", "created_at", postgresql_where=text("deleted_at IS NULL")),)
