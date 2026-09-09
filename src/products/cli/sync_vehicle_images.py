"""Diem chay thu cong cho lenh dong bo anh xe."""

from __future__ import annotations

import logging

import anyio
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.document.infrastructure.settings import get_document_settings
from src.products.application.vehicle_image_sync import sync_vehicle_images
from src.products.infrastructure.vehicle_image_storage import (
    HttpVehicleImageDownloader,
    MinioVehicleImageStorage,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Create production adapters, run synchronization, and print counters."""
    settings = get_document_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    client = Minio(
        settings.minio_endpoint.removeprefix("http://").removeprefix("https://"),
        access_key=settings.access_key.get_secret_value(),
        secret_key=settings.secret_key.get_secret_value(),
        secure=settings.minio_endpoint.startswith("https://"),
    )
    try:
        async with session_factory() as session:
            result = await sync_vehicle_images(
                session=session,
                downloader=HttpVehicleImageDownloader(),
                storage=MinioVehicleImageStorage(client, settings),
                logger=logger,
            )
        print(f"synced={result.synced} skipped={result.skipped} failed={result.failed}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    anyio.run(main)
