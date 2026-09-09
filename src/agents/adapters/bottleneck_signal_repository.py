"""SQLAlchemy adapter for anchored bottleneck signals and advisor CAS workflow."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.opportunity_query_repository import (
    list_opportunities as query_opportunities,
)
from src.agents.adapters.opportunity_query_repository import (
    load_opportunity_slots as query_opportunity_slots,
)
from src.agents.domain.bottleneck_signal import (
    BottleneckSignal,
    BottleneckSignalStatus,
    ConfirmedBottleneckEvidence,
    OpportunitySignal,
    SignalClaimDeniedError,
    SignalInsert,
    SignalNotFoundError,
    SignalVerdict,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.models import ConversationTurnBottleneckRow, ConversationTurnOutcomeRow
from src.agents.ports import ClockPort


@dataclass(frozen=True, slots=True)
class SqlAlchemyBottleneckSignalRepository:
    """Query anchors, persist signals, and enforce lease/verdict CAS."""

    session: AsyncSession
    clock: ClockPort

    async def latest_recommendation_anchor(self, session_id: UUID, current_client_turn_id: UUID) -> UUID | None:
        """Return latest earlier completed turn containing recommendations."""
        current_turn = await self.session.scalar(
            select(ConversationTurnOutcomeRow.turn_number).where(
                ConversationTurnOutcomeRow.session_id == session_id,
                ConversationTurnOutcomeRow.client_turn_id == current_client_turn_id,
            )
        )
        if current_turn is None:
            return None
        return await self.session.scalar(
            select(ConversationTurnOutcomeRow.client_turn_id)
            .where(
                ConversationTurnOutcomeRow.session_id == session_id,
                ConversationTurnOutcomeRow.turn_number < current_turn,
                ConversationTurnOutcomeRow.status == "COMPLETED",
                func.jsonb_array_length(ConversationTurnOutcomeRow.recommendations) > 0,
            )
            .order_by(ConversationTurnOutcomeRow.turn_number.desc())
            .limit(1)
        )

    async def confirmed_evidence(
        self, session_id: UUID, anchor_client_turn_id: UUID
    ) -> tuple[ConfirmedBottleneckEvidence, ...]:
        """Project CORRECT evidence in stable customer-turn order."""
        rows = (
            await self.session.execute(
                select(ConversationTurnBottleneckRow, ConversationTurnOutcomeRow.turn_number)
                .join(
                    ConversationTurnOutcomeRow,
                    (ConversationTurnOutcomeRow.session_id == ConversationTurnBottleneckRow.session_id)
                    & (ConversationTurnOutcomeRow.client_turn_id == ConversationTurnBottleneckRow.client_turn_id),
                )
                .where(
                    ConversationTurnBottleneckRow.session_id == session_id,
                    ConversationTurnBottleneckRow.anchor_client_turn_id == anchor_client_turn_id,
                    ConversationTurnBottleneckRow.status == BottleneckSignalStatus.CORRECT.value,
                )
                .order_by(ConversationTurnOutcomeRow.turn_number, ConversationTurnBottleneckRow.signal_id)
            )
        ).all()
        return tuple(
            ConfirmedBottleneckEvidence(
                signal_id=row.signal_id,
                client_turn_id=row.client_turn_id,
                turn_number=turn_number,
                label=Bottleneck(row.label),
                evidence_quote=row.evidence_quote,
            )
            for row, turn_number in rows
        )

    async def confirmed_evidence_for_session(self, session_id: UUID) -> tuple[ConfirmedBottleneckEvidence, ...]:
        """Project every CORRECT signal for live review detail."""
        rows = (
            await self.session.execute(
                select(ConversationTurnBottleneckRow, ConversationTurnOutcomeRow.turn_number)
                .join(
                    ConversationTurnOutcomeRow,
                    (ConversationTurnOutcomeRow.session_id == ConversationTurnBottleneckRow.session_id)
                    & (ConversationTurnOutcomeRow.client_turn_id == ConversationTurnBottleneckRow.client_turn_id),
                )
                .where(
                    ConversationTurnBottleneckRow.session_id == session_id,
                    ConversationTurnBottleneckRow.status == BottleneckSignalStatus.CORRECT.value,
                )
                .order_by(ConversationTurnOutcomeRow.turn_number, ConversationTurnBottleneckRow.signal_id)
            )
        ).all()
        return tuple(
            ConfirmedBottleneckEvidence(
                signal_id=row.signal_id,
                client_turn_id=row.client_turn_id,
                turn_number=turn_number,
                label=Bottleneck(row.label),
                evidence_quote=row.evidence_quote,
            )
            for row, turn_number in rows
        )

    async def insert(self, signal: SignalInsert) -> BottleneckSignal:
        """Insert one signal per current turn, returning existing row on replay."""
        now = self.clock.now()
        statement = (
            pg_insert(ConversationTurnBottleneckRow)
            .values(
                signal_id=uuid4(),
                session_id=signal.session_id,
                client_turn_id=signal.client_turn_id,
                anchor_client_turn_id=signal.anchor_client_turn_id,
                label=signal.label.value,
                evidence_quote=signal.evidence_quote,
                model_name=signal.model_name,
                prompt_version=signal.prompt_version,
                status=BottleneckSignalStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["session_id", "client_turn_id"])
        )
        await self.session.execute(statement)
        row = await self.session.scalar(
            select(ConversationTurnBottleneckRow).where(
                ConversationTurnBottleneckRow.session_id == signal.session_id,
                ConversationTurnBottleneckRow.client_turn_id == signal.client_turn_id,
            )
        )
        if row is None:
            raise SignalNotFoundError(signal.client_turn_id)
        return _signal(row)

    async def list_pending(self) -> tuple[BottleneckSignal, ...]:
        return await self.list_by_status(BottleneckSignalStatus.PENDING, limit=100, offset=0)

    async def list_by_status(
        self, signal_status: BottleneckSignalStatus, *, limit: int, offset: int
    ) -> tuple[BottleneckSignal, ...]:
        """List one status in stable queue order with bounded caller pagination."""
        rows = (
            await self.session.scalars(
                select(ConversationTurnBottleneckRow)
                .where(ConversationTurnBottleneckRow.status == signal_status.value)
                .order_by(ConversationTurnBottleneckRow.created_at, ConversationTurnBottleneckRow.signal_id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return tuple(_signal(row) for row in rows)

    async def get(self, signal_id: UUID) -> BottleneckSignal:
        row = await self.session.get(ConversationTurnBottleneckRow, signal_id)
        if row is None:
            raise SignalNotFoundError(signal_id)
        return _signal(row)

    async def claim(self, signal_id: UUID, advisor_id: str, lease_minutes: int = 15) -> bool:
        now = self.clock.now()
        result = await self.session.execute(
            update(ConversationTurnBottleneckRow)
            .where(
                ConversationTurnBottleneckRow.signal_id == signal_id,
                ConversationTurnBottleneckRow.status == BottleneckSignalStatus.PENDING.value,
                (ConversationTurnBottleneckRow.claimed_by.is_(None))
                | (ConversationTurnBottleneckRow.lease_expires_at <= now),
            )
            .values(
                claimed_by=advisor_id,
                claimed_at=now,
                lease_expires_at=now + timedelta(minutes=lease_minutes),
                updated_at=now,
            )
        )
        return isinstance(result, CursorResult) and result.rowcount == 1

    async def decide(self, signal_id: UUID, advisor_id: str, verdict: SignalVerdict) -> BottleneckSignal:
        now = self.clock.now()
        result = await self.session.execute(
            update(ConversationTurnBottleneckRow)
            .where(
                ConversationTurnBottleneckRow.signal_id == signal_id,
                ConversationTurnBottleneckRow.status == BottleneckSignalStatus.PENDING.value,
                ConversationTurnBottleneckRow.claimed_by == advisor_id,
                ConversationTurnBottleneckRow.lease_expires_at > now,
            )
            .values(status=verdict.value, advisor_id=advisor_id, decided_at=now, updated_at=now)
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise SignalClaimDeniedError(signal_id, advisor_id)
        return await self.get(signal_id)

    async def list_opportunities(self, since: datetime, limit: int) -> tuple[OpportunitySignal, ...]:
        """Return active recent sessions with at least two distinct CORRECT labels."""
        return await query_opportunities(self.session, since, limit)

    async def load_opportunity_slots(self, session_ids: tuple[UUID, ...]) -> dict[UUID, dict[str, str | Decimal]]:
        """Batch-load typed slot values for opportunity snapshot projection."""
        return await query_opportunity_slots(self.session, session_ids)


def _signal(row: ConversationTurnBottleneckRow) -> BottleneckSignal:
    return BottleneckSignal(
        signal_id=row.signal_id,
        session_id=row.session_id,
        client_turn_id=row.client_turn_id,
        anchor_client_turn_id=row.anchor_client_turn_id,
        label=Bottleneck(row.label),
        evidence_quote=row.evidence_quote,
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        status=BottleneckSignalStatus(row.status),
        claimed_by=row.claimed_by,
        claimed_at=row.claimed_at,
        lease_expires_at=row.lease_expires_at,
        advisor_id=row.advisor_id,
        decided_at=row.decided_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
