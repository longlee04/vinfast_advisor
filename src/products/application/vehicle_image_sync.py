"""Dong bo anh xe tu URL cong khai vao object storage rieng."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from logging import Logger
from typing import Final, Protocol

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.products.infrastructure.models import VehicleRow

IMAGE_WIDTH: Final = 192
IMAGE_HEIGHT: Final = 108
MAX_IMAGE_BYTES: Final = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS: Final = 10
_PAD_COLOUR: Final = (255, 255, 255)


class ImageDownloader(Protocol):
    """Tai mot URL cong khai thanh bytes."""

    async def fetch(self, url: str) -> bytes:
        """Return image bytes or raise ValueError for a recoverable download failure."""


class ImageStorage(Protocol):
    """Day anh da chuan hoa len object storage."""

    async def put(self, object_key: str, payload: bytes) -> None:
        """Store image bytes under object_key or raise ValueError on failure."""


@dataclass(frozen=True, slots=True)
class VehicleImageSyncResult:
    """So xe da dong bo, bo qua va that bai."""

    synced: int
    skipped: int
    failed: int


def normalize_image(payload: bytes) -> bytes:
    """Return deterministic 192x108 PNG fitted without stretching."""
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("image payload exceeds maximum allowed size")
    try:
        with Image.open(BytesIO(payload)) as source:
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("payload is not a readable image") from error

    image.thumbnail((IMAGE_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), _PAD_COLOUR)
    canvas.paste(image, ((IMAGE_WIDTH - image.width) // 2, (IMAGE_HEIGHT - image.height) // 2))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def image_digest(payload: bytes) -> str:
    """Return SHA-256 checksum for normalized image bytes."""
    return sha256(payload).hexdigest()


async def sync_vehicle_images(
    *,
    session: AsyncSession,
    downloader: ImageDownloader,
    storage: ImageStorage,
    logger: Logger,
) -> VehicleImageSyncResult:
    """Sync changed vehicle image URLs while preserving prior assets on failure."""
    result = await session.execute(
        select(VehicleRow).where(VehicleRow.image_url.is_not(None), VehicleRow.image_url != "")
    )
    synced = 0
    skipped = 0
    failed = 0

    for vehicle in result.scalars().all():
        image_url = vehicle.image_url
        if image_url is None:
            continue
        try:
            normalized = normalize_image(await downloader.fetch(image_url))
            digest = image_digest(normalized)
            if digest == vehicle.image_sha256:
                skipped += 1
                continue
            object_key = f"vehicles/{vehicle.vehicle_id}.png"
            await storage.put(object_key, normalized)
        except ValueError as error:
            logger.warning("bo qua anh xe %s tu %s: %s", vehicle.vehicle_id, image_url, error)
            failed += 1
            continue

        vehicle.image_object_key = object_key
        vehicle.image_sha256 = digest
        synced += 1

    if synced:
        await session.commit()
    return VehicleImageSyncResult(synced=synced, skipped=skipped, failed=failed)
