"""Integration test cho SqlAlchemyVehicleRepository — chạy thật với Postgres.

Lý do tồn tại: các test khác trong `tests/test_product/` đều dùng
`FakeVehicleRepository` (in-memory), nên KHÔNG BAO GIỜ chạy qua code thật của
`src/products/infrastructure/repositories.py`. Điều đó khiến một bug kiểu
`NameError: name 'uuid' is not defined` (import bị đổi thành `from uuid import
uuid4` nhưng còn 2 chỗ gọi kiểu cũ `uuid.uuid4()`) không bị bất kỳ test nào
bắt được — `create_vehicle` bị bọc trong `except Exception`, lỗi biến mất
im lặng, và `POST /admin/vehicles` chết mà suite vẫn xanh.

Test này gọi thẳng `SqlAlchemyVehicleRepository` với session Postgres thật để
lớp bảo vệ đó tồn tại. Tự dọn dữ liệu đã tạo, không đụng tới 51 xe VinFast đã
seed sẵn trong DB dev.
"""

from __future__ import annotations

import os
import socket
import uuid
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.products.infrastructure.repositories import SqlAlchemyVehicleRepository

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
PRODUCT_TEST_DATABASE_URL = os.environ.get("PRODUCT_DATABASE_URL", "").strip() or DEFAULT_TEST_DATABASE_URL

_CHILD_TABLES = (
    "vehicle_prices",
    "cars",
    "motorbikes",
    "battery_policies",
    "vehicle_feature_flags",
    "promotion_vehicles",
)


def _server_is_reachable(url: str, default_port: int = 5432) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = parts.port or default_port
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _server_is_reachable(PRODUCT_TEST_DATABASE_URL),
        reason="PostgreSQL không reachable; chạy 'docker compose up -d postgres' trước",
    ),
]


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine(PRODUCT_TEST_DATABASE_URL)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup_vehicle(engine: AsyncEngine, vehicle_id: str) -> None:
    async with engine.begin() as conn:
        for table in _CHILD_TABLES:
            await conn.execute(text(f"DELETE FROM {table} WHERE vehicle_id = :vid"), {"vid": vehicle_id})
        await conn.execute(text("DELETE FROM vehicles WHERE vehicle_id = :vid"), {"vid": vehicle_id})


def _unique_brand() -> str:
    return f"IntegrationTest-{uuid.uuid4().hex[:8]}"


async def test_create_vehicle_persists_to_real_db(engine: AsyncEngine, session_factory: async_sessionmaker) -> None:
    """Regression test cho NameError: uuid.uuid4() phai chay het khong crash.

    Neu bug con o do, create_vehicle nem NameError, bi `except Exception: raise`
    o repositories.py bat lai va re-raise — test nay se fail ro rang thay vi
    im lang nhu khi di qua `except Exception: return None` cua tang route.
    """
    brand = _unique_brand()
    vehicle_id: str | None = None
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyVehicleRepository(session)
        detail = await repo.create_vehicle(
            {
                "brand": brand,
                "model_name": "Model Test",
                "vehicle_type": "CAR",
                "status": "ACTIVE",
                "specs": {"seat_count": 5},
                "prices": [{"price_type": "STARTING_PRICE", "amount_vnd": 100_000_000}],
            }
        )
        vehicle_id = detail.vehicle.vehicle_id
    try:
        # vehicle_id phai la UUID that (khong phai chuoi rong/None do bug cu).
        assert uuid.UUID(vehicle_id)
        assert detail.vehicle.brand == brand
        assert detail.vehicle.model_name == "Model Test"
        assert len(detail.prices) == 1
        assert uuid.UUID(detail.prices[0].price_id)
        assert detail.prices[0].amount_vnd == 100_000_000
    finally:
        await _cleanup_vehicle(engine, vehicle_id)


async def test_update_vehicle_ignores_vehicle_type_and_rejects_duplicate_slug(
    engine: AsyncEngine, session_factory: async_sessionmaker
) -> None:
    """update_vehicle: vehicle_type khong doi duoc qua PATCH; slug trung -> ValueError."""
    brand_a = _unique_brand()
    brand_b = _unique_brand()
    vehicle_id_a: str | None = None
    vehicle_id_b: str | None = None
    try:
        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            detail_a = await repo.create_vehicle(
                {"brand": brand_a, "model_name": "Xe A", "vehicle_type": "CAR", "status": "ACTIVE"}
            )
            detail_b = await repo.create_vehicle(
                {
                    "brand": brand_b,
                    "model_name": "Xe B",
                    "vehicle_type": "ELECTRIC_MOTORBIKE",
                    "status": "ACTIVE",
                }
            )
        vehicle_id_a = detail_a.vehicle.vehicle_id
        vehicle_id_b = detail_b.vehicle.vehicle_id
        slug_b = detail_b.vehicle.slug

        # vehicle_type bi loai khoi allowlist -> PATCH phai im lang bo qua.
        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            updated = await repo.update_vehicle(
                vehicle_id_a, {"vehicle_type": "ELECTRIC_MOTORBIKE", "brand": "Xe A Moi"}
            )
            assert updated.vehicle.vehicle_type.value == "CAR"
            assert updated.vehicle.brand == "Xe A Moi"
            assert updated.specs is not None  # spec cu (car) khong bi mo coi

        # slug cua B da ton tai -> gan cho A phai bi tu choi bang ValueError.
        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            with pytest.raises(ValueError):
                await repo.update_vehicle(vehicle_id_a, {"slug": slug_b})
    finally:
        if vehicle_id_a:
            await _cleanup_vehicle(engine, vehicle_id_a)
        if vehicle_id_b:
            await _cleanup_vehicle(engine, vehicle_id_b)


async def test_archive_restore_and_replace_prices_round_trip(
    engine: AsyncEngine, session_factory: async_sessionmaker
) -> None:
    """archive/restore/replace_vehicle_prices tra ve VehicleDetail dung, khong 404 gia."""
    brand = _unique_brand()
    vehicle_id: str | None = None
    try:
        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            created = await repo.create_vehicle(
                {
                    "brand": brand,
                    "model_name": "Xe Archive",
                    "vehicle_type": "CAR",
                    "status": "ACTIVE",
                    "prices": [{"price_type": "STARTING_PRICE", "amount_vnd": 500_000_000}],
                }
            )
        vehicle_id = created.vehicle.vehicle_id

        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            archived = await repo.archive_vehicle(vehicle_id)
            assert archived is not None
            assert archived.vehicle.status.value == "ARCHIVED"

        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            restored = await repo.restore_vehicle(vehicle_id)
            assert restored is not None
            assert restored.vehicle.status.value == "ACTIVE"

        async with session_factory() as session, session.begin():
            repo = SqlAlchemyVehicleRepository(session)
            replaced = await repo.replace_vehicle_prices(
                vehicle_id,
                [{"price_type": "LISTED", "amount_vnd": 600_000_000, "currency": "VND"}],
            )
            assert replaced is not None
            active = [p for p in replaced.prices if p.status.value == "ACTIVE"]
            expired = [p for p in replaced.prices if p.status.value == "EXPIRED"]
            assert len(active) == 1
            assert active[0].amount_vnd == 600_000_000
            assert len(expired) == 1
            assert expired[0].amount_vnd == 500_000_000
    finally:
        if vehicle_id:
            await _cleanup_vehicle(engine, vehicle_id)
