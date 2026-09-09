import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

import src.main as main_module
from src.locations.infrastructure.models import LocationsBase

#: Bốn test dưới đây gọi vào route Locations thật, mà route đó trả 503 khi
#: chưa nối được database — kể cả với ba test chỉ kiểm validation (422), vì
#: dependency được giải TRƯỚC khi FastAPI validate query. Thiếu database thì
#: SKIP, không để đỏ: một bộ test đỏ vì thiếu hạ tầng không phân biệt được
#: với đỏ vì code sai. Cùng khuôn với `conftest.py` cạnh file này và với
#: `tests/auth/integration/conftest.py`.
requires_locations_database = pytest.mark.skipif(
    not (os.environ.get("LOCATIONS_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL")),
    reason="Cần LOCATIONS_DATABASE_URL hoặc AUTH_DATABASE_URL để chạy test này",
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    url = os.environ.get("LOCATIONS_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL")
    if url:
        engine = create_async_engine(url, poolclass=None)
        async with engine.begin() as connection:
            await connection.run_sync(LocationsBase.metadata.create_all)
        await engine.dispose()

    async with main_module.app.router.lifespan_context(main_module.app):
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


@pytest.mark.asyncio
async def test_all_four_endpoints_are_published(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    assert "/api/v1/locations" in schema["paths"]
    assert "/api/v1/locations/nearby" in schema["paths"]
    assert "/api/v1/locations/categories" in schema["paths"]
    assert "/api/v1/locations/regions" in schema["paths"]


@requires_locations_database
@pytest.mark.asyncio
async def test_partial_bounds_are_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/locations", params={"south": 10.0, "north": 11.0})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_bounds"}


@requires_locations_database
@pytest.mark.asyncio
async def test_inverted_bounds_are_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/locations",
        params={"south": 11.0, "north": 10.0, "west": 106.0, "east": 107.0},
    )

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_bounds"}


@requires_locations_database
@pytest.mark.asyncio
async def test_nearby_without_coordinates_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/locations/nearby", params={"radius_km": 5})

    assert response.status_code == 422


@requires_locations_database
@pytest.mark.asyncio
async def test_nearby_radius_over_the_ceiling_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/locations/nearby",
        params={"lat": 21.0, "lon": 105.0, "radius_km": 500},
    )

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_radius"}


@requires_locations_database
@pytest.mark.asyncio
async def test_listing_returns_the_truncated_marker(client: AsyncClient) -> None:
    response = await client.get("/api/v1/locations", params={"limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "truncated" in body
