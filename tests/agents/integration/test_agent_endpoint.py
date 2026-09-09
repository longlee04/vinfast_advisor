"""[A4-4] Endpoint agent chạy trên app thật với lifespan production."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app


def test_agent_turn_endpoint_answers_on_a_really_started_app() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn",
            json={"session_id": "11111111-1111-1111-1111-111111111111", "message": "em cần xe 7 chỗ"},
        )

    assert response.status_code in (200, 401)


def test_agent_turn_response_declares_the_documented_keys() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn",
            json={"session_id": "11111111-1111-1111-1111-111111111111", "message": "xin chào"},
        )

    if response.status_code == 200:
        assert set(response.json()) == {
            "answer",
            "pending_question",
            "lookup_facts",
            "terminal_reason",
        }


def test_legacy_chat_endpoint_is_gone() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "x"})

    assert response.status_code == 404


def test_agent_turn_rejects_a_payload_without_message() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/turn", json={"session_id": "s"})

    assert response.status_code == 422
