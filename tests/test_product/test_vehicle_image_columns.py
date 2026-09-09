"""Hai cot anh phai ton tai that tren DB, khong chi trong model."""

import os

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def _columns() -> set[str]:
    dsn = (os.environ.get("PRODUCT_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL") or "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    if not dsn:
        pytest.skip("Can PRODUCT_DATABASE_URL hoac AUTH_DATABASE_URL")
    connection = await asyncpg.connect(dsn)
    try:
        rows = await connection.fetch(
            "select column_name from information_schema.columns where table_name = 'vehicles'"
        )
    finally:
        await connection.close()
    return {row["column_name"] for row in rows}


async def test_vehicles_has_image_asset_columns() -> None:
    columns = await _columns()

    assert "image_object_key" in columns
    assert "image_sha256" in columns


async def test_image_columns_are_nullable() -> None:
    dsn = (os.environ.get("PRODUCT_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL") or "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    if not dsn:
        pytest.skip("Can PRODUCT_DATABASE_URL hoac AUTH_DATABASE_URL")
    connection = await asyncpg.connect(dsn)
    try:
        rows = await connection.fetch(
            "select column_name, is_nullable from information_schema.columns "
            "where table_name = 'vehicles' and column_name in ('image_object_key', 'image_sha256')"
        )
    finally:
        await connection.close()

    assert {row["is_nullable"] for row in rows} == {"YES"}
