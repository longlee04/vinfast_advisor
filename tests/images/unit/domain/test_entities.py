"""Domain entity tests for Image."""

from datetime import UTC, datetime

import pytest

from src.images.domain.entities import Image
from src.images.domain.errors import InvalidFilenameError


class TestImageCreation:
    def test_create_image_succeeds_with_valid_metadata(self) -> None:
        image = Image.create(
            filename="logo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1024,
            object_key="images/uuid/token",
            created_by="admin",
        )

        assert image.filename == "logo.png"
        assert image.content_type == "image/png"
        assert image.byte_size == 1024
        assert image.object_key == "images/uuid/token"
        assert image.created_by == "admin"
        assert image.deleted_at is None

    def test_create_image_rejects_empty_filename(self) -> None:
        with pytest.raises(InvalidFilenameError):
            Image.create(
                filename="",
                content_type="image/png",
                content_hash="a" * 64,
                byte_size=1024,
                object_key="images/uuid/token",
                created_by="admin",
            )

    def test_create_image_rejects_whitespace_filename(self) -> None:
        with pytest.raises(InvalidFilenameError):
            Image.create(
                filename="   ",
                content_type="image/png",
                content_hash="a" * 64,
                byte_size=1024,
                object_key="images/uuid/token",
                created_by="admin",
            )


class TestImageDelete:
    def test_delete_sets_deleted_at_and_deleted_by(self) -> None:
        image = Image.create(
            filename="logo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1024,
            object_key="images/uuid/token",
            created_by="admin",
        )
        moment = datetime(2026, 8, 13, tzinfo=UTC)

        deleted = image.delete("admin", moment)

        assert deleted.deleted_at == moment
        assert deleted.deleted_by == "admin"

    def test_delete_is_idempotent(self) -> None:
        image = Image.create(
            filename="logo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1024,
            object_key="images/uuid/token",
            created_by="admin",
        )
        moment = datetime(2026, 8, 13, tzinfo=UTC)
        deleted = image.delete("admin", moment)

        second_delete = deleted.delete("admin", datetime(2026, 8, 14, tzinfo=UTC))

        assert second_delete.deleted_at == moment
        assert second_delete.deleted_by == "admin"
