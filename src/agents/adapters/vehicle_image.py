"""Doc anh xe tu object storage theo ``vehicles.image_object_key``."""

from __future__ import annotations

from uuid import UUID

import anyio
from minio import Minio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.logging import get_agent_logger
from src.document.infrastructure.minio_storage import MinioClient
from src.document.infrastructure.settings import get_document_settings
from src.products.infrastructure.models import VehicleRow

logger = get_agent_logger("agent.adapters.vehicle_image")


def build_minio_vehicle_image_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> MinioVehicleImageSource | None:
    """Build image reader only when private object storage is configured."""
    settings = get_document_settings()
    access_key = settings.access_key.get_secret_value()
    secret_key = settings.secret_key.get_secret_value()
    if not all((settings.minio_endpoint, settings.bucket_name, access_key, secret_key)):
        return None
    client = Minio(
        settings.minio_endpoint.removeprefix("http://").removeprefix("https://"),
        access_key=access_key,
        secret_key=secret_key,
        secure=settings.minio_endpoint.startswith("https://"),
    )
    return MinioVehicleImageSource(
        session_factory=session_factory,
        client=client,
        bucket_name=settings.bucket_name,
    )


class MinioVehicleImageSource:
    """Implement VehicleImageSource tren private bucket cua du an."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        client: MinioClient,
        bucket_name: str,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._bucket_name = bucket_name

    async def load(self, vehicle_id: UUID) -> bytes | None:
        """Return normalized vehicle image, or None when catalog or storage lacks it."""
        try:
            async with self._session_factory() as session:
                object_key = await session.scalar(
                    select(VehicleRow.image_object_key).where(VehicleRow.vehicle_id == str(vehicle_id))
                )
        except (OSError, SQLAlchemyError):
            logger.warning("khong doc duoc anh xe %s tu object storage", vehicle_id, exc_info=True)
            return None
        if object_key is None:
            return None
        try:
            return await anyio.to_thread.run_sync(self._load_object, object_key)
        except Exception:  # noqa: BLE001
            logger.warning("khong doc duoc anh xe %s tu object storage", vehicle_id, exc_info=True)
            return None

    def _load_object(self, object_key: str) -> bytes:
        response = self._client.get_object(bucket_name=self._bucket_name, object_name=object_key)
        try:
            return response.read()
        finally:
            try:
                response.close()
            finally:
                response.release_conn()
