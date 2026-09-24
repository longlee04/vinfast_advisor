"""SQLAlchemy cho Customer 360: cơ hội, gắn phiên, insight, đầu vào độ nóng (plan Phase 4).

Mỗi phương thức mở MỘT transaction ngắn của riêng nó — job nền gọi LLM giữa các bước,
giữ transaction mở suốt một lần gọi mạng là cách chắc nhất để cạn pool (mục 6.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.domain.buyer_for import BuyerFor
from src.agents.domain.customer_insight import CurrentInsight, InsightField
from src.agents.domain.heat_score import HEAT_VERSION, HeatResult
from src.agents.domain.opportunity_attach import (
    CUSTOMER_LEVEL_SLOTS,
    AttachDecision,
    AttachKind,
    OpportunityView,
    merge_slots,
)
from src.agents.domain.sales_stage import SalesStage, StageSignals
from src.agents.domain.values import SlotName
from src.agents.models import (
    ConversationCoreStateRow,
    ConversationMessageRow,
    ConversationSessionRow,
    ConversationSlotRow,
    ConversationTurnOutcomeRow,
    Customer360FeedbackRow,
    CustomerInsightRow,
    CustomerOpportunityRow,
    CustomerProfileRow,
    SessionOpportunityRow,
    TestDriveBookingRow,
    TurnTraceRow,
)
from src.agents.services.operations.customer_360 import (
    Attachment,
    HeatInputs,
    NewInsight,
    SessionContext,
)

_SLOT_KEYS = frozenset(slot.value for slot in SlotName)
#: SĐT Việt Nam trong tin khách — cùng hình với `domain/pii._PHONE`, viết cho Postgres.
_PHONE_REGEX = r"(^|[^0-9+])(\+?84|0)([ .-]?[0-9]){9}([^0-9]|$)"


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _slots_from_rows(rows: Sequence[ConversationSlotRow]) -> dict[str, object]:
    slots: dict[str, object] = {}
    for row in rows:
        value = row.slot_value_number if row.slot_value_number is not None else row.slot_value_text
        if value is not None:
            slots[row.slot_name] = _json_safe(value)
    return slots


class SqlAlchemyCustomer360Repository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        # Ghi đi qua ranh giới transaction chung (chỉ `unit_of_work.py` gọi `begin()`).
        self._unit_of_work: AgentUnitOfWork[AsyncSession] = AgentUnitOfWork(session_factory, lambda session: session)

    # ------------------------------------------------------------ đọc phiên

    async def load_session_context(self, session_id: str) -> SessionContext | None:
        identifier = UUID(session_id)
        async with self._session_factory() as session:
            row = await session.get(ConversationSessionRow, identifier)
            if row is None:
                return None
            core = await session.get(ConversationCoreStateRow, identifier)
            if core is not None and core.slots:
                slots = {key: _json_safe(value) for key, value in core.slots.items() if key in _SLOT_KEYS}
            else:
                slots = _slots_from_rows(
                    (
                        await session.scalars(
                            select(ConversationSlotRow).where(ConversationSlotRow.session_id == identifier)
                        )
                    ).all()
                )
            turns = {
                int(item.turn_index): item.content
                for item in await session.execute(
                    select(ConversationMessageRow.turn_index, ConversationMessageRow.content)
                    .where(ConversationMessageRow.session_id == identifier, ConversationMessageRow.role == "USER")
                    .order_by(ConversationMessageRow.turn_index)
                )
            }
            attached = await session.get(SessionOpportunityRow, identifier)
            attachment = None
            if attached is not None:
                siblings = 0
                if attached.opportunity_id is not None:
                    siblings = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(SessionOpportunityRow)
                            .where(SessionOpportunityRow.opportunity_id == attached.opportunity_id)
                        )
                        or 0
                    )
                attachment = Attachment(
                    opportunity_id=str(attached.opportunity_id) if attached.opportunity_id else None,
                    kind=attached.kind,
                    decided_by=attached.decided_by,
                    extracted_through_turn=int(attached.extracted_through_turn),
                    extraction_count=int(attached.extraction_count),
                    opportunity_session_count=siblings,
                )
        return SessionContext(
            session_id=session_id,
            customer_id=row.customer_id,
            slots=slots,
            user_turns=turns,
            turn_count=int(core.turn_count) if core is not None else len(turns),
            last_activity_at=row.last_activity_at,
            attachment=attachment,
        )

    async def list_open_opportunities(self, customer_id: str) -> list[OpportunityView]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(CustomerOpportunityRow).where(
                        CustomerOpportunityRow.customer_id == customer_id,
                        CustomerOpportunityRow.status.in_(("OPEN", "DORMANT")),
                    )
                )
            ).all()
        return [
            OpportunityView(
                opportunity_id=str(row.opportunity_id),
                vehicle_type=row.vehicle_type,
                buyer_for=BuyerFor(row.buyer_for),
                slots=dict(row.slots_snapshot or {}),
                status=row.status,
                last_seen_at=row.last_seen_at,
            )
            for row in rows
        ]

    # ------------------------------------------------------------ ghi gắn phiên

    async def apply_attachment(
        self, context: SessionContext, decision: AttachDecision, buyer_for: BuyerFor, at: datetime
    ) -> str | None:
        session_uuid = UUID(context.session_id)
        async with self._unit_of_work.transaction() as session:
            opportunity_id: UUID | None = None
            if decision.kind is AttachKind.NEW:
                opportunity_id = uuid4()
                snapshot, _history = merge_slots({}, decision.changes, session_id=context.session_id, at=at)
                session.add(
                    CustomerOpportunityRow(
                        opportunity_id=opportunity_id,
                        customer_id=context.customer_id,
                        vehicle_type=_vehicle_type(context.slots),
                        buyer_for=buyer_for.value,
                        status="OPEN",
                        slots_snapshot=snapshot,
                        slot_history=[],
                        first_seen_at=context.last_activity_at,
                        last_seen_at=context.last_activity_at,
                    )
                )
                await session.flush()
            elif decision.kind in {AttachKind.UPDATE, AttachKind.SAME} and decision.target_id:
                opportunity_id = UUID(decision.target_id)
                target = await session.get(CustomerOpportunityRow, opportunity_id, with_for_update=True)
                if target is None:
                    return None
                snapshot, history = merge_slots(
                    target.slots_snapshot or {}, decision.changes, session_id=context.session_id, at=at
                )
                target.slots_snapshot = snapshot
                target.slot_history = [*(target.slot_history or []), *history]
                target.vehicle_type = target.vehicle_type or _vehicle_type(context.slots)
                target.last_seen_at = max(target.last_seen_at, context.last_activity_at)
                if target.status == "DORMANT":
                    target.status = "OPEN"
            statement = insert(SessionOpportunityRow).values(
                session_id=session_uuid,
                opportunity_id=opportunity_id,
                kind="SUPPORT" if decision.kind is AttachKind.SUPPORT else "SALES",
                decided_by=decision.decided_by.value,
                rule_code=decision.rule_code,
                confidence=decision.confidence,
                needs_review=decision.needs_review,
                evaluated_through_turn=context.turn_count,
                decided_at=at,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SessionOpportunityRow.session_id],
                    set_={
                        "opportunity_id": statement.excluded.opportunity_id,
                        "kind": statement.excluded.kind,
                        "decided_by": statement.excluded.decided_by,
                        "decided_by_actor": None,
                        "rule_code": statement.excluded.rule_code,
                        "confidence": statement.excluded.confidence,
                        "needs_review": statement.excluded.needs_review,
                        "evaluated_through_turn": statement.excluded.evaluated_through_turn,
                        "decided_at": statement.excluded.decided_at,
                    },
                    # Không bao giờ ghi đè quyết định của TVV.
                    where=SessionOpportunityRow.decided_by != "ADVISOR",
                )
            )
        return str(opportunity_id) if opportunity_id is not None else None

    # ------------------------------------------------------------ insight

    async def current_insights(self, customer_id: str) -> list[CurrentInsight]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(CustomerInsightRow).where(
                        CustomerInsightRow.customer_id == customer_id, CustomerInsightRow.superseded_by.is_(None)
                    )
                )
            ).all()
        return [
            CurrentInsight(
                insight_id=str(row.insight_id),
                field=InsightField(row.field),
                opportunity_id=str(row.opportunity_id) if row.opportunity_id else None,
                value=row.value,
                value_code=row.value_code,
            )
            for row in rows
        ]

    async def save_insights(
        self,
        context: SessionContext,
        rows: Sequence[NewInsight],
        *,
        extracted_through_turn: int | None,
        model_name: str | None,
        prompt_version: str | None,
        at: datetime,
    ) -> int:
        saved = 0
        async with self._unit_of_work.transaction() as session:
            for item in rows:
                insight_id = uuid4()
                statement = (
                    insert(CustomerInsightRow)
                    .values(
                        insight_id=insight_id,
                        customer_id=context.customer_id,
                        opportunity_id=UUID(item.opportunity_id) if item.opportunity_id else None,
                        session_id=UUID(context.session_id),
                        field=item.field.value,
                        value=item.value[:120],
                        value_code=item.value_code,
                        evidence_quote=item.evidence_quote,
                        turn_index=item.turn_index,
                        confidence=item.confidence,
                        source=item.source.value,
                        model_name=model_name,
                        prompt_version=prompt_version,
                        extracted_at=at,
                    )
                    .on_conflict_do_nothing(constraint="uq_customer_insights_turn_field_value")
                    .returning(CustomerInsightRow.insight_id)
                )
                inserted = (await session.execute(statement)).scalar_one_or_none()
                if inserted is None:
                    continue
                saved += 1
                if item.supersedes:
                    await session.execute(
                        update(CustomerInsightRow)
                        .where(
                            CustomerInsightRow.insight_id == UUID(item.supersedes),
                            CustomerInsightRow.superseded_by.is_(None),
                        )
                        .values(superseded_by=insight_id)
                    )
            if extracted_through_turn is not None:
                await session.execute(
                    update(SessionOpportunityRow)
                    .where(SessionOpportunityRow.session_id == UUID(context.session_id))
                    .values(
                        extracted_through_turn=func.greatest(
                            SessionOpportunityRow.extracted_through_turn, extracted_through_turn
                        ),
                        extraction_count=SessionOpportunityRow.extraction_count + 1,
                    )
                )
        return saved

    # ------------------------------------------------------------ độ nóng

    async def load_heat_inputs(self, opportunity_id: str, now: datetime) -> HeatInputs | None:
        identifier = UUID(opportunity_id)
        async with self._session_factory() as session:
            opportunity = await session.get(CustomerOpportunityRow, identifier)
            if opportunity is None:
                return None
            session_ids = (
                await session.scalars(
                    select(SessionOpportunityRow.session_id).where(SessionOpportunityRow.opportunity_id == identifier)
                )
            ).all()
            sessions = (
                (
                    await session.scalars(
                        select(ConversationSessionRow).where(ConversationSessionRow.session_id.in_(session_ids))
                    )
                ).all()
                if session_ids
                else []
            )
            cores = (
                (
                    await session.scalars(
                        select(ConversationCoreStateRow).where(ConversationCoreStateRow.session_id.in_(session_ids))
                    )
                ).all()
                if session_ids
                else []
            )
            trace_stages = (
                set(
                    (
                        await session.scalars(
                            select(TurnTraceRow.payload["stage_after"].astext)
                            .where(TurnTraceRow.session_id.in_(session_ids))
                            .distinct()
                        )
                    ).all()
                )
                if session_ids
                else set()
            )
            has_recommendations = bool(
                session_ids
                and await session.scalar(
                    select(
                        exists().where(
                            ConversationTurnOutcomeRow.session_id.in_(session_ids),
                            func.jsonb_array_length(ConversationTurnOutcomeRow.recommendations) > 0,
                        )
                    )
                )
            )
            has_test_drive = bool(
                await session.scalar(
                    select(
                        exists().where(
                            TestDriveBookingRow.customer_id == opportunity.customer_id,
                            TestDriveBookingRow.status.in_(("REQUESTED", "CONFIRMED")),
                        )
                    )
                )
            )
            profile_phone = await session.scalar(
                select(CustomerProfileRow.phone).where(CustomerProfileRow.customer_id == opportunity.customer_id)
            )
            phone_in_chat = bool(
                session_ids
                and await session.scalar(
                    select(
                        exists().where(
                            ConversationMessageRow.session_id.in_(session_ids),
                            ConversationMessageRow.role == "USER",
                            ConversationMessageRow.content.op("~")(_PHONE_REGEX),
                        )
                    )
                )
            )
            insights = (
                await session.execute(
                    select(
                        CustomerInsightRow.field, CustomerInsightRow.value_code, CustomerInsightRow.opportunity_id
                    ).where(
                        CustomerInsightRow.customer_id == opportunity.customer_id,
                        CustomerInsightRow.superseded_by.is_(None),
                        CustomerInsightRow.field.in_(("purchase_timeframe", "payment_method")),
                    )
                )
            ).all()
        ask_counts: dict[str, int] = {}
        for core in cores:
            for slot, count in (core.ask_counts or {}).items():
                ask_counts[slot] = max(ask_counts.get(slot, 0), int(count))
        timeframe = next(
            (
                row.value_code
                for row in insights
                if row.field == "purchase_timeframe" and row.opportunity_id in (identifier, None)
            ),
            None,
        )
        return HeatInputs(
            customer_id=opportunity.customer_id,
            status=opportunity.status,
            current_stage=SalesStage(opportunity.stage),
            stage_signals=StageSignals(
                core_stages=frozenset({core.stage for core in cores} | {stage for stage in trace_stages if stage}),
                has_recommendations=has_recommendations,
                quote_sent=any(row.last_quote_sent_at is not None for row in sessions),
                has_test_drive=has_test_drive,
                won=opportunity.status == "WON",
            ),
            vehicle_type=opportunity.vehicle_type,
            slots=dict(opportunity.slots_snapshot or {}),
            ask_counts=ask_counts,
            purchase_timeframe=timeframe,
            has_phone=bool(profile_phone) or phone_in_chat,
            human_requested=any(row.ownership in {"PENDING_HANDOFF", "HUMAN"} for row in sessions)
            or "HANDED_OFF" in trace_stages,
            sessions_14d=sum(1 for row in sessions if row.last_activity_at >= now - timedelta(days=14)),
            payment_asked=any(row.field == "payment_method" for row in insights),
            last_seen_at=opportunity.last_seen_at,
        )

    async def save_scores(self, opportunity_id: str, stage: SalesStage, heat: HeatResult, at: datetime) -> None:
        async with self._unit_of_work.transaction() as session:
            await session.execute(
                update(CustomerOpportunityRow)
                .where(CustomerOpportunityRow.opportunity_id == UUID(opportunity_id))
                .values(
                    stage=stage.value,
                    heat_score=heat.score,
                    heat_band=heat.band.value,
                    heat_breakdown=[
                        {"code": part.code, "points": part.points, "detail": part.detail} for part in heat.breakdown
                    ],
                    heat_version=HEAT_VERSION,
                    computed_at=at,
                )
            )

    # ------------------------------------------------------------ việc định kỳ

    async def mark_dormant(self, before: datetime) -> int:
        async with self._unit_of_work.transaction() as session:
            result = await session.execute(
                update(CustomerOpportunityRow)
                .where(CustomerOpportunityRow.status == "OPEN", CustomerOpportunityRow.last_seen_at < before)
                .values(status="DORMANT")
            )
        return int(result.rowcount or 0)

    async def sessions_to_refresh(self, idle_before: datetime, active_after: datetime, limit: int) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ConversationSessionRow.session_id)
                .outerjoin(SessionOpportunityRow, SessionOpportunityRow.session_id == ConversationSessionRow.session_id)
                .outerjoin(
                    ConversationCoreStateRow, ConversationCoreStateRow.session_id == ConversationSessionRow.session_id
                )
                .where(
                    ConversationSessionRow.last_activity_at < idle_before,
                    ConversationSessionRow.last_activity_at >= active_after,
                    or_(
                        SessionOpportunityRow.session_id.is_(None),
                        and_(
                            SessionOpportunityRow.decided_by != "ADVISOR",
                            SessionOpportunityRow.evaluated_through_turn
                            < func.coalesce(ConversationCoreStateRow.turn_count, 0),
                        ),
                    ),
                )
                .order_by(ConversationSessionRow.last_activity_at.desc())
                .limit(limit)
            )
        return [str(item) for item in rows]

    async def open_opportunity_ids(self, limit: int) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(CustomerOpportunityRow.opportunity_id)
                .where(CustomerOpportunityRow.status == "OPEN")
                .order_by(CustomerOpportunityRow.computed_at.asc().nulls_first())
                .limit(limit)
            )
        return [str(item) for item in rows]

    # ------------------------------------------------------------ TVV sửa máy

    async def move_session(
        self, session_id: str, target_opportunity_id: str | None, actor: str, at: datetime
    ) -> tuple[str, str | None, str] | None:
        identifier = UUID(session_id)
        async with self._unit_of_work.transaction() as session:
            row = await session.get(ConversationSessionRow, identifier)
            if row is None:
                return None
            attached = await session.get(SessionOpportunityRow, identifier, with_for_update=True)
            previous = attached.opportunity_id if attached is not None else None
            previous_decider = attached.decided_by if attached is not None else None
            if target_opportunity_id is None:
                source = await session.get(CustomerOpportunityRow, previous) if previous else None
                target = CustomerOpportunityRow(
                    opportunity_id=uuid4(),
                    customer_id=row.customer_id,
                    vehicle_type=source.vehicle_type if source else None,
                    buyer_for=source.buyer_for if source else "SELF",
                    status="OPEN",
                    slots_snapshot=dict(source.slots_snapshot or {}) if source else {},
                    slot_history=[],
                    first_seen_at=row.started_at,
                    last_seen_at=row.last_activity_at,
                )
                session.add(target)
                await session.flush()
                target_id = target.opportunity_id
            else:
                target_row = await session.get(CustomerOpportunityRow, UUID(target_opportunity_id))
                if target_row is None or target_row.customer_id != row.customer_id:
                    return None
                target_row.last_seen_at = max(target_row.last_seen_at, row.last_activity_at)
                if target_row.status == "DORMANT":
                    target_row.status = "OPEN"
                target_id = target_row.opportunity_id
            statement = insert(SessionOpportunityRow).values(
                session_id=identifier,
                opportunity_id=target_id,
                kind="SALES",
                decided_by="ADVISOR",
                decided_by_actor=actor,
                confidence=1.0,
                needs_review=False,
                decided_at=at,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SessionOpportunityRow.session_id],
                    set_={
                        "opportunity_id": target_id,
                        "kind": "SALES",
                        "decided_by": "ADVISOR",
                        "decided_by_actor": actor,
                        "confidence": 1.0,
                        "needs_review": False,
                        "decided_at": at,
                    },
                )
            )
            session.add(
                Customer360FeedbackRow(
                    feedback_id=uuid4(),
                    kind="SESSION_SPLIT" if target_opportunity_id is None else "SESSION_MOVED",
                    customer_id=row.customer_id,
                    session_id=identifier,
                    from_opportunity_id=previous,
                    to_opportunity_id=target_id,
                    previous_decided_by=previous_decider,
                    actor=actor,
                    created_at=at,
                )
            )
        return row.customer_id, str(previous) if previous else None, str(target_id)

    async def record_insight_feedback(
        self, insight_id: str, verdict: str, actor: str, note: str | None, at: datetime
    ) -> bool:
        async with self._unit_of_work.transaction() as session:
            insight = await session.get(CustomerInsightRow, UUID(insight_id))
            if insight is None:
                return False
            session.add(
                Customer360FeedbackRow(
                    feedback_id=uuid4(),
                    kind="INSIGHT_WRONG" if verdict == "WRONG" else "INSIGHT_OK",
                    customer_id=insight.customer_id,
                    session_id=insight.session_id,
                    insight_id=insight.insight_id,
                    from_opportunity_id=insight.opportunity_id,
                    field=insight.field,
                    actor=actor,
                    note=note,
                    created_at=at,
                )
            )
        return True

    # ------------------------------------------------------------ danh tính (4F)

    async def profile_needs_identity(self, customer_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(CustomerProfileRow, customer_id)
        return row is None or not row.display_name or not row.phone or not row.address

    async def upsert_profile_identity(
        self,
        customer_id: str,
        display_name: str | None,
        phone: str | None,
        at: datetime,
        *,
        address: str | None = None,
        email: str | None = None,
        overwrite: bool = False,
    ) -> None:
        """Ghi tên/SĐT/địa chỉ/email khách.

        `overwrite=False` (job nền): chỉ lấp chỗ trống. `overwrite=True` (khách vừa tự lưu
        hồ sơ): bản khách khai là bản đúng — đè giá trị cũ, nhưng không xoá ô khách để trống.
        """

        async with self._unit_of_work.transaction() as session:
            statement = insert(CustomerProfileRow).values(
                customer_id=customer_id,
                display_name=display_name,
                phone=phone,
                address=address,
                email=email,
                created_at=at,
                updated_at=at,
            )
            new, old = statement.excluded, CustomerProfileRow
            pick = (
                (lambda column: func.coalesce(getattr(new, column), getattr(old, column)))
                if overwrite
                else (lambda column: func.coalesce(getattr(old, column), getattr(new, column)))
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[CustomerProfileRow.customer_id],
                    set_={
                        "display_name": pick("display_name"),
                        "phone": pick("phone"),
                        "address": pick("address"),
                        "email": pick("email"),
                        "updated_at": at,
                    },
                )
            )


def _vehicle_type(slots: dict[str, object] | object) -> str | None:
    value = (
        slots.get("vehicle_type") if isinstance(slots, dict) else getattr(slots, "get", lambda _k: None)("vehicle_type")
    )
    return str(value) if value in {"CAR", "ELECTRIC_MOTORBIKE"} else None


__all__ = ["CUSTOMER_LEVEL_SLOTS", "SqlAlchemyCustomer360Repository"]
