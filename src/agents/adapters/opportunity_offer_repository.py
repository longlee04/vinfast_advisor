"""SQLAlchemy cho vòng đời ưu đãi theo cơ hội (agent_0039, plan Customer 360 Phase 5B)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.offer_lifecycle import LIVE_STATUSES, OfferStatus
from src.agents.models import (
    ConversationSessionRow,
    CustomerInsightRow,
    CustomerOpportunityRow,
    OpportunityOfferEventRow,
    OpportunityOfferRow,
    SessionOfferRow,
)
from src.agents.services.operations.opportunity_offers import OfferView, PromotionCandidate

#: Ưu đãi đã gửi còn hiệu lực bao lâu trong phiên (cùng quy ước OFFER_TTL_DAYS của nút thắt).
SENT_OFFER_TTL = timedelta(days=7)
#: Insight tầng Khách → field DSL (`products.domain.eligibility_rules.FIELD_TYPES`).
_INSIGHT_FIELDS = {
    "payment_method": "payment_method",
    "trade_in": "trade_in",
    "customer_group": "customer_group",
    "purchase_timeframe": "purchase_timeframe",
    "current_vehicle": "current_vehicle_brand",
}


def _view(row: OpportunityOfferRow) -> OfferView:
    return OfferView(
        offer_id=str(row.offer_id),
        opportunity_id=str(row.opportunity_id),
        customer_id=row.customer_id,
        promotion_code=row.promotion_code,
        status=OfferStatus(row.status),
        discount_vnd=row.discount_vnd,
        needs_manager_approval=bool(row.needs_manager_approval),
        proposed_value=dict(row.proposed_value or {}),
    )


class SqlAlchemyOpportunityOfferRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        # Ghi đi qua ranh giới transaction chung (chỉ `unit_of_work.py` gọi `begin()`).
        self._unit_of_work: AgentUnitOfWork[AsyncSession] = AgentUnitOfWork(session_factory, lambda session: session)

    async def opportunity_context(self, opportunity_id: str) -> tuple[str, dict[str, Any]] | None:
        """Ngữ cảnh đánh giá luật: slot của cơ hội + điều khách đã NÓI (insight hiện hành)."""

        async with self._session_factory() as session:
            opportunity = await session.get(CustomerOpportunityRow, UUID(opportunity_id))
            if opportunity is None:
                return None
            insights = (
                await session.execute(
                    select(CustomerInsightRow.field, CustomerInsightRow.value, CustomerInsightRow.value_code).where(
                        CustomerInsightRow.customer_id == opportunity.customer_id,
                        CustomerInsightRow.superseded_by.is_(None),
                        (CustomerInsightRow.opportunity_id.is_(None))
                        | (CustomerInsightRow.opportunity_id == opportunity.opportunity_id),
                    )
                )
            ).all()
        context: dict[str, Any] = dict(opportunity.slots_snapshot or {})
        if opportunity.vehicle_type:
            context["vehicle_type"] = opportunity.vehicle_type
        if context.get("interest_vehicle"):
            context["vehicle_model"] = context["interest_vehicle"]
        for field, value, value_code in insights:
            target = _INSIGHT_FIELDS.get(field)
            if target is not None:
                context[target] = value_code or value
            elif field in {"registration_province", "home_charging"} and field not in context:
                context[field] = value_code or value
        return opportunity.customer_id, context

    async def create(
        self,
        *,
        opportunity_id: str,
        customer_id: str,
        candidate: PromotionCandidate,
        eligibility: str,
        reasons: Sequence[str],
        status: OfferStatus,
        proposed_value: Mapping[str, Any],
        discount_vnd: int | None,
        needs_manager: bool,
        actor: str,
        at: datetime,
    ) -> OfferView:
        async with self._unit_of_work.transaction() as session:
            row = OpportunityOfferRow(
                offer_id=uuid4(),
                opportunity_id=UUID(opportunity_id),
                customer_id=customer_id,
                promotion_code=candidate.promotion_code,
                eligibility=eligibility,
                eligibility_reasons=list(reasons),
                status=status.value,
                proposed_value=dict(proposed_value),
                discount_vnd=discount_vnd,
                needs_manager_approval=needs_manager,
                suggested_by=actor,
                approved_by=actor if status is OfferStatus.APPROVED else None,
                approved_at=at if status is OfferStatus.APPROVED else None,
                expires_at=candidate.gate.valid_to,
                created_at=at,
                updated_at=at,
            )
            session.add(row)
            await session.flush()
            session.add(
                OpportunityOfferEventRow(
                    event_id=uuid4(),
                    offer_id=row.offer_id,
                    promotion_code=row.promotion_code,
                    from_status=None,
                    to_status=status.value,
                    actor=actor,
                    meta={"discount_vnd": discount_vnd, "needs_manager": needs_manager},
                    created_at=at,
                )
            )
        return _view(row)

    async def get(self, offer_id: str) -> OfferView | None:
        async with self._session_factory() as session:
            row = await session.get(OpportunityOfferRow, UUID(offer_id))
        return None if row is None else _view(row)

    async def transition(
        self,
        offer_id: str,
        current: OfferStatus,
        target: OfferStatus,
        actor: str,
        at: datetime,
        meta: Mapping[str, Any],
    ) -> OfferView | None:
        """Đổi trạng thái có điều kiện (`WHERE status = current`) — hai người bấm cùng lúc chỉ một thắng."""

        async with self._unit_of_work.transaction() as session:
            row = await session.get(OpportunityOfferRow, UUID(offer_id), with_for_update=True)
            if row is None or row.status != current.value:
                return None
            row.status = target.value
            row.updated_at = at
            if target is OfferStatus.APPROVED:
                row.approved_by = str(meta.get("approved_by") or actor)
                row.approved_at = at
            if target is OfferStatus.SENT:
                row.sent_at = at
                if meta.get("session_offer_id"):
                    row.session_offer_id = UUID(str(meta["session_offer_id"]))
            session.add(
                OpportunityOfferEventRow(
                    event_id=uuid4(),
                    offer_id=row.offer_id,
                    promotion_code=row.promotion_code,
                    from_status=current.value,
                    to_status=target.value,
                    actor=actor,
                    meta=dict(meta),
                    created_at=at,
                )
            )
        return _view(row)

    async def deliver(self, offer: OfferView, candidate_title: str, actor: str, at: datetime) -> str | None:
        """Ghi `session_offers` vào phiên đang mở gần nhất của khách — agent từ đây mới được nhắc."""

        async with self._unit_of_work.transaction() as session:
            session_id = await session.scalar(
                select(ConversationSessionRow.session_id)
                .where(
                    ConversationSessionRow.customer_id == offer.customer_id,
                    ConversationSessionRow.status == "ACTIVE",
                    ConversationSessionRow.archived_at.is_(None),
                )
                .order_by(ConversationSessionRow.last_activity_at.desc())
                .limit(1)
            )
            if session_id is None:
                return None
            snapshot = {"display_name": candidate_title, **dict(offer.proposed_value)}
            if offer.discount_vnd is not None and "amount_vnd" not in snapshot:
                snapshot["amount_vnd"] = offer.discount_vnd
            row = SessionOfferRow(
                offer_id=uuid4(),
                session_id=session_id,
                source_kind="OPPORTUNITY_OFFER",
                promotion_code=offer.promotion_code,
                value_snapshot=snapshot,
                status="ACTIVE",
                approved_by=actor,
                expires_at=at + SENT_OFFER_TTL,
                opportunity_offer_id=UUID(offer.offer_id),
                created_at=at,
                updated_at=at,
            )
            session.add(row)
        return str(row.offer_id)

    async def list_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(OpportunityOfferRow)
                    .where(OpportunityOfferRow.customer_id == customer_id)
                    .order_by(OpportunityOfferRow.updated_at.desc())
                )
            ).all()
        return [
            {
                "offer_id": str(row.offer_id),
                "opportunity_id": str(row.opportunity_id),
                "promotion_code": row.promotion_code,
                "status": row.status,
                "discount_vnd": row.discount_vnd,
                "needs_manager_approval": bool(row.needs_manager_approval),
                "eligibility": row.eligibility,
                "suggested_by": row.suggested_by,
                "approved_by": row.approved_by,
                "sent_at": row.sent_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]

    async def expire_due(self, at: datetime) -> int:
        live = [status.value for status in LIVE_STATUSES]
        async with self._unit_of_work.transaction() as session:
            due = (
                await session.scalars(
                    select(OpportunityOfferRow).where(
                        OpportunityOfferRow.status.in_(live), OpportunityOfferRow.expires_at < at
                    )
                )
            ).all()
            for row in due:
                session.add(
                    OpportunityOfferEventRow(
                        event_id=uuid4(),
                        offer_id=row.offer_id,
                        promotion_code=row.promotion_code,
                        from_status=row.status,
                        to_status=OfferStatus.EXPIRED.value,
                        actor="SYSTEM",
                        meta={},
                        created_at=at,
                    )
                )
                row.status = OfferStatus.EXPIRED.value
                row.updated_at = at
            if due:
                await session.execute(
                    update(SessionOfferRow)
                    .where(SessionOfferRow.opportunity_offer_id.in_([row.offer_id for row in due]))
                    .values(status="EXPIRED", updated_at=at)
                )
        return len(due)

    async def stats(self, promotion_code: str | None) -> list[dict[str, Any]]:
        """Số ưu đãi đã từng tới mỗi trạng thái — đo hiệu quả (plan §2.4)."""

        statement = select(
            OpportunityOfferEventRow.promotion_code,
            OpportunityOfferEventRow.to_status,
            func.count(func.distinct(OpportunityOfferEventRow.offer_id)),
        ).group_by(OpportunityOfferEventRow.promotion_code, OpportunityOfferEventRow.to_status)
        if promotion_code:
            statement = statement.where(OpportunityOfferEventRow.promotion_code == promotion_code)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        grouped: dict[str, dict[str, Any]] = {}
        for code, status, count in rows:
            grouped.setdefault(code, {"promotion_code": code})[status.lower()] = int(count)
        result = []
        for code, item in grouped.items():
            sent = item.get("sent", 0)
            item["conversion_rate"] = round(item.get("converted", 0) / sent, 3) if sent else 0.0
            result.append(item)
        return sorted(result, key=lambda item: item["promotion_code"])


__all__ = ["SqlAlchemyOpportunityOfferRepository"]
