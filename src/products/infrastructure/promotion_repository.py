"""SQLAlchemy repository for promotions (read path used by offer suggestion)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from src.products.domain.entities import Promotion
from src.products.domain.values import PromotionType, RecordLifecycleStatus
from src.products.infrastructure.models import PromotionRow


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def _to_promotion(row: PromotionRow) -> Promotion:
    return Promotion(
        promotion_id=row.promotion_id,
        promotion_code=row.promotion_code,
        title=row.title,
        promotion_type=PromotionType(row.promotion_type),
        region_code=row.region_code,
        eligibility_rules=dict(row.eligibility_rules or {}),
        status=RecordLifecycleStatus(row.status),
        valid_from=_utc(row.valid_from),  # type: ignore[arg-type]
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
        description=row.description,
        discount_amount_vnd=row.discount_amount_vnd,
        discount_percent=Decimal(str(row.discount_percent)) if row.discount_percent is not None else None,
        valid_to=_utc(row.valid_to),
        created_by=row.created_by,
        approved_by=row.approved_by,
        approved_at=_utc(row.approved_at),
        gift_group=row.gift_group,
        stackable=bool(row.stackable),
        priority=int(row.priority),
        max_uses=row.max_uses,
        used_count=int(row.used_count or 0),
        requires_advisor_approval=bool(row.requires_advisor_approval),
        advisor_max_discount_vnd=row.advisor_max_discount_vnd,
        source_meta=dict(row.source_meta or {}),
    )


class SqlAlchemyPromotionRepository:
    """Doc promotions ACTIVE trong khung thời gian cho offer suggestion."""

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def list_active(self, at: datetime) -> list[Promotion]:
        """Trả promotions có status=ACTIVE và valid_from <= at <= valid_to."""

        async with self._factory() as session:
            rows = (
                (
                    await session.execute(
                        select(PromotionRow).where(
                            PromotionRow.status == "ACTIVE",
                            PromotionRow.valid_from <= at,
                            (PromotionRow.valid_to.is_(None)) | (PromotionRow.valid_to >= at),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [_to_promotion(r) for r in rows]
