"""Integration-level query behavior for vehicle overview RAG retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from src.agents.adapters.vehicle_overview_source import (
    TOPIC_QUERIES,
    SqlAlchemyVehicleOverviewSource,
)

TARGET_VEHICLE_ID = "11111111-1111-1111-1111-111111111111"
OTHER_VEHICLE_ID = "22222222-2222-2222-2222-222222222222"
ACTIVE_DOCUMENT_IDS = {
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
}
ARCHIVED_DOCUMENT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OTHER_DOCUMENT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


@dataclass(frozen=True, slots=True)
class Chunk:
    """Complete fake database row needed by the retrieval boundary."""

    document_id: str
    vehicle_id: str
    content: str
    status: str
    embedding: tuple[float, ...]


class DeterministicEmbedding:
    """Record batch inputs and return a stable local vector."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(index % 7) for index in range(1536)] for _ in texts]


class FakeResult:
    """Minimal read result exposing SQLAlchemy's ``all`` API."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, str]]:
        return self._rows


class ScopedReadSession:
    """Emulate scoped reads over seeded rows and reject non-SELECT statements."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self.statements: list[Any] = []

    async def __aenter__(self) -> ScopedReadSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: Any) -> FakeResult:
        assert statement.is_select, "overview retrieval must remain read-only"
        self.statements.append(statement)
        if len(self.statements) == 2:
            query_vectors = [
                value
                for value in statement.compile().params.values()
                if isinstance(value, list) and value and isinstance(value[0], float)
            ]
            assert [len(vector) for vector in query_vectors] == [1024]
        scoped = [chunk for chunk in self._chunks if chunk.vehicle_id == TARGET_VEHICLE_ID and chunk.status == "ACTIVE"]
        if len(self.statements) == 1:
            ranked = scoped
        else:
            ranked = list(reversed(scoped))
        return FakeResult([(chunk.document_id, chunk.content) for chunk in ranked])


class ScopedReadSessionFactory:
    """Provide the same fake database session for both hybrid rank queries."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.session = ScopedReadSession(chunks)

    def __call__(self) -> ScopedReadSession:
        return self.session


@pytest.mark.asyncio
async def test_retrieve_scopes_active_evidence_and_deduplicates_hybrid_ranks() -> None:
    chunks = [
        Chunk(
            document_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            vehicle_id=TARGET_VEHICLE_ID,
            content="Hệ thống hỗ trợ giữ làn đường.",
            status="ACTIVE",
            embedding=(0.2, 0.4, 0.6),
        ),
        Chunk(
            document_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            vehicle_id=TARGET_VEHICLE_ID,
            content="Camera quan sát và cảnh báo điểm mù.",
            status="ACTIVE",
            embedding=(0.3, 0.3, 0.6),
        ),
        Chunk(
            document_id=ARCHIVED_DOCUMENT_ID,
            vehicle_id=TARGET_VEHICLE_ID,
            content="Nội dung cũ đã lưu trữ.",
            status="ARCHIVED",
            embedding=(0.2, 0.4, 0.6),
        ),
        Chunk(
            document_id=OTHER_DOCUMENT_ID,
            vehicle_id=OTHER_VEHICLE_ID,
            content="Nội dung an toàn của xe khác.",
            status="ACTIVE",
            embedding=(0.2, 0.4, 0.6),
        ),
    ]
    embedding = DeterministicEmbedding()
    factory = ScopedReadSessionFactory(chunks)
    source = SqlAlchemyVehicleOverviewSource(factory, embedding)

    evidence = await source.retrieve((UUID(TARGET_VEHICLE_ID),), topic="safety")

    evidence_ids = [item.evidence_id for item in evidence]
    assert set(evidence_ids) == ACTIVE_DOCUMENT_IDS
    assert ARCHIVED_DOCUMENT_ID not in evidence_ids
    assert OTHER_DOCUMENT_ID not in evidence_ids
    assert len(evidence_ids) <= 3
    assert len(evidence_ids) == len(set(evidence_ids))
    assert embedding.calls == [[TOPIC_QUERIES["safety"]]]
    assert len(factory.session.statements) == 2
    for statement in factory.session.statements:
        compiled = statement.compile()
        assert "vehicle_documents.vehicle_id" in str(compiled)
        assert "vehicle_documents.status" in str(compiled)
        assert "vehicle_documents.valid_from" in str(compiled)
        assert "vehicle_documents.valid_to" in str(compiled)
        assert "ACTIVE" in compiled.params.values()
        assert [TARGET_VEHICLE_ID] in compiled.params.values()
