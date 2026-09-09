"""PRD 5.4: so sanh 2-3 mau, chan so cheo loai phuong tien."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.api.dependencies import get_agent, get_current_customer_id
from src.agents.domain.comparison import (
    ComparisonCell,
    ComparisonRow,
    ComparisonTable,
    CrossVehicleTypeComparisonError,
)
from src.agents.domain.values import VehicleType
from src.main import app


class ComparisonService:
    """Return a fixed comparison table from a service boundary."""

    def __init__(self, table: ComparisonTable) -> None:
        self._table = table

    async def compare(self, *, run_id: UUID, vehicle_ids: list[UUID]) -> ComparisonTable:
        return self._table


class CrossTypeComparisonService:
    """Expose cross-vehicle-type error at service boundary."""

    async def compare(self, *, run_id: UUID, vehicle_ids: list[UUID]) -> ComparisonTable:
        raise CrossVehicleTypeComparisonError


@pytest.fixture
def comparison_table() -> ComparisonTable:
    """Provide table containing nullable values for HTTP serialization."""

    first_vehicle_id, second_vehicle_id = uuid4(), uuid4()
    return ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(first_vehicle_id, second_vehicle_id),
        captured_at=datetime(2026, 8, 11, tzinfo=UTC),
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=(
                    ComparisonCell(
                        vehicle_id=first_vehicle_id,
                        value_text="500000000",
                        source="STRUCTURED",
                        evidence_ref="vehicles:1",
                        label=None,
                        is_better=True,
                    ),
                    ComparisonCell(
                        vehicle_id=second_vehicle_id,
                        value_text=None,
                        source=None,
                        evidence_ref=None,
                        label=None,
                    ),
                ),
            ),
        ),
    )


@pytest.fixture
def authenticated_agent(comparison_table: ComparisonTable):
    """Override narrow route seams with authenticated comparison composition."""

    composition = SimpleNamespace(services=SimpleNamespace(recommendation=ComparisonService(comparison_table)))
    app.dependency_overrides[get_agent] = lambda: composition
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    try:
        yield comparison_table
    finally:
        app.dependency_overrides.pop(get_agent, None)
        app.dependency_overrides.pop(get_current_customer_id, None)


@pytest.fixture
def unauthenticated_agent(comparison_table: ComparisonTable):
    composition = SimpleNamespace(services=SimpleNamespace(recommendation=ComparisonService(comparison_table)))
    app.dependency_overrides[get_agent] = lambda: composition
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_agent, None)


@pytest.mark.asyncio
async def test_compare_without_credentials_is_rejected(unauthenticated_agent) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/compare",
            json={"run_id": str(uuid4()), "vehicle_ids": [str(uuid4()), str(uuid4())]},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_compare_rejects_a_single_vehicle(authenticated_agent) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/compare",
            json={"run_id": str(uuid4()), "vehicle_ids": [str(uuid4())]},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_rejects_invalid_run_id(authenticated_agent) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/compare",
            json={"run_id": "invalid", "vehicle_ids": [str(uuid4()), str(uuid4())]},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_returns_snapshot_table_with_nullable_cells(
    authenticated_agent, comparison_table: ComparisonTable
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/compare",
            json={
                "run_id": str(uuid4()),
                "vehicle_ids": [str(vehicle_id) for vehicle_id in comparison_table.vehicle_ids],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "captured_at": "2026-08-11T00:00:00Z",
        "vehicle_ids": [str(vehicle_id) for vehicle_id in comparison_table.vehicle_ids],
        "rows": [
            {
                "criterion_code": "STARTING_PRICE_VND",
                "cells": [
                    {
                        "vehicle_id": str(comparison_table.vehicle_ids[0]),
                        "value_text": "500000000",
                        "source": "STRUCTURED",
                        "evidence_ref": "vehicles:1",
                        "label": None,
                        "is_better": True,
                    },
                    {
                        "vehicle_id": str(comparison_table.vehicle_ids[1]),
                        "value_text": None,
                        "source": None,
                        "evidence_ref": None,
                        "label": None,
                        "is_better": False,
                    },
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_compare_returns_cross_vehicle_type_reason() -> None:
    composition = SimpleNamespace(services=SimpleNamespace(recommendation=CrossTypeComparisonService()))
    app.dependency_overrides[get_agent] = lambda: composition
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/compare",
                json={"run_id": str(uuid4()), "vehicle_ids": [str(uuid4()), str(uuid4())]},
            )
    finally:
        app.dependency_overrides.pop(get_agent, None)
        app.dependency_overrides.pop(get_current_customer_id, None)

    assert response.status_code == 422
    assert response.json()["detail"] == "Không thể so sánh ô tô với xe máy điện trong cùng bảng"
