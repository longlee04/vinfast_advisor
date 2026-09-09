"""Image repository integration tests against real PostgreSQL."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.images.domain.entities import Image
from src.images.infrastructure.repositories import SqlAlchemyImageRepository
from tests.support.postgres_test_database import (
    TemporaryPostgresDatabase,
    assert_connection_uses_temporary_database,
)


@pytest_asyncio.fixture
async def session_factory(image_engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(image_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_images(
    image_engine: AsyncEngine,
    image_database: TemporaryPostgresDatabase,
) -> None:
    async with image_engine.begin() as connection:
        await assert_connection_uses_temporary_database(connection, image_database)
        await connection.execute(sa.text("TRUNCATE TABLE images CASCADE"))


@pytest.mark.asyncio
async def test_repository_adds_and_retrieves_image(session_factory: async_sessionmaker) -> None:
    image = Image.create(
        filename="repo.png",
        content_type="image/png",
        content_hash="a" * 64,
        byte_size=42,
        object_key="images/repo/token",
        created_by="admin",
    )
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyImageRepository(session)
        await repository.add(image)

    async with session_factory() as session:
        repository = SqlAlchemyImageRepository(session)
        fetched = await repository.get(image.id)

    assert fetched is not None
    assert fetched.id == image.id
    assert fetched.filename == "repo.png"
    assert fetched.content_type == "image/png"
    assert fetched.byte_size == 42
    assert fetched.object_key == "images/repo/token"
    assert fetched.created_by == "admin"
    assert fetched.deleted_at is None


@pytest.mark.asyncio
async def test_repository_lists_only_active_images(session_factory: async_sessionmaker) -> None:
    active = Image.create(
        filename="active.png",
        content_type="image/png",
        content_hash="a" * 64,
        byte_size=1,
        object_key="images/active/token",
        created_by="admin",
    )
    deleted = Image.create(
        filename="deleted.png",
        content_type="image/png",
        content_hash="b" * 64,
        byte_size=1,
        object_key="images/deleted/token",
        created_by="admin",
    ).delete("admin", datetime(2026, 1, 1, tzinfo=UTC))
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyImageRepository(session)
        await repository.add(active)
        await repository.add(deleted)

    async with session_factory() as session:
        repository = SqlAlchemyImageRepository(session)
        images = await repository.list_active()

    assert len(images) == 1
    assert images[0].id == active.id


@pytest.mark.asyncio
async def test_repository_soft_delete_marks_image_deleted(session_factory: async_sessionmaker) -> None:
    image = Image.create(
        filename="to-delete.png",
        content_type="image/png",
        content_hash="a" * 64,
        byte_size=1,
        object_key="images/delete/token",
        created_by="admin",
    )
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyImageRepository(session)
        await repository.add(image)

    moment = datetime(2026, 8, 13, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyImageRepository(session)
        deleted = await repository.delete(image.id, "admin", moment)

    assert deleted is not None
    assert deleted.deleted_at == moment
    assert deleted.deleted_by == "admin"

    async with session_factory() as session:
        repository = SqlAlchemyImageRepository(session)
        fetched = await repository.get(image.id)

    assert fetched is not None
    assert fetched.deleted_at is not None
