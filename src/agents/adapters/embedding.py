"""Embedding adapters implementing EmbeddingPort (mục 4 docs/team_split.md)."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Sequence

from src.agents.logging import get_agent_logger, log_file_execution
from src.config import get_settings

logger = get_agent_logger("agent.adapters.embedding")

# Khớp cột `Vector(1024)` của `vehicle_documents`. Không dùng 3072 (chiều gốc của
# text-embedding-3-large) vì index HNSW của pgvector chỉ nhận tối đa 2000 chiều —
# vượt ngưỡng thì index không tạo được và mọi truy vấn tương đồng thành seq scan.
EMBEDDING_DIMENSION = 1024

# Chiều riêng của adapter thay thế. Vector băm chỉ được so với nhau trong cùng một
# tiến trình và không bao giờ ghi xuống DB, nên nó không cần khớp cột — giữ 1536 để
# phân bố băm (và các ngưỡng tương đồng đã hiệu chỉnh theo nó) không đổi khi chiều
# thật thay đổi.
FALLBACK_EMBEDDING_DIMENSION = 1536


def _stable_index(token: str, dimension: int) -> int:
    """Băm ổn định giữa các tiến trình.

    `hash()` dựng sẵn của Python randomize theo `PYTHONHASHSEED` cho `str`, nên
    một adapter mang tên Deterministic mà dùng nó thì mỗi lần chạy ra một vector
    khác — E2E đóng băng (A9-2) mất ý nghĩa và test khớp vector thành flaky.
    """

    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dimension


class OpenAIEmbeddingAdapter:
    """Embedding adapter calling OpenAI Embeddings (text-embedding-3-small/large)."""

    def __init__(
        self, model_name: str = "text-embedding-3-large", dimensions: int | None = EMBEDDING_DIMENSION
    ) -> None:
        log_file_execution("src/agents/adapters/embedding.py", logger)
        self._model_name = model_name
        self._dimensions = dimensions
        self._api_key = get_settings().openai_api_key

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embedding vectors for input texts."""
        if not texts:
            return []

        if not self._api_key:
            if get_settings().app_env == "production":
                raise RuntimeError("OPENAI_API_KEY bắt buộc ở production: vector hash không dùng để phục vụ thật")
            logger.warning("OPENAI_API_KEY not set; falling back to deterministic embedding adapter")
            fallback = DeterministicEmbeddingAdapter(dimension=self._dimensions or 1536)
            return await fallback.embed(texts)

        try:
            from langchain_openai import OpenAIEmbeddings

            kwargs = {"model": self._model_name, "openai_api_key": self._api_key}
            if self._dimensions is not None:
                kwargs["dimensions"] = self._dimensions
            embeddings_client = OpenAIEmbeddings(**kwargs)
            return await embeddings_client.aembed_documents(list(texts))
        except Exception as exc:
            logger.warning("OpenAI Embedding call failed: %s; using deterministic fallback", exc)
            fallback = DeterministicEmbeddingAdapter(dimension=self._dimensions or 1536)
            return await fallback.embed(texts)


class DeterministicEmbeddingAdapter:
    """Deterministic, semantic-sensitive non-negative embedding adapter for test environments."""

    def __init__(self, dimension: int = FALLBACK_EMBEDDING_DIMENSION) -> None:
        self._dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate deterministic normalized non-negative vector based on weighted word tokens and character n-grams."""
        vectors = []
        for text_str in texts:
            vec = [0.0] * self._dimension
            clean_text = text_str.lower().strip()
            words = clean_text.split()

            # Non-negative word token weights
            word_counts = Counter(words)
            for word, count in word_counts.items():
                idx = _stable_index(word, self._dimension)
                vec[idx] += 3.0 * (1.0 + math.log(count))

            # Non-negative character 3-gram weights
            for word in words:
                if len(word) >= 3:
                    for i in range(len(word) - 2):
                        gram = word[i : i + 3]
                        idx = _stable_index(gram, self._dimension)
                        vec[idx] += 0.5

            # Normalize vector to unit length
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            else:
                vec[0] = 1.0

            vectors.append(vec)
        return vectors
