"""[Task 8] `TurnResponse.recommendations` — hợp đồng JSON cho card đề xuất xe.

Dùng lại đúng cơ chế fake `run_turn` đã có ở
`tests/agents/integration/test_conversation_api.py`: app FastAPI tối giản +
monkeypatch `run_turn` trong module route, không dựng lifespan/DB thật.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agents.api import routes
from src.agents.api.dependencies import get_current_customer_id
from src.agents.contracts import Citation, RecommendedVehicleView, TurnResult
from src.agents.services.registry import AgentServices

SESSION_ID = uuid4()
VEHICLE_ID = uuid4()
EVIDENCE_ID = uuid4()

FAKE_RESULT = TurnResult(
    session_id=str(SESSION_ID),
    answer="VF 6 đi được 399 km [1].",
    pending_question=None,
    recommendations=[
        RecommendedVehicleView(
            vehicle_id=VEHICLE_ID,
            rank=1,
            display_name="VF 6",
            image_url="https://cdn/vf6.png",
            starting_price_vnd="690000000",
            pitch="VF 6 đi được 399 km [1].",
            citations=(Citation(index=1, evidence_id=EVIDENCE_ID, source_record="cars:row"),),
        )
    ],
)

EMPTY_RESULT = TurnResult(
    session_id=str(SESSION_ID),
    answer="Chào anh, em tư vấn được gì ạ?",
    pending_question=None,
)


class _StubGraph:
    """Không dùng tới: `run_turn` bị monkeypatch trước khi chạm graph thật."""

    async def ainvoke(self, state: dict) -> dict:
        return state


def _fake_client(monkeypatch: pytest.MonkeyPatch, fake_result: TurnResult) -> AsyncClient:
    """Dựng app tối giản với `run_turn` giả trả sẵn `fake_result`."""

    async def fake_run_turn(*args: object, **kwargs: object) -> TurnResult:
        del args, kwargs
        return fake_result

    monkeypatch.setattr(routes, "run_turn", fake_run_turn)
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    application.state.agent = SimpleNamespace(graph=_StubGraph(), services=AgentServices())
    application.dependency_overrides[get_current_customer_id] = lambda: "customer-1"
    transport = ASGITransport(app=application)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_turn_serializes_recommendations_with_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _fake_client(monkeypatch, FAKE_RESULT) as client:
        response = await client.post("/api/v1/agent/turn", json={"session_id": str(SESSION_ID), "message": "xin chao"})

    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "VF 6 đi được 399 km [1]."
    assert body["recommendations"] == [
        {
            "vehicle_id": str(VEHICLE_ID),
            "rank": 1,
            "display_name": "VF 6",
            "image_url": "https://cdn/vf6.png",
            "starting_price_vnd": "690000000",
            "pitch": "VF 6 đi được 399 km [1].",
            "citations": [{"index": 1}],
        }
    ]
    citation = body["recommendations"][0]["citations"][0]
    assert "evidence_id" not in citation
    assert "source_record" not in citation


@pytest.mark.asyncio
async def test_turn_without_recommendations_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _fake_client(monkeypatch, EMPTY_RESULT) as client:
        response = await client.post("/api/v1/agent/turn", json={"session_id": str(SESSION_ID), "message": "xin chao"})

    assert response.json()["recommendations"] == []
    assert response.json()["nearby_locations"] is None


@pytest.mark.asyncio
async def test_turn_serializes_nearby_locations(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.agents.contracts import NearbyLocationListView, NearbyLocationView

    location_result = TurnResult(
        session_id=str(SESSION_ID),
        answer="Dưới đây là trạm sạc gần bạn nhất:",
        pending_question=None,
        nearby_locations=NearbyLocationListView(
            locations=[
                NearbyLocationView(
                    id="loc-1",
                    name="Trạm sạc VinFast Times City",
                    address="458 Minh Khai, Hà Nội",
                    latitude=20.995,
                    longitude=105.868,
                    distance_km=1.2,
                    location_type="CHARGING_STATION_CAR",
                    category_label="Trạm sạc Ô tô điện",
                    maps_url="https://maps.google.com/?q=20.995,105.868",
                    charger_type="CAR_CHARGER",
                )
            ],
            location_types=["CHARGING_STATION_CAR"],
            origin_latitude=21.0,
            origin_longitude=105.85,
        ),
    )
    async with _fake_client(monkeypatch, location_result) as client:
        response = await client.post(
            "/api/v1/agent/turn", json={"session_id": str(SESSION_ID), "message": "tìm trạm sạc"}
        )

    body = response.json()
    assert response.status_code == 200
    assert body["nearby_locations"] is not None
    assert len(body["nearby_locations"]["results"]) == 1
    loc = body["nearby_locations"]["results"][0]
    assert loc["name"] == "Trạm sạc VinFast Times City"
    assert loc["distance_km"] == 1.2
    assert loc["maps_url"] == "https://maps.google.com/?q=20.995,105.868"
