"""RetrievalServiceImpl — Service layer coordinating Layer 1 & Layer 2 retrieval (A1-2/3/6/7)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.catalog_reader import CatalogReadAdapter
from src.agents.adapters.feature_retriever import FeatureRetrievalAdapter
from src.agents.contracts import FeatureAssertion, FilterCriteria
from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger, log_file_execution
from src.agents.ports import CatalogReadPort, EmbeddingPort, FeatureRetrievalPort
from src.agents.services.slot_codec import coerce_vehicle_type

logger = get_agent_logger("agent.services.retrieval")


class RetrievalServiceImpl:
    """Retrieval service orchestrating Layer 1 hard filter and Layer 2 feature retrieval."""

    def __init__(
        self,
        catalog_reader: CatalogReadPort | None = None,
        feature_retriever: FeatureRetrievalPort | None = None,
        embedding: EmbeddingPort | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        log_file_execution("src/agents/services/retrieval.py", logger)
        # Nhận `session_factory` thay vì một `AsyncSession` mở sẵn: layer1/layer2
        # tự mở session theo từng lời gọi để luôn đọc catalog/feature flag mới
        # nhất, không giữ một transaction sống suốt vòng đời service.
        if catalog_reader is not None:
            self._catalog_reader = catalog_reader
        elif session_factory is not None:
            self._catalog_reader = CatalogReadAdapter(session_factory)
        else:
            raise ValueError("Either catalog_reader port or session_factory must be provided")

        if feature_retriever is not None:
            self._feature_retriever: FeatureRetrievalPort | None = feature_retriever
            self._session_factory: async_sessionmaker[AsyncSession] | None = None
        elif session_factory is not None:
            self._feature_retriever = None
            self._session_factory = session_factory
        else:
            raise ValueError("Either feature_retriever port or session_factory must be provided")
        self._embedding = embedding

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        """Execute Layer 1 SQL hard filter."""
        logger.info("RetrievalServiceImpl executing Layer 1 hard filter")
        return await self._catalog_reader.hard_filter(criteria)

    async def layer2(
        self, *, utterance: str, vehicle_type: VehicleType | str, candidate_ids: Sequence[UUID]
    ) -> list[FeatureAssertion]:
        """Execute Layer 2 feature retrieval (2a - 2e).

        `vehicle_type` vào đây là chuỗi thô vì node không được import `domain/`
        (mục 6.5b); đổi sang `VehicleType` ngay tại biên này trước khi xuống adapter.
        """
        logger.info("RetrievalServiceImpl executing Layer 2 feature retrieval for %d candidates", len(candidate_ids))
        resolved = coerce_vehicle_type(vehicle_type)
        if resolved is None:
            raise ValueError(f"loại phương tiện không hợp lệ: {vehicle_type!r}")
        if self._feature_retriever is not None:
            return await self._feature_retriever.resolve(
                utterance=utterance,
                vehicle_type=resolved,
                candidate_ids=list(candidate_ids),
            )
        # `FeatureRetrievalAdapter` có nhánh ghi (reverse write PENDING flag ở
        # 2e) nên session phải mở transaction thật (`session.begin()`) để ghi
        # được commit, khác các nhánh chỉ đọc ở trên.
        assert self._session_factory is not None
        async with self._session_factory() as session, session.begin():
            retriever = FeatureRetrievalAdapter(session, embedding_port=self._embedding)
            return await retriever.resolve(
                utterance=utterance,
                vehicle_type=resolved,
                candidate_ids=list(candidate_ids),
            )
