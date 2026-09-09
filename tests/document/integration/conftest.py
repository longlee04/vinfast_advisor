"""Real PostgreSQL and private MinIO fixtures for Document integration tests."""

import os
import socket
import subprocess
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

from src.document.composition import DocumentResources, _SessionRepository
from src.document.infrastructure.minio_storage import MinioObjectStorage
from src.document.infrastructure.repositories import DocumentUnitOfWork
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.routes import build_document_router
from tests.support.document_test_schema import (
    apply_document_test_schema,
    prepare_document_migration_database,
    run_document_alembic,
)
from tests.support.minio_test_bucket import assert_disposable_bucket_name
from tests.support.postgres_test_database import (
    TemporaryPostgresDatabase,
    assert_connection_uses_temporary_database,
    create_temporary_database,
    drop_temporary_database,
)

TEST_DATABASE_ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "").strip()
DOCUMENT_DATABASE_PREFIX = "p150_document_test_"
MINIO_ENDPOINT = os.environ.get("DOCUMENT_MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("DOCUMENT_ACCESS_KEY", "p150_minio")
MINIO_SECRET_KEY = os.environ.get("DOCUMENT_SECRET_KEY", "p150_minio_test_secret")
DOCUMENT_BUCKET_PREFIX = "document-test-"
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


def run_alembic(
    database: TemporaryPostgresDatabase,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run the Document migration command with the isolated Document URL."""
    return run_document_alembic(database, REPOSITORY_ROOT, *arguments)


@pytest.fixture(scope="session", autouse=True)
def document_postgres_is_reachable() -> None:
    """Skip safely unless an explicit PostgreSQL test-admin URL is reachable."""
    if not TEST_DATABASE_ADMIN_URL:
        pytest.skip("TEST_DATABASE_ADMIN_URL is required for Document integration tests")
    if not _server_is_reachable(TEST_DATABASE_ADMIN_URL, 5432):
        pytest.skip("PostgreSQL test service is not reachable")


@pytest_asyncio.fixture(scope="session")
async def document_database() -> AsyncIterator[TemporaryPostgresDatabase]:
    """Create, migrate, and remove a dedicated Document test database."""
    database = await create_temporary_database(
        TEST_DATABASE_ADMIN_URL,
        expected_prefix=DOCUMENT_DATABASE_PREFIX,
    )
    try:
        apply_document_test_schema(database, REPOSITORY_ROOT)
        yield database
    finally:
        await drop_temporary_database(database)


@pytest_asyncio.fixture
async def document_migration_database() -> AsyncIterator[TemporaryPostgresDatabase]:
    """Create a fresh disposable database for one migration lifecycle test."""
    database = await create_temporary_database(
        TEST_DATABASE_ADMIN_URL,
        expected_prefix=DOCUMENT_DATABASE_PREFIX,
    )
    try:
        prepare_document_migration_database(database, REPOSITORY_ROOT)
        yield database
    finally:
        await drop_temporary_database(database)


@pytest.fixture(scope="session")
def document_bucket_name() -> str:
    """Return a run-isolated bucket name to avoid retaining test data."""
    return f"{DOCUMENT_BUCKET_PREFIX}{uuid4().hex}"


@pytest.fixture(scope="session")
def minio_client(document_bucket_name: str) -> Iterator[Minio]:
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
        document_bucket_name,
        expected_prefix=DOCUMENT_BUCKET_PREFIX,
        owned_bucket_name=document_bucket_name,
    )
    client.make_bucket(document_bucket_name)
    try:
        yield client
    finally:
        assert_disposable_bucket_name(
            document_bucket_name,
            expected_prefix=DOCUMENT_BUCKET_PREFIX,
            owned_bucket_name=document_bucket_name,
        )
        objects = tuple(client.list_objects(document_bucket_name, recursive=True))
        errors = tuple(
            client.remove_objects(
                document_bucket_name,
                (DeleteObject(item.object_name) for item in objects),
            )
        )
        assert not errors
        client.remove_bucket(document_bucket_name)


@pytest_asyncio.fixture
async def document_engine(
    document_database: TemporaryPostgresDatabase,
) -> AsyncIterator[AsyncEngine]:
    """Migrate and expose the real Document PostgreSQL engine."""
    engine = create_async_engine(document_database.database_url)
    try:
        async with engine.connect() as connection:
            await assert_connection_uses_temporary_database(connection, document_database)
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def document_app(
    document_database: TemporaryPostgresDatabase,
    document_bucket_name: str,
    document_engine: AsyncEngine,
    minio_client: Minio,
) -> AsyncIterator[FastAPI]:
    """Build the production route composition against real PostgreSQL and MinIO."""
    async with document_engine.begin() as connection:
        await assert_connection_uses_temporary_database(connection, document_database)
        await connection.execute(
            text("TRUNCATE TABLE policy_notifications, vehicle_documents, documents CASCADE")
        )
    session_factory = async_sessionmaker(document_engine, expire_on_commit=False)
    settings = DocumentSettings(
        enabled=True,
        database_url=document_database.database_url,
        minio_endpoint=MINIO_ENDPOINT,
        bucket_name=document_bucket_name,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
    )
    resources = DocumentResources(
        repository=_SessionRepository(session_factory),
        unit_of_work=DocumentUnitOfWork(session_factory),
        storage=MinioObjectStorage(minio_client, settings),
        engine=document_engine,
    )
    application = FastAPI()
    application.include_router(build_document_router(resources.route_services()), prefix="/api/v1")
    try:
        yield application
    finally:
        async with document_engine.begin() as connection:
            await assert_connection_uses_temporary_database(connection, document_database)
            await connection.execute(
                text("TRUNCATE TABLE policy_notifications, vehicle_documents, documents CASCADE")
            )
