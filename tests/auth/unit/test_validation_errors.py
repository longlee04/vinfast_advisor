"""Regression coverage for scoped Auth validation errors."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/auth/staff/login", {"email": 7, "password": ["malformed"]}),
        ("/api/v1/auth/staff/complete-password", {"email": 7}),
        ("/api/v1/auth/admin/users/target/role", {}),
    ],
)
async def test_scoped_auth_validation_redacts_body_errors_and_disables_storage(
    path: str, payload: dict[str, object]
) -> None:
    """Given malformed Auth input, when request validates, then details stay redacted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        response = await client.request("PATCH" if path.endswith("/role") else "POST", path, json=payload)

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list("set-cookie") == []
    assert "validation" not in response.text
    assert "email" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["page=invalid", "page=0", "page_size=101"])
async def test_admin_validation_redacts_query_errors_and_disables_storage(query: str) -> None:
    """Given malformed admin query input, when request validates, then details stay redacted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        response = await client.get(f"/api/v1/auth/admin/users?{query}")

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list("set-cookie") == []
    assert query.split("=")[0] not in response.text


@pytest.mark.asyncio
async def test_customer_auth_validation_keeps_existing_fastapi_contract() -> None:
    """Given malformed customer input, when request validates, then FastAPI details remain available."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        response = await client.post("/api/v1/auth/login", json={"email": 7})

    assert response.status_code == 422
    assert isinstance(response.json().get("detail"), list)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list("set-cookie") == []
