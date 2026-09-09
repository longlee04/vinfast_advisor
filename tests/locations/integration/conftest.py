"""Fixture Postgres cho test Locations."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.locations.infrastructure.models import LocationsBase


@pytest_asyncio.fixture
async def locations_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Đảm bảo bảng `locations` tồn tại, xóa dữ liệu test (EXT-%) trước và sau test.

    Thiếu DSN thì SKIP, không `raise`. Đây là test tích hợp cần Postgres thật —
    cùng loại với `tests/auth/integration/conftest.py`, nơi đã dùng
    `pytest.skip("PostgreSQL is not reachable; ...")` từ đầu.

    `raise RuntimeError` biến "môi trường chưa có database" thành lỗi ERROR, và
    một bộ test đỏ vì thiếu hạ tầng thì không phân biệt được với đỏ vì code sai —
    đúng lúc cần phân biệt nhất.
    """

    url = os.environ.get("LOCATIONS_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL")
    if not url:
        pytest.skip("Cần LOCATIONS_DATABASE_URL hoặc AUTH_DATABASE_URL để chạy test này")
    engine = create_async_engine(url, poolclass=None)
    async with engine.begin() as connection:
        await connection.run_sync(LocationsBase.metadata.create_all)
        await connection.execute(text("DELETE FROM locations WHERE external_id LIKE 'EXT-%'"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM locations WHERE external_id LIKE 'EXT-%'"))
        await engine.dispose()
