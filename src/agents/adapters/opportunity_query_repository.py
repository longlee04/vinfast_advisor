"""SQLAlchemy queries for qualified sales opportunity projections."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.domain.bottleneck_signal import (
    BottleneckSignalStatus,
    ConfirmedBottleneckEvidence,
    OpportunitySignal,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import (
    ConversationSessionRow,
    ConversationSlotRow,
    ConversationTurnBottleneckRow,
    ConversationTurnOutcomeRow,
)


async def list_opportunities(session: AsyncSession, since: datetime, limit: int) -> tuple[OpportunitySignal, ...]:
    """Return active recent sessions with at least two distinct CORRECT labels."""
    qualified = (
        select(
            ConversationSessionRow.session_id.label("session_id"),
            ConversationSessionRow.customer_id.label("customer_id"),
            ConversationSessionRow.last_activity_at.label("last_active_at"),
            func.max(ConversationTurnBottleneckRow.created_at).label("latest_signal_at"),
            func.count(ConversationTurnBottleneckRow.signal_id).label("signal_count"),
        )
        .join(
            ConversationTurnBottleneckRow,
            ConversationTurnBottleneckRow.session_id == ConversationSessionRow.session_id,
        )
        .where(
            ConversationSessionRow.status == "ACTIVE",
            ConversationSessionRow.last_activity_at >= since,
            ConversationTurnBottleneckRow.status == BottleneckSignalStatus.CORRECT.value,
        )
        .group_by(ConversationSessionRow.session_id)
        .having(func.count(distinct(ConversationTurnBottleneckRow.label)) >= 2)
        .order_by(
            ConversationSessionRow.last_activity_at.desc(),
            ConversationSessionRow.session_id,
        )
        .limit(limit)
        .cte("qualified_opportunities")
    )
    rows = (
        await session.execute(
            select(
                qualified,
                ConversationTurnBottleneckRow,
                ConversationTurnOutcomeRow.turn_number,
            )
            .join(
                ConversationTurnBottleneckRow,
                ConversationTurnBottleneckRow.session_id == qualified.c.session_id,
            )
            .join(
                ConversationTurnOutcomeRow,
                (ConversationTurnOutcomeRow.session_id == ConversationTurnBottleneckRow.session_id)
                & (ConversationTurnOutcomeRow.client_turn_id == ConversationTurnBottleneckRow.client_turn_id),
            )
            .where(ConversationTurnBottleneckRow.status == BottleneckSignalStatus.CORRECT.value)
            .order_by(
                qualified.c.last_active_at.desc(),
                qualified.c.session_id,
                ConversationTurnOutcomeRow.turn_number,
                ConversationTurnBottleneckRow.signal_id,
            )
        )
    ).all()
    grouped: dict[UUID, list[ConfirmedBottleneckEvidence]] = {}
    summaries: dict[UUID, tuple[str, datetime, datetime, int]] = {}
    for row in rows:
        session_id = row.session_id
        grouped.setdefault(session_id, []).append(
            ConfirmedBottleneckEvidence(
                signal_id=row.ConversationTurnBottleneckRow.signal_id,
                client_turn_id=row.ConversationTurnBottleneckRow.client_turn_id,
                turn_number=row.turn_number,
                label=Bottleneck(row.ConversationTurnBottleneckRow.label),
                evidence_quote=row.ConversationTurnBottleneckRow.evidence_quote,
            )
        )
        summaries[session_id] = (
            row.customer_id,
            row.last_active_at,
            row.latest_signal_at,
            row.signal_count,
        )
    return tuple(
        OpportunitySignal(
            session_id=session_id,
            customer_id=summaries[session_id][0],
            labels=frozenset(item.label for item in evidence),
            evidence=tuple(evidence),
            last_active_at=summaries[session_id][1],
            latest_signal_at=summaries[session_id][2],
            correct_signal_count=summaries[session_id][3],
        )
        for session_id, evidence in grouped.items()
    )


async def load_opportunity_slots(
    session: AsyncSession, session_ids: tuple[UUID, ...]
) -> dict[UUID, dict[str, str | Decimal]]:
    """Batch-load typed slot values for opportunity snapshot projection."""
    if not session_ids:
        return {}
    rows = (
        await session.scalars(select(ConversationSlotRow).where(ConversationSlotRow.session_id.in_(session_ids)))
    ).all()
    slots: dict[UUID, dict[str, str | Decimal]] = {session_id: {} for session_id in session_ids}
    for row in rows:
        value = row.slot_value_number if row.slot_value_number is not None else row.slot_value_text
        if value is not None:
            slots[row.session_id][row.slot_name] = value
    return slots
