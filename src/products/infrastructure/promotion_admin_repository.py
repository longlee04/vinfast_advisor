"""SQLAlchemy cho màn quản trị ưu đãi (plan Customer 360 Phase 5C)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.products.infrastructure.models import PromotionRow

_COLUMNS = (
    "promotion_id",
    "promotion_code",
    "title",
    "description",
    "promotion_type",
    "discount_amount_vnd",
    "discount_percent",
    "region_code",
    "eligibility_rules",
    "status",
    "valid_from",
    "valid_to",
    "created_by",
    "approved_by",
    "approved_at",
    "gift_group",
    "stackable",
    "priority",
    "max_uses",
    "used_count",
    "requires_advisor_approval",
    "advisor_max_discount_vnd",
    "source_meta",
    "created_at",
    "updated_at",
)


def _as_dict(row: PromotionRow) -> dict[str, Any]:
    values = {name: getattr(row, name) for name in _COLUMNS}
    if values["discount_percent"] is not None:
        values["discount_percent"] = float(values["discount_percent"])
    return values


class SqlAlchemyPromotionAdminRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, status: str | None) -> list[dict[str, Any]]:
        statement = select(PromotionRow).order_by(PromotionRow.priority, PromotionRow.promotion_code)
        if status:
            statement = statement.where(PromotionRow.status == status)
        async with self._session_factory() as session:
            return [_as_dict(row) for row in (await session.scalars(statement)).all()]

    async def get(self, promotion_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            row = await session.get(PromotionRow, promotion_id)
        return None if row is None else _as_dict(row)

    async def code_exists(self, promotion_code: str) -> bool:
        async with self._session_factory() as session:
            found = await session.scalar(
                select(PromotionRow.promotion_id).where(PromotionRow.promotion_code == promotion_code)
            )
        return found is not None

    async def insert(self, values: Mapping[str, Any]) -> dict[str, Any]:
        async with self._session_factory() as session, session.begin():
            row = PromotionRow(
                promotion_id=str(uuid4()),
                region_code="VN",
                eligibility_rules={},
                **{key: value for key, value in values.items() if key in _COLUMNS},
            )
            session.add(row)
            await session.flush()
            return _as_dict(row)

    async def update(self, promotion_id: str, values: Mapping[str, Any]) -> dict[str, Any] | None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(PromotionRow, promotion_id, with_for_update=True)
            if row is None:
                return None
            for key, value in values.items():
                if key in _COLUMNS:
                    setattr(row, key, value)
            await session.flush()
            return _as_dict(row)


__all__ = ["SqlAlchemyPromotionAdminRepository"]
