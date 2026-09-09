"""[FIND_NEARBY_LOCATION] Hợp đồng HTTP của hai endpoint tìm địa điểm.

App FastAPI tối giản + service thật chạy trên cổng giả — không lifespan, không
database, không mạng. Cùng cơ chế `tests/api/test_turn_recommendations.py` đang
dùng, và cố ý KHÔNG giả nốt service: thứ cần kiểm ở đây là số lượng, thứ tự, bộ
lọc theo loại và hình dạng JSON mà service thật sinh ra, chứ không phải khả năng
sao chép một dict đã dựng sẵn.

Hai endpoint, hai hợp đồng:

- `POST /locations/nearest` — bề mặt hiện hành, `location_type` bắt buộc.
- `POST /charging-stations/nearest` — bề mặt CŨ, phải giữ nguyên hình dạng.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import nearby_location_routes as routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.ports import GeocodedPlace, NearbyPlace
from src.agents.services.nearby_location import NearbyLocationServiceImpl
from src.agents.services.registry import AgentServices

#: Toạ độ hồ Hoàn Kiếm — gốc tính khoảng cách của mọi ca dưới đây.
ORIGIN = {"latitude": 21.0285, "longitude": 105.8542}


def _row(identifier: str, name: str, distance_km: float, location_type: str) -> NearbyPlace:
    return NearbyPlace(
        id=identifier,
        location_type=location_type,
        category_label="nhãn nguồn",
        name=name,
        address=f"{name}, Hà Nội",
        latitude=21.0123,
        longitude=105.8456,
        distance_km=distance_km,
        hotline="1900232389",
        open_time="06:00",
        close_time="22:00",
        status="1",
    )


#: Cả năm loại trộn lẫn trong MỘT bảng — đúng như `locations` thật. Đã sắp tăng
#: dần vì `NearbyLocationPort` cam kết như vậy (adapter sắp bằng `ORDER BY` trong
#: SQL); test kiểm rằng route KHÔNG đảo lại thứ tự đó.
ALL_ROWS = [
    _row("SR-CAR", "Showroom Ô tô Long Biên", 0.9, "showroom_car"),
    _row("CS-CAR", "Trạm sạc Vincom Bà Triệu", 1.24, "car_charging_station"),
    _row("SW-1", "Tủ đổi pin Nhà Thờ", 2.1, "battery_swap_station"),
    _row("CS-BIKE", "Trạm sạc xe máy Royal City", 3.51, "bike_charging_station"),
    _row("SR-BIKE", "Showroom Xe máy Cầu Giấy", 7.08, "showroom_escooter"),
]


class FakeStore:
    """Lọc theo loại và bán kính đúng như adapter thật làm bằng SQL."""

    async def nearest(self, *, latitude, longitude, radius_km, location_types, limit):
        del latitude, longitude
        wanted = set(location_types)
        return [row for row in ALL_ROWS if row.location_type in wanted and row.distance_km <= radius_km][:limit]


class FailingGeocoder:
    """Không tra ra địa danh nào — đúng hợp đồng `GeocodePort` (`None`, không raise)."""

    async def geocode(self, location_text: str) -> GeocodedPlace | None:
        del location_text
        return None


def _client(*, with_service: bool = True) -> AsyncClient:
    service = NearbyLocationServiceImpl(locations=FakeStore(), geocoder=FailingGeocoder()) if with_service else None
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    application.include_router(routes.legacy_router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(services=AgentServices(nearby_location=service))
    application.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


# ── Bề mặt hiện hành ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_returns_only_the_requested_kind() -> None:
    """[Bước 5'] Tra tủ đổi pin không được trả về showroom hay trạm sạc.

    Năm loại dùng chung một bảng và một service, nên một bộ lọc thiếu trả về đúng
    thứ trông giống kết quả — cùng khoảng cách, cùng hình dạng card — nhưng sai
    loại.
    """

    async with _client() as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={**ORIGIN, "location_type": ["BATTERY_SWAP_CABINET"]},
        )

    body = response.json()
    assert response.status_code == 200
    assert [item["id"] for item in body["results"]] == ["SW-1"]
    assert body["results"][0]["location_type"] == "BATTERY_SWAP_CABINET"
    assert body["results"][0]["category_label"] == "Tủ đổi pin"
    # Tủ đổi pin không có cổng sạc nào để nói.
    assert body["results"][0]["charger_type"] is None
    assert body["location_types"] == ["BATTERY_SWAP_CABINET"]
    assert body["action_type"] == "NEARBY_LOCATION_LIST"


@pytest.mark.asyncio
async def test_several_kinds_come_back_in_ascending_distance_order() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={
                **ORIGIN,
                "location_type": ["SHOWROOM_CAR", "SHOWROOM_MOTORBIKE"],
            },
        )

    body = response.json()
    assert response.status_code == 200
    # Vòng quét đầu tiên (5 km) đã có kết quả nên showroom xe máy ở 7,08 km chưa
    # được lấy — quét nới dần dừng ở bán kính đầu tiên có kết quả.
    assert [item["id"] for item in body["results"]] == ["SR-CAR"]
    assert body["searched_radius_km"] == 5.0
    distances = [item["distance_km"] for item in body["results"]]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_each_result_carries_a_directions_deep_link_from_the_customer() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={**ORIGIN, "location_type": ["CHARGING_STATION_CAR"]},
        )

    first = response.json()["results"][0]
    assert first["maps_url"].startswith("https://www.google.com/maps/dir/?api=1")
    assert "origin=21.0285,105.8542" in first["maps_url"]
    assert "destination=21.0123,105.8456" in first["maps_url"]
    assert first["charger_type"] == "CAR_CHARGER"


@pytest.mark.asyncio
async def test_failed_geocoding_returns_a_fallback_message_not_a_500() -> None:
    """Địa danh không tra ra là một câu trả lời, không phải một sự cố.

    Nhà cung cấp geocoding nằm ngoài tầm kiểm soát; để nó biến câu hỏi của khách
    thành HTTP 500 là đưa một lỗi hạ tầng ra tận màn hình khách.
    """

    async with _client() as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={
                "location_text": "Xã Không Tồn Tại",
                "location_type": ["SHOWROOM_CAR"],
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["needs_location"] is True
    assert body["results"] == []
    assert "Xã Không Tồn Tại" in body["reply_text"]


@pytest.mark.asyncio
async def test_request_without_any_location_is_rejected_not_guessed() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/locations/nearest", json={"location_type": ["SHOWROOM_CAR"]})

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "LOCATION_REQUIRED"}


@pytest.mark.asyncio
async def test_request_without_a_kind_is_rejected_by_validation() -> None:
    """`location_type` là bắt buộc: đoán loại hộ khách là trả sai bảng."""

    async with _client() as client:
        response = await client.post("/api/v1/locations/nearest", json=ORIGIN)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_kind_is_rejected_by_validation() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={**ORIGIN, "location_type": ["QUAN_CAFE"]},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_requires_authentication() -> None:
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(services=AgentServices())
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={**ORIGIN, "location_type": ["SHOWROOM_CAR"]},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_coordinates_are_written_back_to_the_session() -> None:
    """Bấm "Chia sẻ vị trí" phải dạy cho PHIÊN biết khách đang ở đâu.

    Không ghi thì lượt chat kế tiếp lại xin quyền vị trí lần nữa — đúng thứ mà bộ
    nhớ phiên sinh ra để tránh, và là mảnh nối duy nhất giữa đường REST (nút bấm)
    và đường `/agent/turn` (hội thoại).
    """

    saved: list[tuple[str, dict]] = []

    class FakeConversation:
        async def save_user_location(self, session_id, payload):
            saved.append((session_id, dict(payload)))

    service = NearbyLocationServiceImpl(locations=FakeStore())
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(
        services=AgentServices(nearby_location=service, conversation=FakeConversation())
    )
    application.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/locations/nearest",
            json={
                **ORIGIN,
                "location_type": ["CHARGING_STATION_CAR"],
                "session_id": "session-42",
            },
        )

    assert response.status_code == 200
    assert saved == [
        (
            "session-42",
            {
                "latitude": 21.0285,
                "longitude": 105.8542,
                "source": "browser",
                "label": None,
            },
        )
    ]


# ── Bề mặt CŨ, phải không đổi ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_endpoint_keeps_its_exact_shape() -> None:
    """[Bước 5'] `/charging-stations/nearest` cũ vẫn chạy y như trước.

    Client đã dựng theo hợp đồng này; một endpoint biến mất hay một trường đổi
    kiểu là một màn hình trắng chứ không phải một lỗi biên dịch.
    """

    async with _client() as client:
        response = await client.post("/api/v1/charging-stations/nearest", json=ORIGIN)

    body = response.json()
    assert response.status_code == 200
    assert body["action_type"] == "CHARGING_STATION_LIST"
    # Không cần `location_type` trong request, và không có nó trong từng phần tử.
    assert "location_type" not in body["results"][0]
    assert "location_types" not in body
    # Chỉ trạm sạc — CẢ HAI loại, đúng như endpoint này vẫn làm trước khi có năm
    # loại. Showroom (0,9 km) và tủ đổi pin (2,1 km) bị loại dù gần hơn CS-BIKE.
    assert [item["id"] for item in body["results"]] == ["CS-CAR", "CS-BIKE"]
    assert body["results"][0]["charger_type"] == "CAR_CHARGER"
    assert body["needs_location"] is False
    assert body["reply_text"]


@pytest.mark.asyncio
async def test_legacy_endpoint_still_reports_geocoding_failure_softly() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/charging-stations/nearest",
            json={"location_text": "Xã Không Tồn Tại"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["needs_location"] is True
    assert body["results"] == []
