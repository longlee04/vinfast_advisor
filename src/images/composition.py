"""Enabled-only Image adapter composition."""

from dataclasses import dataclass
from datetime import datetime

from minio import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.document.infrastructure.settings import DocumentSettings
from src.images.application.contracts import (
    DeleteImage,
    DetailImage,
    DownloadImage,
    ListImages,
    UploadImage,
)
from src.images.application.ports import ImageRepository, ImageStorage
from src.images.domain.entities import Image
from src.images.domain.values import ImageId
from src.images.infrastructure.minio_storage import MinioImageStorage
from src.images.infrastructure.repositories import SqlAlchemyImageRepository
from src.images.presentation.routes import ImageRouteServices


@dataclass(frozen=True, slots=True)
class ImageResources:
    """Concrete adapters serving the enabled image feature, or injected by tests."""

    repository: ImageRepository
    storage: ImageStorage
    engine: AsyncEngine | None = None

    def route_services(self) -> ImageRouteServices:
        """Expose use cases while keeping presentation independent of infrastructure."""
        return ImageRouteServices(
            upload=UploadImage(self.repository, self.storage),
            list_images=ListImages(self.repository),
            detail=DetailImage(self.repository),
            download=DownloadImage(self.repository, self.storage),
            delete=DeleteImage(self.repository, self.storage),
        )


class ImageComposition:
    """Construct concrete Image adapters only for enabled deployments."""

    def __init__(self, settings: DocumentSettings, resources: ImageResources | None = None) -> None:
        self._settings = settings
        self._resources = resources

    @property
    def enabled(self) -> bool:
        """Return whether the image feature is enabled."""
        return self._settings.enabled

    @property
    def resources(self) -> ImageResources | None:
        """Return constructed or injected resources without forcing disabled setup."""
        return self._resources

    async def start(self) -> None:
        """Create the database and storage adapters for enabled deployments."""
        if not self.enabled or self._resources is not None:
            return
        engine = create_async_engine(self._settings.database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        client = Minio(
            self._settings.minio_endpoint.removeprefix("http://").removeprefix("https://"),
            access_key=self._settings.access_key.get_secret_value(),
            secret_key=self._settings.secret_key.get_secret_value(),
            secure=self._settings.minio_endpoint.startswith("https://"),
        )
        try:
            bucket = self._settings.bucket_name
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except Exception:
            pass
        self._resources = ImageResources(
            repository=_SessionRepository(session_factory),
            storage=MinioImageStorage(client, self._settings),
            engine=engine,
        )

    async def shutdown(self) -> None:
        """Dispose only the engine owned by enabled production composition."""
        resources, self._resources = self._resources, None
        if resources is not None and resources.engine is not None:
            await resources.engine.dispose()


class _SessionRepository:
    """Open a short-lived session for image reads and writes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, image: Image) -> Image:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyImageRepository(session).add(image)

    async def get(self, image_id: ImageId) -> Image | None:
        async with self._session_factory() as session:
            return await SqlAlchemyImageRepository(session).get(image_id)

    async def list_active(self) -> tuple[Image, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyImageRepository(session).list_active()

    async def delete(self, image_id: ImageId, actor_id: str, deleted_at: datetime) -> Image | None:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyImageRepository(session).delete(image_id, actor_id, deleted_at)
