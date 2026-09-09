"""SQLAlchemy adapter for advisor-approved session offers (T4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.domain.session_offer import SessionOffer
from src.agents.models import SessionOfferRow
from src.agents.ports import ClockPort


@dataclass(frozen=True, slots=True)
class SqlAlchemySessionOfferRepository:
    """Persist and load ACTIVE session-scoped offers."""

    session: AsyncSession
    clock: ClockPort

    async def insert(
        self,
        *,
        session_id: UUID,
        source_kind: str,
        promotion_code: str,
        value_snapshot: dict,
        approved_by: str,
        expires_at: datetime | None,
        source_signal_id: UUID | None = None,
        source_review_id: UUID | None = None,
    ) -> SessionOffer:
        now = self.clock.now()
        row = SessionOfferRow(
            offer_id=uuid4(),
            session_id=session_id,
            source_kind=source_kind,
            source_signal_id=source_signal_id,
            source_review_id=source_review_id,
            promotion_code=promotion_code,
            value_snapshot=value_snapshot,
            status="ACTIVE",
            approved_by=approved_by,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return self._to_offer(row)

    async def active_for_session(self, session_id: str) -> list[SessionOffer]:
        at = self.clock.now()
        rows = (
            await self.session.execute(
                select(SessionOfferRow).where(
                    SessionOfferRow.session_id == UUID(session_id),
                    SessionOfferRow.status == "ACTIVE",
                    (SessionOfferRow.expires_at.is_(None)) | (SessionOfferRow.expires_at > at),
                )
            )
        ).scalars()
        return [self._to_offer(row) for row in rows]

    @staticmethod
    def _to_offer(row: SessionOfferRow) -> SessionOffer:
        return SessionOffer(
            offer_id=row.offer_id,
            session_id=row.session_id,
            source_kind=row.source_kind,
            promotion_code=row.promotion_code,
            value_snapshot=row.value_snapshot,
            status=row.status,
            approved_by=row.approved_by,
            expires_at=row.expires_at,
        )
