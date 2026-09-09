"""A5-3: nguồn xếp hạng đọc snapshot đã đóng băng, không đọc catalog sống."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.conversation_repository import _slot_value
from src.agents.domain.feature_introduction import FeatureIntroductionRecord
from src.agents.domain.values import SlotName
from src.agents.models import AgentRunRow, ConversationSlotRow, RunSnapshotRow
from src.agents.services.recommendation import RunScoringContext
from src.agents.services.snapshotting import parse_snapshot
from src.products.infrastructure.models import (
    FeatureDefinitionRow,
    FeatureNeedTagRow,
    VehicleFeatureFlagRow,
)


class SqlAlchemyRecommendationDataSource:
    """Ghép snapshot đã đóng băng của run với slot hiện có của phiên (A5-2)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Mở session mới mỗi lần load() để đọc snapshot/slot mới nhất, không
        # giữ transaction sống suốt vòng đời adapter.
        self._session_factory = session_factory

    async def load(self, run_id: UUID) -> RunScoringContext | None:
        """Đọc `run_snapshots`/`conversation_slots`; không query lại catalog sống."""

        async with self._session_factory() as session:
            snapshot_row = (
                await session.execute(
                    select(RunSnapshotRow)
                    .where(RunSnapshotRow.run_id == run_id)
                    .order_by(RunSnapshotRow.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snapshot_row is None:
                return None
            envelope = parse_snapshot({**snapshot_row.payload, "captured_at": snapshot_row.captured_at})
            run = await session.get(AgentRunRow, run_id)
            if run is None:
                return None
            slot_rows = (
                await session.execute(
                    select(ConversationSlotRow).where(ConversationSlotRow.session_id == run.session_id)
                )
            ).scalars()
            slots = {
                SlotName(slot_row.slot_name): _slot_value(SlotName(slot_row.slot_name), slot_row)
                for slot_row in slot_rows
            }
            return RunScoringContext(snapshot=envelope, slots=slots)


class SqlAlchemyFeatureIntroductionSource:
    """Ghép feature-flag của xe với need-tag đã đóng để chọn tính năng giới thiệu."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Mở session mới mỗi lần load() để đọc feature flag mới nhất, không
        # giữ transaction sống suốt vòng đời adapter.
        self._session_factory = session_factory

    async def load(
        self, *, vehicle_ids: tuple[UUID, ...], need_tags: tuple[str, ...]
    ) -> Sequence[FeatureIntroductionRecord]:
        """Join ba bảng feature theo xe được xếp hạng và need-tag đã xác nhận."""

        if not vehicle_ids or not need_tags:
            return []
        statement = (
            select(VehicleFeatureFlagRow, FeatureDefinitionRow, FeatureNeedTagRow)
            .join(
                FeatureDefinitionRow,
                FeatureDefinitionRow.feature_code == VehicleFeatureFlagRow.feature_code,
            )
            .join(
                FeatureNeedTagRow,
                FeatureNeedTagRow.feature_code == VehicleFeatureFlagRow.feature_code,
            )
            .where(
                VehicleFeatureFlagRow.vehicle_id.in_([str(vehicle_id) for vehicle_id in vehicle_ids]),
                FeatureNeedTagRow.need_tag.in_(need_tags),
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [
            FeatureIntroductionRecord(
                vehicle_id=UUID(flag.vehicle_id),
                feature_code=flag.feature_code,
                feature_name=definition.name,
                need_tag=need_tag_row.need_tag,
                relevance=need_tag_row.relevance,
                flag_status=flag.status,
                verification_status=flag.verification_status,
                feature_status=definition.status,
                display_order=definition.display_order,
                evidence_ref=f"vehicle_feature_flags:{flag.vehicle_id}:{flag.feature_code}",
            )
            for flag, definition, need_tag_row in rows
        ]
