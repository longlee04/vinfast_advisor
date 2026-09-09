"""PRD 5.6/5.7/5.8/5.10/5.12: endpoint van hanh phai ton tai, khong 404."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

OPERATIONS_PATHS = (
    "/api/v1/agent/review/00000000-0000-0000-0000-000000000000/claim",
    "/api/v1/agent/bookings",
    "/api/v1/agent/history/customer-1",
    "/api/v1/agent/notices",
    "/api/v1/agent/analytics/funnel",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", OPERATIONS_PATHS)
async def test_operations_router_is_mounted(path: str) -> None:
    """Each operations route group is registered and does not return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code != 404


@pytest.mark.asyncio
async def test_review_queue_without_credentials_is_rejected_not_missing() -> None:
    """Review route exists and rejects unauthenticated callers instead of returning 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/review/00000000-0000-0000-0000-000000000000/claim")

    assert response.status_code != 404
    assert response.status_code in {401, 403, 405}
