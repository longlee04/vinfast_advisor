"""Real-only embedding adapter for authoritative policy corpus rows."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.config import get_settings
from src.document.application.errors import PolicyEmbeddingUnavailableError
from src.document.application.policy_corpus import (
    DEFAULT_EMBEDDING_MODEL,
    VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger(__name__)


class OpenAIPolicyEmbeddingAdapter:
    """Create schema-sized OpenAI vectors without a deterministic fallback."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL, api_key: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name
        self._api_key = settings.openai_api_key if api_key is None else api_key

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return real provider vectors or fail before authoritative persistence."""

        if not texts:
            return []
        if not self._api_key:
            raise PolicyEmbeddingUnavailableError()
        try:
            from langchain_openai import OpenAIEmbeddings

            client = OpenAIEmbeddings(
                model=self._model_name,
                openai_api_key=self._api_key,
                dimensions=VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS,
            )
            vectors = await client.aembed_documents(list(texts))
        except PolicyEmbeddingUnavailableError:
            raise
        except Exception as error:  # noqa: BLE001 - provider/network failures map to one safe boundary
            logger.warning("Policy embedding request failed (%s)", type(error).__name__)
            raise PolicyEmbeddingUnavailableError() from error
        return [list(vector) for vector in vectors]
