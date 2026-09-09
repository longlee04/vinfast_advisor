"""Dong bo anh xe: tai, chuan hoa 192x108, ghi hai cot. Khong goi mang that."""

from __future__ import annotations

import io
from dataclasses import dataclass
from logging import getLogger
from types import SimpleNamespace

import pytest
from PIL import Image

from src.products.application.vehicle_image_sync import (
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MAX_IMAGE_BYTES,
    normalize_image,
    sync_vehicle_images,
)


def _png(width: int, height: int, colour: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalize_returns_exact_target_size() -> None:
    result = normalize_image(_png(1024, 576))

    assert Image.open(io.BytesIO(result)).size == (IMAGE_WIDTH, IMAGE_HEIGHT)


def test_normalize_pads_instead_of_stretching_a_square() -> None:
    result = normalize_image(_png(500, 500, (255, 0, 0)))
    image = Image.open(io.BytesIO(result)).convert("RGB")

    assert image.size == (IMAGE_WIDTH, IMAGE_HEIGHT)
    assert image.getpixel((0, IMAGE_HEIGHT // 2)) != (255, 0, 0)
    assert image.getpixel((IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2)) == (255, 0, 0)


def test_normalize_is_byte_identical_across_calls() -> None:
    source = _png(800, 450)

    assert normalize_image(source) == normalize_image(source)


def test_normalize_rejects_payload_that_is_not_an_image() -> None:
    with pytest.raises(ValueError):
        normalize_image(b"<html>not an image</html>")


def test_normalize_rejects_oversized_payload() -> None:
    with pytest.raises(ValueError):
        normalize_image(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_IMAGE_BYTES + 1))


@dataclass
class _FakeSession:
    rows: list[SimpleNamespace]
    committed: bool = False

    async def execute(self, _statement: object) -> SimpleNamespace:
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))

    async def commit(self) -> None:
        self.committed = True


@dataclass
class _FakeDownloader:
    payloads: dict[str, bytes | ValueError]

    async def fetch(self, url: str) -> bytes:
        payload = self.payloads[url]
        if isinstance(payload, ValueError):
            raise payload
        return payload


@dataclass
class _FakeStorage:
    uploads: list[tuple[str, bytes]]

    async def put(self, object_key: str, payload: bytes) -> None:
        self.uploads.append((object_key, payload))


@pytest.mark.asyncio
async def test_sync_uploads_changed_image_and_updates_fields() -> None:
    row = SimpleNamespace(
        vehicle_id="vehicle-1", image_url="https://example/one", image_sha256=None, image_object_key=None
    )
    session = _FakeSession([row])
    downloader = _FakeDownloader({row.image_url: _png(320, 180)})
    storage = _FakeStorage([])

    result = await sync_vehicle_images(
        session=session,
        downloader=downloader,
        storage=storage,
        logger=getLogger("test"),
    )

    assert result.synced == 1
    assert result.skipped == 0
    assert result.failed == 0
    assert storage.uploads[0][0] == "vehicles/vehicle-1.png"
    assert row.image_object_key == "vehicles/vehicle-1.png"
    assert row.image_sha256 is not None
    assert session.committed


@pytest.mark.asyncio
async def test_sync_skips_matching_digest_without_upload() -> None:
    payload = normalize_image(_png(320, 180))
    from src.products.application.vehicle_image_sync import image_digest

    row = SimpleNamespace(
        vehicle_id="vehicle-2",
        image_url="https://example/two",
        image_sha256=image_digest(payload),
        image_object_key="vehicles/vehicle-2.png",
    )
    session = _FakeSession([row])
    storage = _FakeStorage([])

    result = await sync_vehicle_images(
        session=session,
        downloader=_FakeDownloader({row.image_url: _png(320, 180)}),
        storage=storage,
        logger=getLogger("test"),
    )

    assert result.skipped == 1
    assert result.synced == 0
    assert result.failed == 0
    assert storage.uploads == []
    assert not session.committed


@pytest.mark.asyncio
async def test_sync_failure_preserves_existing_fields() -> None:
    row = SimpleNamespace(
        vehicle_id="vehicle-3",
        image_url="https://example/broken",
        image_sha256="old-digest",
        image_object_key="vehicles/vehicle-3.png",
    )
    session = _FakeSession([row])
    storage = _FakeStorage([])

    result = await sync_vehicle_images(
        session=session,
        downloader=_FakeDownloader({row.image_url: ValueError("broken URL")}),
        storage=storage,
        logger=getLogger("test"),
    )

    assert result.failed == 1
    assert result.synced == 0
    assert result.skipped == 0
    assert storage.uploads == []
    assert row.image_sha256 == "old-digest"
    assert row.image_object_key == "vehicles/vehicle-3.png"
    assert not session.committed
