"""Đọc `promotions` (module products) cho ưu đãi theo cơ hội (plan Customer 360 Phase 5B).

Cùng khuôn `offer_suggestion_source`: agents đọc bảng products qua model của products, cùng DB.
`consume_use` tăng `used_count` bằng MỘT câu UPDATE có điều kiện — hai TVV bấm gửi cùng lúc
không thể cùng lấy suất cuối (G13: suất tính khi SENT).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.offer_lifecycle import PromotionGate
from src.agents.services.operations.opportunity_offers import PromotionCandidate
from src.products.infrastructure.models import PromotionRow, PromotionVehicleRow, VehicleRow


def _gate(row: PromotionRow) -> PromotionGate:
    return PromotionGate(
        status=row.status,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        max_uses=row.max_uses,
        used_count=int(row.used_count or 0),
        advisor_max_discount_vnd=row.advisor_max_discount_vnd,
    )


class SqlAlchemyPromotionCatalog:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        # Ghi đi qua ranh giới transaction chung (chỉ `unit_of_work.py` gọi `begin()`).
        self._unit_of_work: AgentUnitOfWork[AsyncSession] = AgentUnitOfWork(session_factory, lambda session: session)

    async def candidates(self, at: datetime) -> list[PromotionCandidate]:
        """Chỉ ACTIVE trong khung thời gian — UNVERIFIED/DRAFT không bao giờ lọt vào đây."""

        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(PromotionRow).where(
                        PromotionRow.status == "ACTIVE",
                        PromotionRow.valid_from <= at,
                        or_(PromotionRow.valid_to.is_(None), PromotionRow.valid_to >= at),
                    )
                )
            ).all()
            models: dict[str, list[str]] = {}
            if rows:
                for promotion_id, model_name in await session.execute(
                    select(PromotionVehicleRow.promotion_id, VehicleRow.model_name)
                    .join(VehicleRow, VehicleRow.vehicle_id == PromotionVehicleRow.vehicle_id)
                    .where(PromotionVehicleRow.promotion_id.in_([row.promotion_id for row in rows]))
                ):
                    models.setdefault(str(promotion_id), []).append(model_name)
        return [
            PromotionCandidate(
                promotion_code=row.promotion_code,
                title=row.title,
                promotion_type=row.promotion_type,
                discount_amount_vnd=row.discount_amount_vnd,
                discount_percent=float(row.discount_percent) if row.discount_percent is not None else None,
                eligibility_rules=dict(row.eligibility_rules or {}),
                priority=int(row.priority),
                stackable=bool(row.stackable),
                requires_advisor_approval=bool(row.requires_advisor_approval),
                advisor_max_discount_vnd=row.advisor_max_discount_vnd,
                vehicle_models=tuple(sorted(set(models.get(str(row.promotion_id), [])))),
                gate=_gate(row),
            )
            for row in rows
        ]

    async def gate(self, promotion_code: str) -> PromotionGate | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(PromotionRow).where(PromotionRow.promotion_code == promotion_code))
        return None if row is None else _gate(row)

    async def consume_use(self, promotion_code: str) -> bool:
        async with self._unit_of_work.transaction() as session:
            result = await session.execute(
                update(PromotionRow)
                .where(
                    PromotionRow.promotion_code == promotion_code,
                    or_(PromotionRow.max_uses.is_(None), PromotionRow.used_count < PromotionRow.max_uses),
                )
                .values(used_count=PromotionRow.used_count + 1)
            )
        return bool(result.rowcount)


__all__ = ["SqlAlchemyPromotionCatalog"]
