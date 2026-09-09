"""SQLAlchemy adapter for conversation sessions and slots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import assert_never
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.domain.values import SlotName, SlotValue, VehicleType, is_declined
from src.agents.errors import ConversationArchivedError, SessionOwnershipError
from src.agents.models import (
    ConversationMessageRow,
    ConversationSessionRow,
    ConversationSlotRow,
    PendingFeatureMentionRow,
    SlotAskAttemptRow,
)
from src.agents.ports import ClockPort


@dataclass(frozen=True, slots=True)
class SqlAlchemySessionRepository:
    """Persist session ownership and one current value for each slot."""

    session: AsyncSession
    clock: ClockPort

    async def ensure_session(self, session_id: str, customer_id: str, vehicle_type_hint: VehicleType | None) -> None:
        """Create a session or refresh its activity only for its authenticated owner."""

        identifier = UUID(session_id)
        now = self.clock.now()
        statement = insert(ConversationSessionRow).values(
            session_id=identifier,
            customer_id=customer_id,
            vehicle_type_hint=vehicle_type_hint.value if vehicle_type_hint is not None else None,
            started_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ConversationSessionRow.session_id],
            set_={
                "last_activity_at": now,
                "updated_at": now,
                "vehicle_type_hint": func.coalesce(
                    statement.excluded.vehicle_type_hint, ConversationSessionRow.vehicle_type_hint
                ),
            },
            where=(ConversationSessionRow.customer_id == customer_id) & ConversationSessionRow.archived_at.is_(None),
        )
        result = await self.session.execute(statement.returning(ConversationSessionRow.session_id))
        if result.scalar_one_or_none() is None:
            archived_at = await self.session.scalar(
                select(ConversationSessionRow.archived_at).where(
                    ConversationSessionRow.session_id == identifier,
                    ConversationSessionRow.customer_id == customer_id,
                )
            )
            if archived_at is not None:
                raise ConversationArchivedError(conversation_id=str(identifier))
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)

    async def get_slots(self, session_id: str, customer_id: str) -> dict[SlotName, SlotValue]:
        """Load current slot values only for their authenticated session owner.

        A session that has not been created yet has no slots and no owner.
        """

        identifier = UUID(session_id)
        owner = await self.session.scalar(
            select(ConversationSessionRow.customer_id).where(ConversationSessionRow.session_id == identifier)
        )
        if owner is None:
            return {}
        if owner != customer_id:
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)
        statement = select(ConversationSlotRow).where(ConversationSlotRow.session_id == identifier)
        rows = (await self.session.execute(statement)).scalars()
        return {SlotName(row.slot_name): _slot_value(SlotName(row.slot_name), row) for row in rows}

    async def load_pending_slot(self, session_id: str) -> dict | None:
        """[A7-10] Slot đang chờ khách trả lời, hoặc `None`."""

        return await self.session.scalar(
            select(ConversationSessionRow.pending_slot_request).where(
                ConversationSessionRow.session_id == UUID(session_id)
            )
        )

    async def save_pending_slot(self, session_id: str, payload: Mapping | None) -> None:
        """Ghi hoặc XOÁ pending. `None` là xoá — khác hẳn `save_quote_decision`,
        nơi `None` không bao giờ được ghi xuống."""

        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(
                pending_slot_request=None if payload is None else dict(payload),
                updated_at=self.clock.now(),
            )
        )

    async def load_pending_intent_confirmation(self, session_id: str) -> dict | None:
        """Câu xác nhận ý định đang chờ khách trả lời, hoặc `None`."""

        return await self.session.scalar(
            select(ConversationSessionRow.pending_intent_confirmation).where(
                ConversationSessionRow.session_id == UUID(session_id)
            )
        )

    async def save_pending_intent_confirmation(self, session_id: str, payload: Mapping | None) -> None:
        """Ghi hoặc XOÁ bản ghi xác nhận. `None` là xoá, cùng quy ước A7-10."""

        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(
                pending_intent_confirmation=None if payload is None else dict(payload),
                updated_at=self.clock.now(),
            )
        )

    async def load_active_task(self, session_id: str) -> dict | None:
        """Return the focused structured task, or ``None`` when no task is active."""

        return await self.session.scalar(
            select(ConversationSessionRow.active_task_state).where(
                ConversationSessionRow.session_id == UUID(session_id)
            )
        )

    async def save_active_task(self, session_id: str, payload: Mapping | None) -> None:
        """Replace or clear the single follow-up-eligible task for this session."""

        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(
                active_task_state=None if payload is None else dict(payload),
                updated_at=self.clock.now(),
            )
        )

    async def load_user_location(self, session_id: str) -> dict | None:
        """Vị trí khách đã chia sẻ trong phiên, hoặc `None`."""

        return await self.session.scalar(
            select(ConversationSessionRow.user_location).where(ConversationSessionRow.session_id == UUID(session_id))
        )

    async def save_user_location(self, session_id: str, payload: Mapping | None) -> None:
        """Ghi đè vị trí của phiên. `None` là xoá, cùng quy ước A7-10."""

        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(
                user_location=None if payload is None else dict(payload),
                updated_at=self.clock.now(),
            )
        )

    async def load_quote_decision(self, session_id: str) -> tuple[dict | None, datetime | None]:
        """Đọc đánh giá của báo giá gần nhất; phiên chưa có thì trả `(None, None)`."""

        row = (
            await self.session.execute(
                select(
                    ConversationSessionRow.last_quote_evaluation,
                    ConversationSessionRow.last_quote_sent_at,
                ).where(ConversationSessionRow.session_id == UUID(session_id))
            )
        ).one_or_none()
        return (None, None) if row is None else (row[0], row[1])

    async def save_quote_decision(self, session_id: str, evaluation: Mapping[str, object], sent_at: datetime) -> None:
        """Ghi đè bộ nhớ báo giá — CHỈ gọi khi vừa dựng một đánh giá mới.

        Không có nhánh nào ghi `None` vào đây: xoá bộ nhớ là cách nhanh nhất để
        dựng lại đúng con bug mà A7-5 sinh ra để sửa.
        """

        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(
                last_quote_evaluation=dict(evaluation),
                last_quote_sent_at=sent_at,
                updated_at=self.clock.now(),
            )
        )

    async def upsert_slot(self, session_id: str, slot_name: SlotName, value: SlotValue) -> None:
        """Replace a slot value while retaining its single composite-key row."""

        text_value, number_value = _slot_columns(value)
        now = self.clock.now()
        statement = insert(ConversationSlotRow).values(
            session_id=UUID(session_id),
            slot_name=slot_name.value,
            slot_value_text=text_value,
            slot_value_number=number_value,
            confirmed_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ConversationSlotRow.session_id, ConversationSlotRow.slot_name],
            set_={
                "slot_value_text": text_value,
                "slot_value_number": number_value,
                "confirmed_at": now,
                "updated_at": now,
            },
        )
        await self.session.execute(statement)

    async def list_owned_sessions(self, customer_id: str) -> list[ConversationSessionRow]:
        """List a customer's sessions newest first."""

        result = await self.session.execute(
            select(ConversationSessionRow)
            .where(ConversationSessionRow.customer_id == customer_id)
            .order_by(ConversationSessionRow.last_activity_at.desc())
        )
        return list(result.scalars())

    async def get_session(self, session_id: UUID) -> ConversationSessionRow | None:
        """Load one session without exposing it to an unauthorized caller."""

        return await self.session.scalar(
            select(ConversationSessionRow).where(ConversationSessionRow.session_id == session_id)
        )

    async def get_ownership(self, session_id: str) -> str | None:
        """Read the conversation ownership state (`AI`/`PENDING_HANDOFF`/`HUMAN`)."""

        return await self.session.scalar(
            select(ConversationSessionRow.ownership).where(ConversationSessionRow.session_id == UUID(session_id))
        )

    async def set_ownership(self, session_id: str, ownership: str) -> bool:
        """Transition the conversation ownership state."""

        result = await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == UUID(session_id))
            .values(ownership=ownership, updated_at=self.clock.now())
        )
        return result.rowcount == 1

    async def delete_session(self, session_id: UUID, customer_id: str | None = None) -> bool:
        """Delete an owned session or staff deleted session; database cascades remove its children."""

        statement = ConversationSessionRow.__table__.delete().where(ConversationSessionRow.session_id == session_id)
        if customer_id is not None:
            statement = statement.where(ConversationSessionRow.customer_id == customer_id)
        result = await self.session.execute(statement)
        return result.rowcount == 1

    async def delete_messages(self, session_id: UUID, customer_id: str) -> int:
        """Delete messages only while retaining the conversation shell."""

        owner = await self.session.scalar(
            select(ConversationSessionRow.customer_id).where(ConversationSessionRow.session_id == session_id)
        )
        if owner != customer_id:
            raise SessionOwnershipError(session_id=str(session_id), customer_id=customer_id)
        result = await self.session.execute(
            ConversationMessageRow.__table__.delete().where(ConversationMessageRow.session_id == session_id)
        )
        return result.rowcount

    async def archive_session(self, session_id: UUID, customer_id: str) -> bool:
        """Archive an owned active session without deleting its transcript."""

        result = await self.session.execute(
            update(ConversationSessionRow)
            .where(
                ConversationSessionRow.session_id == session_id,
                ConversationSessionRow.customer_id == customer_id,
            )
            .values(status="COMPLETED", ended_at=self.clock.now(), updated_at=self.clock.now())
        )
        return result.rowcount == 1

    async def list_staff_sessions(
        self, *, requester_id: str, role: str, customer_id: str | None = None
    ) -> list[ConversationSessionRow]:
        """List all sessions for staff (admin or advisor)."""

        statement = select(ConversationSessionRow)
        if customer_id is not None:
            statement = statement.where(ConversationSessionRow.customer_id == customer_id)
        if role.lower() not in {"admin", "advisor"}:
            statement = statement.where(ConversationSessionRow.assigned_advisor_id == requester_id)
        result = await self.session.execute(statement.order_by(ConversationSessionRow.last_activity_at.desc()))
        return list(result.scalars())

    async def claim_session(self, session_id: UUID, advisor_id: str) -> bool:
        """Atomically claim an unassigned conversation for live chat."""

        result = await self.session.execute(
            update(ConversationSessionRow)
            .where(
                ConversationSessionRow.session_id == session_id,
                (ConversationSessionRow.assigned_advisor_id.is_(None))
                | (ConversationSessionRow.assigned_advisor_id == advisor_id),
                ConversationSessionRow.status == "ACTIVE",
            )
            .values(
                assigned_advisor_id=advisor_id,
                ownership="HUMAN",
                status="ACTIVE",
                updated_at=self.clock.now(),
                last_activity_at=self.clock.now(),
            )
        )
        return result.rowcount == 1

    async def close_session(self, session_id: UUID, advisor_id: str) -> bool:
        """Close a live chat and mark completed."""

        row = await self.session.scalar(
            select(ConversationSessionRow).where(ConversationSessionRow.session_id == session_id)
        )
        if row is None:
            return False
        if row.status == "COMPLETED":
            return True
        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == session_id)
            .values(status="COMPLETED", ownership="AI", ended_at=self.clock.now(), updated_at=self.clock.now())
        )
        return True

    async def release_session_to_agent(self, session_id: UUID) -> bool:
        """Release an assigned session back to the AI Agent."""

        result = await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == session_id)
            .values(
                assigned_advisor_id=None,
                ownership="AI",
                status="ACTIVE",
                updated_at=self.clock.now(),
                last_activity_at=self.clock.now(),
            )
        )
        return result.rowcount == 1

    async def restart_advisory(self, session_id: str) -> None:
        """Clear all mutable advisory state while retaining the conversation transcript."""

        identifier = UUID(session_id)
        await self.session.execute(delete(ConversationSlotRow).where(ConversationSlotRow.session_id == identifier))
        await self.session.execute(delete(SlotAskAttemptRow).where(SlotAskAttemptRow.session_id == identifier))
        await self.session.execute(
            update(ConversationSessionRow)
            .where(ConversationSessionRow.session_id == identifier)
            .values(
                vehicle_type_hint=None,
                pending_slot_request=None,
                active_task_state=None,
                updated_at=self.clock.now(),
            )
        )

    async def get_ask_counts(self, session_id: str) -> dict[str, int]:
        """Số lần đã hỏi từng field trong phiên.

        Khoá là chuỗi thô chứ không phải `SlotName`: câu định tuyến (`ROUTING_FIELD`)
        cũng cần đếm nhưng không thuộc cây slot nào.
        """

        statement = select(SlotAskAttemptRow).where(SlotAskAttemptRow.session_id == UUID(session_id))
        return {row.slot_name: row.ask_count for row in (await self.session.execute(statement)).scalars()}

    async def bump_ask_count(self, session_id: str, slot_name: str) -> None:
        """Tăng đếm cho đúng một slot, tạo hàng nếu chưa có."""

        now = self.clock.now()
        statement = insert(SlotAskAttemptRow).values(
            session_id=UUID(session_id),
            slot_name=slot_name,
            ask_count=1,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[SlotAskAttemptRow.session_id, SlotAskAttemptRow.slot_name],
            set_={"ask_count": SlotAskAttemptRow.ask_count + 1, "updated_at": now},
        )
        await self.session.execute(statement)

    async def reset_ask_count(self, session_id: str, slot_name: str) -> None:
        """Khách trả lời được thì đếm về 0 (prompt mục 4)."""

        await self.session.execute(
            update(SlotAskAttemptRow)
            .where(
                SlotAskAttemptRow.session_id == UUID(session_id),
                SlotAskAttemptRow.slot_name == slot_name,
            )
            .values(ask_count=0, updated_at=self.clock.now())
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyPendingFeatureMentionRepository:
    """Persist and atomically consume authenticated unresolved feature mentions."""

    session: AsyncSession
    clock: ClockPort

    async def record(self, session_id: str, customer_id: str, mentions: list[str]) -> None:
        """Insert normalized pending mentions once per session under database uniqueness."""

        await self._assert_owner(session_id, customer_id, lock=False)
        now = self.clock.now()
        for mention in mentions:
            statement = insert(PendingFeatureMentionRow).values(
                id=uuid4(), session_id=UUID(session_id), raw_mention=mention, created_at=now
            )
            await self.session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[PendingFeatureMentionRow.session_id, PendingFeatureMentionRow.raw_mention],
                    index_where=PendingFeatureMentionRow.applied_at.is_(None),
                )
            )

    async def consume(self, session_id: str, customer_id: str) -> list[str]:
        """Lock ownership then delete and return each pending mention exactly once."""

        await self._assert_owner(session_id, customer_id, lock=True)
        statement = (
            update(PendingFeatureMentionRow)
            .where(
                PendingFeatureMentionRow.session_id == UUID(session_id),
                PendingFeatureMentionRow.applied_at.is_(None),
            )
            .values(applied_at=self.clock.now())
            .returning(PendingFeatureMentionRow.raw_mention)
        )
        return list((await self.session.scalars(statement)).all())

    async def _assert_owner(self, session_id: str, customer_id: str, lock: bool) -> None:
        statement = select(ConversationSessionRow.customer_id).where(
            ConversationSessionRow.session_id == UUID(session_id)
        )
        if lock:
            statement = statement.with_for_update()
        owner = await self.session.scalar(statement)
        if owner != customer_id:
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)


@dataclass(frozen=True, slots=True)
class SqlAlchemyMessageRepository:
    """Persist and read durable messages inside the caller transaction."""

    session: AsyncSession
    clock: ClockPort

    async def find_user_by_client_turn(self, session_id: UUID, client_turn_id: str) -> tuple[UUID, datetime] | None:
        row = (
            await self.session.execute(
                select(ConversationMessageRow.message_id, ConversationMessageRow.created_at)
                .where(
                    ConversationMessageRow.session_id == session_id,
                    ConversationMessageRow.role == "USER",
                    ConversationMessageRow.client_turn_id == client_turn_id,
                )
                .limit(1)
            )
        ).first()
        return (row.message_id, row.created_at) if row is not None else None

    async def find_assistant_after(self, session_id: UUID, created_after: datetime) -> tuple[UUID, str] | None:
        row = (
            await self.session.execute(
                select(ConversationMessageRow.message_id, ConversationMessageRow.content)
                .where(
                    ConversationMessageRow.session_id == session_id,
                    ConversationMessageRow.role == "ASSISTANT",
                    ConversationMessageRow.created_at >= created_after,
                )
                .order_by(ConversationMessageRow.created_at, ConversationMessageRow.message_id)
                .limit(1)
            )
        ).first()
        return (row.message_id, row.content) if row is not None else None

    async def add(
        self,
        *,
        session_id: UUID,
        role: str,
        content: str,
        client_turn_id: str | None = None,
        durable_for_review_id: UUID | None = None,
    ) -> UUID:
        """Insert one non-empty durable message and flush its generated identity."""

        if role not in {"USER", "ASSISTANT", "ADVISOR"}:
            raise ValueError("unsupported conversation message role")
        if not content.strip():
            raise ValueError("conversation message content must not be empty")
        message_id = uuid4()
        last_index = await self.session.scalar(
            select(func.max(ConversationMessageRow.turn_index)).where(ConversationMessageRow.session_id == session_id)
        )
        typed_client_turn_id: UUID | None = None
        if client_turn_id:
            try:
                typed_client_turn_id = UUID(client_turn_id)
            except ValueError:
                pass
        self.session.add(
            ConversationMessageRow(
                message_id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                client_turn_id=typed_client_turn_id,
                review_id=durable_for_review_id,
                turn_index=int(last_index or 0) + 1,
                created_at=self.clock.now(),
            )
        )
        await self.session.flush()
        return message_id

    async def list_for_session(
        self, session_id: UUID, limit: int = 100
    ) -> list[tuple[UUID, str, str, str | None, datetime]]:
        rows = (
            await self.session.execute(
                select(
                    ConversationMessageRow.message_id,
                    ConversationMessageRow.role,
                    ConversationMessageRow.content,
                    ConversationMessageRow.client_turn_id,
                    ConversationMessageRow.created_at,
                )
                .where(ConversationMessageRow.session_id == session_id)
                .order_by(ConversationMessageRow.turn_index, ConversationMessageRow.created_at)
                .limit(limit)
            )
        ).all()
        return [
            (
                row[0],
                row[1],
                row[2],
                str(row[3]) if row[3] is not None else None,
                row[4],
            )
            for row in rows
        ]

    async def latest_content(self, session_id: UUID) -> str | None:
        """Tin cuối theo `turn_index` rồi `created_at` — cùng thứ tự `list_for_session` đọc.

        Màn TVV (đợt 9) chỉ cần MỘT dòng xem trước cho mỗi phiên; kéo cả 200 tin
        của mỗi phiên trong danh sách là N lần nặng hơn cần thiết.
        """

        row = (
            await self.session.execute(
                select(ConversationMessageRow.content)
                .where(ConversationMessageRow.session_id == session_id)
                .order_by(ConversationMessageRow.turn_index.desc(), ConversationMessageRow.created_at.desc())
                .limit(1)
            )
        ).first()
        return None if row is None else row[0]


def _slot_columns(value: SlotValue) -> tuple[str | None, Decimal | None]:
    match value:
        case None:
            return None, None
        case bool():
            return str(value).lower(), None
        case str():
            return value, None
        case int() | float():
            return None, Decimal(str(value))
        case list():
            return json.dumps(value), None
        case unreachable:
            assert_never(unreachable)


def _slot_value(slot_name: SlotName, row: ConversationSlotRow) -> SlotValue:
    if row.slot_value_number is not None:
        if row.slot_value_number == row.slot_value_number.to_integral_value():
            return int(row.slot_value_number)
        return float(row.slot_value_number)
    if slot_name is SlotName.HOME_CHARGING and row.slot_value_text in {"true", "false"}:
        return row.slot_value_text == "true"
    if (
        slot_name is SlotName.HABIT_NEED_TAGS
        and row.slot_value_text is not None
        and not is_declined(row.slot_value_text)
    ):
        decoded = json.loads(row.slot_value_text)
        if isinstance(decoded, list) and all(isinstance(tag, str) for tag in decoded):
            return decoded
    return row.slot_value_text
