import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_turn_rejects_empty_message(client):
    """A4-4 thay `/chat` cũ: cùng hợp đồng 422 cho payload rỗng."""
    response = await client.post(
        "/api/v1/agent/turn", json={"session_id": "33333333-3333-3333-3333-333333333333", "message": ""}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_legacy_chat_and_status_are_gone(client):
    """`src/api/routes.py` + `src/agents/legacy_graph.py` đã bị A4-4 xoá."""
    assert (await client.post("/api/v1/chat", json={"message": ""})).status_code == 404
    assert (await client.get("/api/v1/status")).status_code == 404
