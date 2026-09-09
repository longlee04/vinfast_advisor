"""Hợp đồng HTTP cho việc chọn vị trí NGAY TRÊN thẻ lái thử (đợt 8, contract mục 2).

Lượt chat khi chưa biết vị trí trả thẻ `needs_location=True`; khách bấm "Dùng vị
trí của tôi" hoặc gõ quận/huyện trong thẻ → endpoint này dựng thẻ đầy đủ, LƯU vị
trí cho phiên, và ghi `conversation_core_state` y như act `ShowroomOptions` để nút
giờ bấm xong đi đúng đường `Book` của lượt chat.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import test_drive_routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.contracts import CatalogBrowseResult, FindNearbyLocationResult, VehiclePitch
from src.agents.core.state import CoreState, PendingKind, Stage
from src.agents.domain.nearby_location import LocationKind, UserLocation
from src.agents.domain.values import SlotName
from src.agents.ports import NearbyPlace
from src.agents.services.registry import AgentServices
from src.agents.services.test_drive import TestDriveServiceImpl

SESSION = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"
HANOI = {"latitude": 21.0285, "longitude": 105.8542}


class _Locations:
    def __init__(self, places: bool = True) -> None:
        self.seen: list[dict] = []
        self.places = places

    async def nearest(self, **kwargs) -> list[NearbyPlace]:
        self.seen.append(kwargs)
        if not self.places:
            return []
        return [
            NearbyPlace(
                id="sr-1",
                location_type="showroom_car",
                category_label="Showroom",
                name="Showroom Long Biên",
                address="Số 1 Nguyễn Văn Cừ",
                latitude=21.05,
                longitude=105.87,
                distance_km=1.2,
                hotline=None,
                open_time="09:00",
                close_time="18:00",
                status="1",
            )
        ]


class _NoBookings:
    async def count_active_at(self, showroom: str, moment: datetime) -> int:
        del showroom, moment
        return 0


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="VF 5", pitches=(VehiclePitch(vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 5", pitch="ok"),)
        )


class _Geocoder:
    """`nearby_location.answer(location_text=…)` → toạ độ, như lõi cũ."""

    def __init__(self, resolved: UserLocation | None) -> None:
        self.resolved = resolved
        self.seen: list[dict] = []

    async def answer(self, **kwargs) -> FindNearbyLocationResult:
        self.seen.append(kwargs)
        return FindNearbyLocationResult(answer="", locations=None, resolved_location=self.resolved)


class _Conversation:
    def __init__(self, *, owner: str | None = "customer-1", state: CoreState | None = None) -> None:
        self._owner = owner
        self.state = state
        self.location: dict | None = None
        self.saved_states: list[CoreState] = []

    async def get_session(self, session_id: str):
        if self._owner is None:
            return None
        return SimpleNamespace(customer_id=self._owner, archived_at=None)

    async def load_user_location(self, session_id: str) -> dict | None:
        return self.location

    async def save_user_location(self, session_id: str, payload) -> None:
        self.location = dict(payload) if payload else None

    async def load_core_state(self, session_id: str) -> CoreState | None:
        return self.state

    async def save_core_state(self, state: CoreState) -> None:
        self.saved_states.append(state)
        self.state = state


def _client(
    *,
    conversation: _Conversation | None = None,
    locations: _Locations | None = None,
    geocoder: _Geocoder | None = None,
    caller: str = "customer-1",
    with_service: bool = True,
) -> tuple[AsyncClient, _Conversation]:
    service = TestDriveServiceImpl(locations=locations or _Locations(), bookings=_NoBookings())
    application = FastAPI()
    application.include_router(test_drive_routes.router, prefix="/api/v1")
    conversation = conversation or _Conversation(
        state=CoreState(
            session_id=SESSION,
            stage=Stage.CHOSEN,
            chosen_vehicle_id=V1,
            slots={SlotName.VEHICLE_TYPE: "CAR"},
            turn_count=4,
        )
    )
    application.state.agent = SimpleNamespace(
        services=AgentServices(
            test_drive=service if with_service else None,
            conversation=conversation,
            catalog_browse=_Catalog(),
            nearby_location=geocoder,
        )
    )
    application.dependency_overrides[get_current_customer_id] = lambda: caller
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test"), conversation


URL = "/api/v1/agent/test-drive/options"


@pytest.mark.asyncio
async def test_toa_do_thi_dung_thang_luu_vi_tri_va_ghi_state() -> None:
    client, conversation = _client()
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, **HANOI})

    body = response.json()
    assert response.status_code == 200, body
    card = body["test_drive_card"]
    assert card["needs_location"] is False and card["vehicle_id"] == V1 and card["vehicle_name"] == "VinFast VF 5"
    assert card["showrooms"] and card["options"], "thẻ phải có showroom và ô giờ"
    # Đợt 9: cùng `navigate` như lượt chat để client mở bản đồ có ghim ngay.
    assert body["navigate"]["kind"] == "map" and len(body["navigate"]["showrooms"]) == len(card["showrooms"])
    assert body["quick_replies"] and all(item["value"].startswith("__lichlaithu__") for item in body["quick_replies"])
    # (b) vị trí lưu đúng kho mà `_known_location` đọc.
    assert conversation.location["latitude"] == pytest.approx(HANOI["latitude"])
    # (d) state ghi như act ShowroomOptions: pending showroom_slot + SCHEDULING + xe chốt.
    state = conversation.saved_states[-1]
    assert (
        state.pending is not None and state.pending.kind is PendingKind.CHOICE and state.pending.key == "showroom_slot"
    )
    assert state.stage is Stage.SCHEDULING and state.chosen_vehicle_id == V1


@pytest.mark.asyncio
async def test_chu_tu_do_thi_geocode_theo_loai_xe() -> None:
    geocoder = _Geocoder(UserLocation(latitude=21.0, longitude=105.8, source="text", label="Cầu Giấy"))
    client, conversation = _client(geocoder=geocoder)
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, "location_text": "Cầu Giấy"})

    assert response.status_code == 200, response.json()
    assert geocoder.seen[0]["location_text"] == "Cầu Giấy"
    assert list(geocoder.seen[0]["location_kinds"]) == [LocationKind.SHOWROOM_CAR]
    assert conversation.location["latitude"] == pytest.approx(21.0)


@pytest.mark.asyncio
async def test_geocode_khong_ra_thi_200_rong_kem_message() -> None:
    client, conversation = _client(geocoder=_Geocoder(None))
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, "location_text": "xóm nhà em"})

    body = response.json()
    assert response.status_code == 200
    assert body["test_drive_card"]["showrooms"] == [] and body["message"] == "Chưa tìm thấy showroom quanh đây"
    assert conversation.saved_states == [], "không ghi state cho một thẻ rỗng"


@pytest.mark.asyncio
async def test_khong_showroom_quanh_toa_do_cung_200_rong() -> None:
    client, _ = _client(locations=_Locations(places=False))
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, **HANOI})

    assert response.status_code == 200
    assert response.json()["message"] == "Chưa tìm thấy showroom quanh đây"


@pytest.mark.asyncio
async def test_thieu_vi_tri_thi_422() -> None:
    client, _ = _client()
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_xe_khong_co_thi_404() -> None:
    client, _ = _client()
    async with client:
        response = await client.post(
            URL, json={"session_id": SESSION, "vehicle_id": "33333333-3333-3333-3333-333333333333", **HANOI}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_phien_cua_nguoi_khac_thi_404() -> None:
    client, _ = _client(caller="customer-2")
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, **HANOI})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chua_noi_dich_vu_thi_503() -> None:
    client, _ = _client(with_service=False)
    async with client:
        response = await client.post(URL, json={"session_id": SESSION, "vehicle_id": V1, **HANOI})
    assert response.status_code == 503
