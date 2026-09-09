"""Application use case tests for Image."""

from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO

import pytest

from src.images.application.contracts import (
    DeleteImage,
    DetailImage,
    DownloadImage,
    ListImages,
    UploadImage,
    UploadImageCommand,
)
from src.images.application.errors import ImageNotFoundError
from src.images.application.ports import ImageRepository, ImageStorage, StoredImage
from src.images.domain.entities import Image
from src.images.domain.values import ImageId


class InMemoryImageRepository(ImageRepository):
    def __init__(self) -> None:
        self.images: dict[str, Image] = {}

    async def add(self, image: Image) -> Image:
        self.images[image.id.value] = image
        return image

    async def get(self, image_id: ImageId) -> Image | None:
        return self.images.get(image_id.value)

    async def list_active(self) -> tuple[Image, ...]:
        return tuple(
            image
            for image in sorted(self.images.values(), key=lambda i: i.created_at, reverse=True)
            if image.deleted_at is None
        )

    async def delete(self, image_id: ImageId, actor_id: str, deleted_at: datetime) -> Image | None:
        image = self.images.get(image_id.value)
        if image is None or image.deleted_at is not None:
            return None
        deleted = image.delete(actor_id, deleted_at)
        self.images[image_id.value] = deleted
        return deleted


class InMemoryImageStorage(ImageStorage):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    async def upload(self, image_id: ImageId, data: BytesIO, filename: str, content_type: str) -> StoredImage:
        payload = data.read()
        object_key = f"images/{image_id.value}/token"
        self.objects[object_key] = payload
        return StoredImage(
            object_key=object_key,
            content_hash="hash",
            content_type=content_type,
            byte_size=len(payload),
        )

    async def remove(self, object_key: str) -> None:
        self.removed.append(object_key)
        self.objects.pop(object_key, None)

    async def presign(self, image: Image) -> str:
        return f"https://download.invalid/{image.id.value}"


@pytest.fixture
def repository() -> InMemoryImageRepository:
    return InMemoryImageRepository()


@pytest.fixture
def storage() -> InMemoryImageStorage:
    return InMemoryImageStorage()


class TestUploadImage:
    @pytest.mark.asyncio
    async def test_upload_persists_image_and_returns_entity(
        self, repository: InMemoryImageRepository, storage: InMemoryImageStorage
    ) -> None:
        use_case = UploadImage(repository, storage)
        command = UploadImageCommand(
            filename="photo.png",
            content_type="image/png",
            data=BytesIO(b"pngdata"),
            actor_id="advisor",
        )

        image = await use_case.execute(command)

        assert image.filename == "photo.png"
        assert image.content_type == "image/png"
        assert image.byte_size == 7
        assert image.created_by == "advisor"
        assert image.object_key.startswith("images/")
        assert repository.images[image.id.value].id == image.id


class TestListImages:
    @pytest.mark.asyncio
    async def test_list_returns_only_active_images(self, repository: InMemoryImageRepository) -> None:
        active = Image.create(
            filename="active.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1,
            object_key="images/active/token",
            created_by="admin",
        )
        deleted = replace(active, id=ImageId("00000000-0000-0000-0000-000000000001")).delete(
            "admin", datetime(2026, 1, 1, tzinfo=UTC)
        )
        await repository.add(active)
        await repository.add(deleted)
        use_case = ListImages(repository)

        images = await use_case.execute()

        assert len(images) == 1
        assert images[0].id == active.id


class TestDetailImage:
    @pytest.mark.asyncio
    async def test_detail_returns_active_image(self, repository: InMemoryImageRepository) -> None:
        image = Image.create(
            filename="photo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1,
            object_key="images/photo/token",
            created_by="admin",
        )
        await repository.add(image)
        use_case = DetailImage(repository)

        result = await use_case.execute(image.id)

        assert result.id == image.id

    @pytest.mark.asyncio
    async def test_detail_raises_when_image_deleted(self, repository: InMemoryImageRepository) -> None:
        image = Image.create(
            filename="photo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1,
            object_key="images/photo/token",
            created_by="admin",
        ).delete("admin", datetime(2026, 1, 1, tzinfo=UTC))
        await repository.add(image)
        use_case = DetailImage(repository)

        with pytest.raises(ImageNotFoundError):
            await use_case.execute(image.id)


class TestDownloadImage:
    @pytest.mark.asyncio
    async def test_download_returns_presigned_url(
        self, repository: InMemoryImageRepository, storage: InMemoryImageStorage
    ) -> None:
        image = Image.create(
            filename="photo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1,
            object_key="images/photo/token",
            created_by="admin",
        )
        await repository.add(image)
        use_case = DownloadImage(repository, storage)

        url = await use_case.execute(image.id)

        assert url == f"https://download.invalid/{image.id.value}"


class TestDeleteImage:
    @pytest.mark.asyncio
    async def test_delete_soft_deletes_and_removes_storage(
        self, repository: InMemoryImageRepository, storage: InMemoryImageStorage
    ) -> None:
        image = Image.create(
            filename="photo.png",
            content_type="image/png",
            content_hash="a" * 64,
            byte_size=1,
            object_key="images/photo/token",
            created_by="admin",
        )
        await repository.add(image)
        use_case = DeleteImage(repository, storage)

        deleted = await use_case.execute(image.id, "admin")

        assert deleted.deleted_at is not None
        assert deleted.deleted_by == "admin"
        assert image.object_key in storage.removed

    @pytest.mark.asyncio
    async def test_delete_raises_when_image_missing(
        self, repository: InMemoryImageRepository, storage: InMemoryImageStorage
    ) -> None:
        use_case = DeleteImage(repository, storage)

        with pytest.raises(ImageNotFoundError):
            await use_case.execute(ImageId("00000000-0000-0000-0000-000000000000"), "admin")
