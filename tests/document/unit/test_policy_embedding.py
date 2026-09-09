"""Authoritative policy embeddings must never use local fallback vectors."""

from __future__ import annotations

import pytest

from src.document.application.errors import PolicyEmbeddingUnavailableError
from src.document.infrastructure.policy_embedding import OpenAIPolicyEmbeddingAdapter


@pytest.mark.asyncio
async def test_missing_api_key_fails_instead_of_generating_fallback_vector() -> None:
    adapter = OpenAIPolicyEmbeddingAdapter(api_key="")

    with pytest.raises(PolicyEmbeddingUnavailableError):
        await adapter.embed(["Bằng chứng bảo hành đã được kiểm chứng."])


def test_document_composition_does_not_import_agent_embedding_adapter() -> None:
    source = open("src/document/composition.py", encoding="utf-8").read()

    assert "src.agents.adapters.embedding" not in source
