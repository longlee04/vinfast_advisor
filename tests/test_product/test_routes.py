"""Integration tests cho Product FastAPI routes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.products.application.tco_service import TcoService
from src.products.domain.entities import VehicleShowcaseItem
from src.products.presentation.routes import _detail_out
from src.products.presentation.routes import router as products_router
from tests.test_product.test_services import _car_detail
from tests.test_product.test_tco_service import FakeTcoRepository, car_snapshot


def _tco_app(snapshot: dict | None) -> FastAPI:
    """FastAPI de rieng cho endpoint TCO, dung fake repository (khong cham DB).

    Theo mau o `tests/document/integration/test_http.py`: dung mot `FastAPI()`
    doc lap, `include_router(...)` truc tiep, va bom fake qua `app.state`.
    """
    application = FastAPI()
    application.include_router(products_router, prefix="/api/v1")
    application.state.product = SimpleNamespace(tco_service=TcoService(FakeTcoRepository(snapshot)))
    return application


async def _get(application: FastAPI, path: str):
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        return await client.get(path)


def test_vehicle_detail_maps_showcase_source_metadata() -> None:
    now = datetime(2026, 8, 11, tzinfo=UTC)
    detail = replace(
        _car_detail(),
        showcase_items=[
            VehicleShowcaseItem(
                showcase_item_id="a62963c3-958d-5b96-8e3b-e80c19eb600f",
                vehicle_id="v-car-1",
                section_key="overview",
                item_key="overview.hero-wide",
                title="VF 8",
                display_order=0,
                source_url="https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf8.html",
                source_retrieved_at=now,
                created_at=now,
                updated_at=now,
                media_url="https://shop.vinfastauto.com/vf8.webp",
            )
        ],
    )

    output = _detail_out(detail)

    assert output.showcase_items[0].item_key == "overview.hero-wide"
    assert output.showcase_items[0].source_url.startswith("https://shop.vinfastauto.com/")


@pytest.mark.asyncio
async def test_get_vehicle_tco_returns_200_with_correctly_mapped_breakdown() -> None:
    """Regression cho anh xa TcoBreakdown.inspection_vnd -> inspection_fee_vnd
    o routes.py — day la diem chinh xac ma viec resolve ten truong cua Task 1
    co the lang le gay ra loi lan nua."""
    application = _tco_app(car_snapshot())

    response = await _get(
        application,
        "/api/v1/vehicles/veh-1/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 200
    breakdown = response.json()["data"]["breakdown"]

    expected = await TcoService(FakeTcoRepository(car_snapshot())).estimate(
        "veh-1", monthly_km=Decimal(1000), years=5, region_code="KHU_VUC_II"
    )
    assert breakdown["inspection_fee_vnd"] == int(expected.breakdown.inspection_vnd)
    assert breakdown["inspection_count"] == expected.breakdown.inspection_count


@pytest.mark.asyncio
async def test_get_vehicle_tco_returns_404_when_vehicle_not_found() -> None:
    application = _tco_app(None)

    response = await _get(
        application,
        "/api/v1/vehicles/khong-ton-tai/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "vehicle_not_found"}


@pytest.mark.asyncio
async def test_get_vehicle_tco_returns_422_when_unavailable() -> None:
    application = _tco_app(car_snapshot(assumptions=None))

    response = await _get(
        application,
        "/api/v1/vehicles/veh-1/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "tco_unavailable"}


@pytest.mark.asyncio
async def test_get_vehicle_tco_route_is_not_swallowed_by_vehicle_detail_route() -> None:
    """`/vehicles/{identifier}/tco` phai toi dung handler TCO, khong bi
    `/vehicles/{identifier}` (khai bao sau) nuot mat segment `/tco`."""
    application = _tco_app(car_snapshot())

    response = await _get(
        application,
        "/api/v1/vehicles/veh-1/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "breakdown" in data
    assert "vehicle" not in data


@pytest.mark.asyncio
async def test_get_vehicle_tco_returns_503_when_product_state_missing() -> None:
    application = FastAPI()
    application.include_router(products_router, prefix="/api/v1")
    # app.state.product khong duoc gan — mo phong dung guard getattr(..., None)

    response = await _get(
        application,
        "/api/v1/vehicles/veh-1/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_vehicle_tco_returns_503_when_tco_service_missing() -> None:
    application = FastAPI()
    application.include_router(products_router, prefix="/api/v1")
    application.state.product = SimpleNamespace()  # khong co tco_service

    response = await _get(
        application,
        "/api/v1/vehicles/veh-1/tco?province=C%E1%BA%A7n%20Th%C6%A1&monthly_distance_km=1000&ownership_years=5",
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_update_admin_vehicle_unauthorized() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/api/v1/admin/vehicles/v1",
            json={"model_name": "New Model"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_admin_vehicle_price_unauthorized() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/admin/vehicles/v1/prices/p1",
            json={"amount_vnd": 500000000},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_admin_vehicle_specs_unauthorized() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/admin/vehicles/v1/specs",
            json={"specs": {"range_km": 600}},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_review_admin_feature_flag_unauthorized() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/admin/vehicles/v1/feature-flags/GPS",
            json={"verification_status": "APPROVED"},
        )
        assert response.status_code == 403
