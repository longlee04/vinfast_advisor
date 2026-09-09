"""Disabled Document feature regressions for non-document application routes.

`/chat` và `/status` cũ đã bị A4-4 xoá; endpoint agent thật thay chỗ, hợp đồng
422 cho payload rỗng giữ nguyên.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.document.infrastructure.settings import DocumentSettings
from src.main import app, lifespan


@pytest.mark.asyncio
async def test_legacy_routes_preserve_contracts_when_document_feature_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setattr("src.main.get_document_settings", lambda: DocumentSettings(_env_file=None, enabled=False))

    # When
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/health")
            turn = await client.post(
                "/api/v1/agent/turn", json={"session_id": "44444444-4444-4444-4444-444444444444", "message": ""}
            )
            documents = await client.get("/api/v1/documents")

    # Then
    assert health.json()["status"] == "ok"
    assert turn.status_code == 422
    assert documents.status_code == 503
    assert documents.json() == {"detail": "Document service unavailable"}
