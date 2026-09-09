"""Real PostgreSQL and MinIO fixtures for Image integration tests."""

import os
import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from minio import Minio
from minio.deleteobjects import DeleteObject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.document.infrastructure.settings import DocumentSettings
from src.images.composition import ImageResources, _SessionRepository
from src.images.infrastructure.minio_storage import MinioImageStorage
from src.images.presentation.routes import build_image_router
from tests.support.document_test_schema import apply_document_test_schema
from tests.support.minio_test_bucket import assert_disposable_bucket_name
from tests.support.postgres_test_database import (
    TemporaryPostgresDatabase,
    assert_connection_uses_temporary_database,
    create_temporary_database,
    drop_temporary_database,
)

TEST_DATABASE_ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "").strip()
IMAGE_DATABASE_PREFIX = "p150_image_test_"
MINIO_ENDPOINT = os.environ.get("DOCUMENT_MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("DOCUMENT_ACCESS_KEY", "p150_minio")
MINIO_SECRET_KEY = os.environ.get("DOCUMENT_SECRET_KEY", "p150_minio_test_secret")
IMAGE_BUCKET_PREFIX = "image-test-"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _server_is_reachable(url: str, default_port: int) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = parts.port or default_port
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def image_postgres_is_reachable() -> None:
    """Skip safely unless an explicit PostgreSQL test-admin URL is reachable."""
    if not TEST_DATABASE_ADMIN_URL:
        pytest.skip("TEST_DATABASE_ADMIN_URL is required for Image integration tests")
    if not _server_is_reachable(TEST_DATABASE_ADMIN_URL, 5432):
        pytest.skip("PostgreSQL test service is not reachable")


@pytest_asyncio.fixture(scope="session")
async def image_database() -> AsyncIterator[TemporaryPostgresDatabase]:
    """Create, migrate, and remove a dedicated Image test database."""
    database = await create_temporary_database(
        TEST_DATABASE_ADMIN_URL,
        expected_prefix=IMAGE_DATABASE_PREFIX,
    )
    try:
        apply_document_test_schema(database, REPOSITORY_ROOT)
        yield database
    finally:
        await drop_temporary_database(database)


@pytest.fixture(scope="session")
def image_bucket_name() -> str:
    """Return a run-isolated bucket name to avoid retaining test data."""
    return f"{IMAGE_BUCKET_PREFIX}{uuid4().hex}"


@pytest.fixture(scope="session")
def minio_client(image_bucket_name: str) -> Iterator[Minio]:
    """Create a real client and fixture-owned private bucket."""
    if not _server_is_reachable(MINIO_ENDPOINT, 9000):
        pytest.skip("MinIO is not reachable; start it with 'docker compose up -d postgres minio'")
    client = Minio(
        MINIO_ENDPOINT.removeprefix("http://").removeprefix("https://"),
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_ENDPOINT.startswith("https://"),
    )
    assert_disposable_bucket_name(
        image_bucket_name,
        expected_prefix=IMAGE_BUCKET_PREFIX,
        owned_bucket_name=image_bucket_name,
    )
    client.make_bucket(image_bucket_name)
    try:
        yield client
    finally:
        assert_disposable_bucket_name(
            image_bucket_name,
            expected_prefix=IMAGE_BUCKET_PREFIX,
            owned_bucket_name=image_bucket_name,
        )
        objects = tuple(client.list_objects(image_bucket_name, recursive=True))
        errors = tuple(
            client.remove_objects(
                image_bucket_name,
                (DeleteObject(item.object_name) for item in objects),
            )
        )
        assert not errors
        client.remove_bucket(image_bucket_name)


@pytest_asyncio.fixture
async def image_engine(
    image_database: TemporaryPostgresDatabase,
) -> AsyncIterator[AsyncEngine]:
    """Migrate and expose the real Document PostgreSQL engine."""
    engine = create_async_engine(image_database.database_url)
    try:
        async with engine.connect() as connection:
            await assert_connection_uses_temporary_database(connection, image_database)
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def image_app(
    image_database: TemporaryPostgresDatabase,
    image_bucket_name: str,
    image_engine: AsyncEngine,
    minio_client: Minio,
) -> AsyncIterator[FastAPI]:
    """Build the production image route composition against real PostgreSQL and MinIO."""
    async with image_engine.begin() as connection:
        await assert_connection_uses_temporary_database(connection, image_database)
        await connection.execute(text("TRUNCATE TABLE images, vehicle_documents, documents CASCADE"))
    session_factory = async_sessionmaker(image_engine, expire_on_commit=False)
    settings = DocumentSettings(
        enabled=True,
        database_url=image_database.database_url,
        minio_endpoint=MINIO_ENDPOINT,
        bucket_name=image_bucket_name,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
    )
    resources = ImageResources(
        repository=_SessionRepository(session_factory),
        storage=MinioImageStorage(minio_client, settings),
        engine=image_engine,
    )
    application = FastAPI()
    application.include_router(build_image_router(resources.route_services()), prefix="/api/v1")
    try:
        yield application
    finally:
        async with image_engine.begin() as connection:
            await assert_connection_uses_temporary_database(connection, image_database)
            await connection.execute(text("TRUNCATE TABLE images, vehicle_documents, documents CASCADE"))
