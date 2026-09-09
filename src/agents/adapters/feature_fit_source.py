"""Đọc cặp (tính năng xe CÓ THẬT, nhu cầu) kèm câu lợi ích đã duyệt từ `feature_need_tags`."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.domain.feature_fit import FeatureFit
from src.products.infrastructure.models import FeatureDefinitionRow, FeatureNeedTagRow, VehicleFeatureFlagRow


class SqlAlchemyFeatureFitSource:
    """Chỉ cờ `YES` + `APPROVED` và định nghĩa `ACTIVE`: cùng luật với bảng thông số gửi khách."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load(self, vehicle_ids: Sequence[UUID], need_tags: Sequence[str]) -> dict[UUID, list[FeatureFit]]:
        if not vehicle_ids or not need_tags:
            return {}
        statement = (
            select(
                VehicleFeatureFlagRow.vehicle_id,
                VehicleFeatureFlagRow.feature_code,
                FeatureDefinitionRow.name,
                FeatureNeedTagRow.need_tag,
                FeatureNeedTagRow.relevance,
                FeatureNeedTagRow.note,
            )
            .join(FeatureDefinitionRow, FeatureDefinitionRow.feature_code == VehicleFeatureFlagRow.feature_code)
            .join(FeatureNeedTagRow, FeatureNeedTagRow.feature_code == VehicleFeatureFlagRow.feature_code)
            .where(
                VehicleFeatureFlagRow.vehicle_id.in_([str(vehicle_id) for vehicle_id in vehicle_ids]),
                VehicleFeatureFlagRow.status == "YES",
                VehicleFeatureFlagRow.verification_status == "APPROVED",
                FeatureDefinitionRow.status == "ACTIVE",
                FeatureNeedTagRow.need_tag.in_(list(need_tags)),
                FeatureNeedTagRow.note.is_not(None),
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        grouped: dict[UUID, list[FeatureFit]] = {}
        for raw_vehicle_id, feature_code, name, need_tag, relevance, note in rows:
            if not str(note or "").strip():
                continue
            grouped.setdefault(UUID(str(raw_vehicle_id)), []).append(
                FeatureFit(
                    feature_code=str(feature_code),
                    feature_name=str(name),
                    need_tag=str(need_tag),
                    relevance=Decimal(str(relevance)),
                    note=str(note),
                )
            )
        return grouped


__all__ = ["SqlAlchemyFeatureFitSource"]
