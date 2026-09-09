"""SqlAlchemyFeatureVocabularyAdapter — A2-4: enum feature dựng tại runtime từ DB.

Danh sách `feature_code` không được viết cứng trong prompt (mục 6.7b): thêm một
hàng `feature_definitions` là đủ để tool schema có mã mới, không sửa file prompt.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger, log_file_execution
from src.products.infrastructure.models import FeatureDefinitionRow

logger = get_agent_logger("agent.adapters.feature_vocabulary")


class SqlAlchemyFeatureVocabularyAdapter:
    """Đọc `feature_definitions` đang `ACTIVE` cho một loại phương tiện."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        log_file_execution("src/agents/adapters/feature_vocabulary.py", logger)
        # Mở session mới cho từng lời gọi để luôn đọc feature_definitions mới
        # nhất, không giữ transaction sống suốt vòng đời adapter.
        self._session_factory = session_factory

    async def list_active_features(self, vehicle_type: VehicleType) -> list[tuple[str, str]]:
        """Trả `(feature_code, name)` theo `display_order`.

        Hàng có `vehicle_type` rỗng là feature dùng chung cho mọi loại xe, nên
        vẫn được lấy — lọc cứng theo đúng một giá trị sẽ đánh rơi nhóm này.
        """

        stmt = (
            select(FeatureDefinitionRow.feature_code, FeatureDefinitionRow.name)
            .where(
                FeatureDefinitionRow.status == "ACTIVE",
                or_(
                    FeatureDefinitionRow.vehicle_type == vehicle_type.value,
                    FeatureDefinitionRow.vehicle_type.is_(None),
                    FeatureDefinitionRow.vehicle_type == "",
                ),
            )
            .order_by(FeatureDefinitionRow.display_order, FeatureDefinitionRow.feature_code)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        logger.info("Feature vocabulary loaded: %d feature cho %s", len(rows), vehicle_type.value)
        return [(code, name) for code, name in rows]
