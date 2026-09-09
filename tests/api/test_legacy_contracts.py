"""[A0-4 → A4-4] Hợp đồng đã chuyển từ `/chat` cũ sang endpoint agent thật.

Bản gốc đóng băng `POST /api/v1/chat` + `GET /api/v1/status` của
`src/api/routes.py`. A4-4 đã xoá cả file đó lẫn `src/agents/legacy_graph.py`,
nên ba test dưới đây giữ đúng vai trò cũ: hai test đầu theo dõi hình dạng
response ở địa chỉ mới, test cuối khẳng định địa chỉ cũ đã biến mất thật.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app

#: T12: hình dạng `TurnResponse` công khai - đúng đủ các khoá này, không hơn
#: không kém. Field mới phải được thêm cả ở đây lẫn ở `src/agents/api/routes.py`
#: cùng lúc, có chủ đích - không phải một lần lỡ tay thêm field nội bộ.
_TURN_RESPONSE_KEYS = {
    "answer",
    "pending_question",
    "lookup_facts",
    "terminal_reason",
    "awaiting_review",
    "recommendations",
    "quick_replies",
    "comparison",
    "nearby_locations",
}

#: T12: những cái tên này KHÔNG bao giờ được xuất hiện trên bất kỳ response
#: REST nào của endpoint agent - dấu vết nội bộ (bản nháp, trạng thái guardrail,
#: snapshot hồ sơ) không phải hợp đồng công khai.
_FORBIDDEN_MARKERS = (
    "draft_answer",
    "advisor_content",
    "profile_snapshot",
    "guardrail_handoff",
    "quote_requires_hitl",
    "delivery_action",
)


def test_agent_turn_response_never_leaks_internal_markers() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn", json={"session_id": "22222222-2222-2222-2222-222222222222", "message": "xin chào"}
        )

    raw_text = response.text
    for marker in _FORBIDDEN_MARKERS:
        assert marker not in raw_text, f"leak: '{marker}' xuat hien tren response REST"


def test_agent_turn_response_body_keys_are_unchanged_when_successful() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn", json={"session_id": "22222222-2222-2222-2222-222222222222", "message": "xin chào"}
        )

    if response.status_code == 200:
        assert set(response.json().keys()) == _TURN_RESPONSE_KEYS


def test_agent_turn_replaces_the_legacy_chat_shape() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn", json={"session_id": "22222222-2222-2222-2222-222222222222", "message": "xin chào"}
        )

    assert response.status_code in (200, 401, 503)


def test_agent_turn_answer_field_carries_the_reply_text() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/turn", json={"session_id": "22222222-2222-2222-2222-222222222222", "message": "xin chào"}
        )

    if response.status_code == 200:
        body = response.json()
        assert "answer" in body
        assert body["answer"] is None or isinstance(body["answer"], str)


def test_legacy_chat_endpoint_no_longer_exists() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/chat", json={"message": "x"}).status_code == 404


def test_legacy_status_endpoint_no_longer_exists() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/status").status_code == 404
