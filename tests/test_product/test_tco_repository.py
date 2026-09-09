"""Unit test cho `_assumption_snapshot` và regression test cho `_looks_like_uuid`.

Bối cảnh (finding 3 và 5 của đợt review cuối, 2026-08-08):

- Finding 3: `SqlAlchemyTcoRepository` lọc identifier không phải UUID trước khi
  đưa vào so sánh với cột `vehicle_id` (kiểu UUID) — nếu thiếu bước lọc này,
  asyncpg ném `DataError` ngay ở tầng driver khi tra cứu TCO bằng slug. Không
  có test nào bắt được việc xoá `_looks_like_uuid`.
- Finding 5: mọi cột tiền trên `tco_assumptions` đều nullable; nếu một hàng
  ACTIVE thiếu dữ liệu, `Decimal(str(None))` ném `decimal.InvalidOperation`
  (lộ thành lỗi 500) thay vì để `TcoService.estimate()` trả 422
  `tco_unavailable` như hợp đồng API yêu cầu.
"""

from __future__ import annotations

import os
import socket
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.products.infrastructure.repositories import (
    SqlAlchemyTcoRepository,
    _assumption_snapshot,
)
from src.products.infrastructure.seed_catalog import _seed

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
PRODUCT_TEST_DATABASE_URL = os.environ.get("PRODUCT_DATABASE_URL", "").strip() or DEFAULT_TEST_DATABASE_URL


def _server_is_reachable(url: str, default_port: int = 5432) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = parts.port or default_port
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Finding 5 — _assumption_snapshot: khong crash tren gia tri NULL, tra None.
# ---------------------------------------------------------------------------


def _fake_assumption(**overrides: object) -> SimpleNamespace:
    base = dict(
        assumption_id="00000000-0000-0000-0000-000000000001",
        region_code="VN",
        assumption_version=3,
        electricity_vnd_per_kwh=3150,
        registration_fee_percent=Decimal("0.00"),
        registration_fee_flat_vnd=0,
        plate_fee_vnd=14000000,
        inspection_fee_vnd=290000,
        inspection_first_month=36,
        inspection_interval_months=24,
        inspection_interval_months_after_7y=12,
        mandatory_insurance_vnd_per_year=480000,
        road_fee_vnd_per_year=1560000,
        maintenance_vnd_per_service=1500000,
        maintenance_interval_km=Decimal("12000.00"),
        horizon_months=60,
        source_note="nguồn mẫu",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_assumption_snapshot_is_none_when_row_is_none() -> None:
    assert _assumption_snapshot(None) is None


def test_assumption_snapshot_builds_full_dict_when_all_fields_present() -> None:
    snapshot = _assumption_snapshot(_fake_assumption())

    assert snapshot is not None
    assert snapshot["plate_fee_vnd"] == Decimal("14000000")
    assert snapshot["inspection_fee_vnd"] == Decimal("290000")
    assert snapshot["source_note"] == "nguồn mẫu"


@pytest.mark.parametrize(
    "field",
    [
        "electricity_vnd_per_kwh",
        "registration_fee_percent",
        "registration_fee_flat_vnd",
        "plate_fee_vnd",
        "inspection_fee_vnd",
        "mandatory_insurance_vnd_per_year",
        "road_fee_vnd_per_year",
        "maintenance_vnd_per_service",
        "maintenance_interval_km",
        "source_note",
    ],
)
def test_assumption_snapshot_is_none_when_a_required_field_is_null(field: str) -> None:
    """Trước fix: `Decimal(str(None))` ném `decimal.InvalidOperation` (500 ẩn).
    Sau fix: `_assumption_snapshot` trả None để `TcoService.estimate()` bắt
    bằng nhánh `if not assumptions: raise TcoUnavailableError(...)` sẵn có,
    cho ra 422 `tco_unavailable` như hợp đồng API yêu cầu."""
    assumption = _fake_assumption(**{field: None})

    assert _assumption_snapshot(assumption) is None


# ---------------------------------------------------------------------------
# Finding 3 — get_tco_snapshot bằng slug không phải UUID không được crash.
# ---------------------------------------------------------------------------


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


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _server_is_reachable(PRODUCT_TEST_DATABASE_URL),
    reason="PostgreSQL không reachable; chạy 'docker compose up -d postgres' trước",
)
async def test_get_tco_snapshot_by_slug_does_not_crash_on_uuid_typed_column(
    session_factory: async_sessionmaker,
) -> None:
    """Regression cho `_looks_like_uuid`: tra cứu bằng slug (không phải UUID)
    tưng nổ `asyncpg.exceptions.DataError` khi so sánh thẳng với cột
    `vehicle_id` kiểu UUID, trước khi Task 3 thêm bộ lọc này. Nếu ai đó xoá
    `_looks_like_uuid`, test này raise thay vì pass im lặng."""
    async with session_factory() as seed_session, seed_session.begin():
        await _seed(seed_session)
    repo = SqlAlchemyTcoRepository(session_factory)

    snapshot = await repo.get_tco_snapshot("vinfast-vf-2-all-new", region_code="KHU_VUC_II")

    assert snapshot is not None
    assert snapshot["vehicle_id"]
    assert snapshot["vehicle_type"] == "CAR"
