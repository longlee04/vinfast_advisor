"""HTTP contracts for the enabled Image presentation router."""

from datetime import datetime, timedelta
from io import BytesIO
from typing import BinaryIO

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.domain.authorization import Role
from src.document.infrastructure.settings import DocumentSettings
from src.images.application.contracts import (
    DeleteImage,
    DetailImage,
    DownloadImage,
    ListImages,
    UploadImage,
)
from src.images.application.ports import StoredImage
from src.images.domain.entities import Image
from src.images.domain.values import ImageId
from src.images.infrastructure.minio_storage import MinioImageStorage
from src.images.presentation.dependencies import CurrentPrincipal, get_current_principal
from src.images.presentation.routes import ImageRouteServices, build_image_router


class Repository:
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


class Storage:
    def __init__(self) -> None:
        self.presign_calls = 0
        self.put_calls: list[tuple[str, str, int, str]] = []
        self.removed: list[str] = []
        self._adapter = MinioImageStorage(
            self,
            DocumentSettings(
                enabled=True,
                database_url="postgresql+asyncpg://user:password@localhost:5432/images",
                minio_endpoint="https://minio.test",
                bucket_name="images",
                access_key="access-key",
                secret_key="secret-key",
            ),
        )

    async def upload(self, image_id: ImageId, data: BytesIO, filename: str, content_type: str) -> StoredImage:
        return await self._adapter.upload(image_id, data, filename, content_type)

    async def remove(self, object_key: str) -> None:
        self.removed.append(object_key)

    async def presign(self, image: Image) -> str:
        self.presign_calls += 1
        return f"https://download.invalid/{image.id.value}"

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        del data
        self.put_calls.append((object_name, bucket_name, length, content_type))

    def remove_object(self, *, bucket_name: str, object_name: str) -> None:
        del bucket_name, object_name

    def presigned_get_object(self, *, bucket_name: str, object_name: str, expires: timedelta) -> str:
        del bucket_name, object_name, expires
        return "https://unused.invalid"


@pytest.fixture
def app() -> tuple[FastAPI, Storage]:
    repository, storage = Repository(), Storage()
    services = ImageRouteServices(
        upload=UploadImage(repository, storage),
        list_images=ListImages(repository),
        detail=DetailImage(repository),
        download=DownloadImage(repository, storage),
        delete=DeleteImage(repository, storage),
    )
    application = FastAPI()
    application.include_router(build_image_router(services), prefix="/api/v1")
    return application, storage


async def _request(application: FastAPI, method: str, path: str, **kwargs: object):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_image_list_returns_401_for_anonymous_callers(app: tuple[FastAPI, Storage]) -> None:
    application, _ = app
    response = await _request(application, "GET", "/api/v1/images")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_customer_can_read_but_cannot_upload_or_delete_images(
    app: tuple[FastAPI, Storage],
) -> None:
    application, _ = app

    async def customer() -> CurrentPrincipal:
        return CurrentPrincipal("customer", Role.CUSTOMER)

    application.dependency_overrides[get_current_principal] = customer
    created = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": ("photo.png", b"pngdata", "image/png")},
    )
    listed = await _request(application, "GET", "/api/v1/images")
    deleted = await _request(application, "DELETE", "/api/v1/images/00000000-0000-0000-0000-000000000001")

    assert created.status_code == 403
    assert listed.status_code == 200
    assert deleted.status_code == 403


@pytest.mark.asyncio
async def test_advisor_can_upload_and_delete_image(app: tuple[FastAPI, Storage]) -> None:
    application, storage = app

    async def advisor() -> CurrentPrincipal:
        return CurrentPrincipal("advisor", Role.ADVISOR)

    application.dependency_overrides[get_current_principal] = advisor
    created = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": ("photo.png", b"pngdata", "image/png")},
    )

    assert created.status_code == 201
    assert created.json()["filename"] == "photo.png"
    assert created.json()["content_type"] == "image/png"
    assert created.json()["byte_size"] == 7
    assert storage.put_calls[0][0].startswith("images/")
    assert storage.put_calls[0][1] == "images"

    image_id = created.json()["id"]
    listed = await _request(application, "GET", "/api/v1/images")
    detail = await _request(application, "GET", f"/api/v1/images/{image_id}")
    download = await _request(application, "GET", f"/api/v1/images/{image_id}/download")
    deleted = await _request(application, "DELETE", f"/api/v1/images/{image_id}")

    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    assert detail.status_code == 200
    assert download.status_code == 200 and download.json()["url"].startswith("https://download.invalid/")
    assert deleted.status_code == 200
    assert image_id in {item["id"] for item in listed.json()["items"]}


@pytest.mark.asyncio
async def test_admin_can_upload_image(app: tuple[FastAPI, Storage]) -> None:
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    response = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": ("photo.jpg", b"jpgdata", "image/jpeg")},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "photo.jpg"
    assert response.json()["content_type"] == "image/jpeg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type"),
    (("photo.bmp", "image/bmp"), ("document.pdf", "application/pdf")),
)
async def test_image_upload_returns_415_for_non_image_files(
    app: tuple[FastAPI, Storage], filename: str, content_type: str
) -> None:
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    response = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": (filename, b"data", content_type)},
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "image upload rejected"}


@pytest.mark.asyncio
async def test_image_upload_returns_413_when_file_exceeds_limit(
    app: tuple[FastAPI, Storage],
) -> None:
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    oversized = b"x" * (25 * 1024 * 1024 + 1)
    response = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": ("big.png", oversized, "image/png")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "image upload rejected"}


@pytest.mark.asyncio
async def test_image_upload_returns_stable_422_for_malformed_multipart(
    app: tuple[FastAPI, Storage],
) -> None:
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    response = await _request(
        application,
        "POST",
        "/api/v1/images",
        content=b"invalid",
        headers={"content-type": "multipart/form-data; boundary=bad"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid image request"}


@pytest.mark.asyncio
async def test_image_detail_and_download_return_404_for_deleted_image(
    app: tuple[FastAPI, Storage],
) -> None:
    application, _ = app

    async def admin() -> CurrentPrincipal:
        return CurrentPrincipal("admin", Role.ADMIN)

    application.dependency_overrides[get_current_principal] = admin
    # Seed the repository through the upload endpoint would be cleaner, but direct mutation is acceptable for this assertion.
    # The repository is internal to the app fixture; we use the delete endpoint instead.
    created = await _request(
        application,
        "POST",
        "/api/v1/images",
        files={"file": ("photo.png", b"pngdata", "image/png")},
    )
    image_id = created.json()["id"]
    await _request(application, "DELETE", f"/api/v1/images/{image_id}")

    detail = await _request(application, "GET", f"/api/v1/images/{image_id}")
    download = await _request(application, "GET", f"/api/v1/images/{image_id}/download")

    assert detail.status_code == 404
    assert download.status_code == 404
