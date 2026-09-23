"""SQLAlchemy adapter for owned conversation transcript and summary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationCursor,
    ConversationMessage,
    ConversationPage,
    ConversationState,
    ConversationSummary,
    CoreTurnLease,
    LeaseBusy,
    MessageCursor,
    MessagePage,
    TerminalReplay,
    TurnClaim,
    TurnOutcome,
    TurnOutcomeStatus,
    redact_sensitive,
)
from src.agents.domain.turn_result_payload import serialize_turn_result
from src.agents.errors import (
    ConversationArchivedError,
    ConversationNotFoundError,
    CoreTurnLeaseStaleError,
    SessionOwnershipError,
)
from src.agents.models import (
    ConversationMessageRow,
    ConversationSessionRow,
    ConversationSummaryRow,
    ConversationTurnOutcomeRow,
)
from src.agents.ports import ClockPort
from src.agents.services.conversation_memory import _turn_result as _normalized_turn_result


@dataclass(frozen=True, slots=True)
class SqlAlchemyConversationRepository:
    """Own the authenticated conversation lifecycle and visible message pages."""

    session: AsyncSession
    clock: ClockPort

    async def create(self, customer_id: str, *, conversation_id: UUID | None = None) -> Conversation:
        """Create an active conversation owned by the authenticated customer."""

        if not customer_id.strip():
            raise ValueError("customer_id must not be empty")
        now = self.clock.now()
        row = ConversationSessionRow(
            session_id=conversation_id or uuid4(),
            customer_id=customer_id,
            assigned_advisor_id=None,
            vehicle_type_hint=None,
            status="ACTIVE",
            started_at=now,
            last_activity_at=now,
            archived_at=None,
            ended_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return _conversation(row)

    async def list_owned(
        self,
        customer_id: str,
        *,
        limit: int,
        cursor: ConversationCursor | None = None,
        include_archived: bool = False,
    ) -> ConversationPage:
        """List owned conversations in stable newest-activity order."""

        if not 1 <= limit <= 100:
            raise ValueError("page limit must be between 1 and 100")
        statement = select(ConversationSessionRow).where(ConversationSessionRow.customer_id == customer_id)
        if not include_archived:
            statement = statement.where(ConversationSessionRow.archived_at.is_(None))
        if cursor is not None:
            statement = statement.where(
                or_(
                    ConversationSessionRow.last_activity_at < cursor.last_activity_at,
                    (
                        (ConversationSessionRow.last_activity_at == cursor.last_activity_at)
                        & (ConversationSessionRow.session_id < cursor.conversation_id)
                    ),
                )
            )
        rows = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        ConversationSessionRow.last_activity_at.desc(),
                        ConversationSessionRow.session_id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
        )
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = ConversationCursor(last.last_activity_at, last.session_id)
        return ConversationPage(tuple(_conversation(row) for row in visible), limit, next_cursor)

    async def get_owned(self, conversation_id: UUID, customer_id: str) -> Conversation:
        """Return an owned active or archived conversation."""

        row = await self._owned_row(conversation_id, customer_id, lock=False)
        return _conversation(row)

    async def archive(self, conversation_id: UUID, customer_id: str) -> Conversation:
        """Hide an owned conversation from the default list without deleting it."""

        row = await self._owned_row(conversation_id, customer_id, lock=True)
        if row.archived_at is None:
            now = self.clock.now()
            row.archived_at = now
            row.updated_at = now
            await self.session.flush()
        return _conversation(row)

    async def delete(self, conversation_id: UUID, customer_id: str) -> None:
        """Hard-delete one owned conversation and its Agent-owned dependent memory."""

        await self._owned_row(conversation_id, customer_id, lock=True)
        await self.session.execute(
            delete(ConversationSessionRow).where(ConversationSessionRow.session_id == conversation_id)
        )

    async def read_messages(
        self,
        conversation_id: UUID,
        customer_id: str,
        *,
        limit: int,
        cursor: MessageCursor | None = None,
    ) -> MessagePage:
        """Read a chronological stable page of customer-visible messages."""

        if not 1 <= limit <= 100:
            raise ValueError("page limit must be between 1 and 100")
        await self._owned_row(conversation_id, customer_id, lock=False)
        statement = select(ConversationMessageRow).where(ConversationMessageRow.session_id == conversation_id)
        if cursor is not None:
            statement = statement.where(
                or_(
                    ConversationMessageRow.turn_index > cursor.turn_index,
                    (
                        (ConversationMessageRow.turn_index == cursor.turn_index)
                        & (ConversationMessageRow.message_id > cursor.message_id)
                    ),
                )
            )
        rows = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        ConversationMessageRow.turn_index,
                        ConversationMessageRow.message_id,
                    ).limit(limit + 1)
                )
            ).all()
        )
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = MessageCursor(last.turn_index, last.message_id)
        return MessagePage(tuple(_message(row) for row in visible), limit, next_cursor)

    async def _owned_row(self, conversation_id: UUID, customer_id: str, *, lock: bool) -> ConversationSessionRow:
        statement = select(ConversationSessionRow).where(
            ConversationSessionRow.session_id == conversation_id,
            ConversationSessionRow.customer_id == customer_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise ConversationNotFoundError(str(conversation_id))
        return row


@dataclass(frozen=True, slots=True)
class SqlAlchemyTurnOutcomeRepository:
    """Claim and finalize exact replay payloads under the conversation row lock."""

    session: AsyncSession
    clock: ClockPort

    async def claim(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnClaim:
        """Claim one client key or return its existing immutable/current state."""

        conversation = await self.session.scalar(
            select(ConversationSessionRow)
            .where(
                ConversationSessionRow.session_id == conversation_id,
                ConversationSessionRow.customer_id == customer_id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.archived_at is not None:
            raise ConversationArchivedError(str(conversation_id))
        existing = await self.session.scalar(
            select(ConversationTurnOutcomeRow).where(
                ConversationTurnOutcomeRow.session_id == conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == client_turn_id,
            )
        )
        if existing is not None:
            return TurnClaim(_outcome(existing), claimed=False)
        last_turn = await self.session.scalar(
            select(func.max(ConversationTurnOutcomeRow.turn_number)).where(
                ConversationTurnOutcomeRow.session_id == conversation_id
            )
        )
        now = self.clock.now()
        row = ConversationTurnOutcomeRow(
            outcome_id=uuid4(),
            session_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=int(last_turn or 0) + 1,
            status=TurnOutcomeStatus.IN_PROGRESS.value,
            answer=None,
            pending_question=None,
            terminal_reason=None,
            lookup_facts=[],
            error_category=None,
            review_id=None,
            message_id=None,
            created_at=now,
            updated_at=now,
        )
        conversation.last_activity_at = now
        conversation.updated_at = now
        self.session.add(row)
        await self.session.flush()
        return TurnClaim(_outcome(row), claimed=True)

    async def acquire_core_turn_lease(
        self,
        conversation_id: UUID,
        customer_id: str,
        client_turn_id: UUID,
        *,
        lease_seconds: int,
    ) -> CoreTurnLease | TerminalReplay | LeaseBusy:
        """Cấp/takeover lease cho một turn, hoặc replay/trả busy.

        Transaction NGẮN: khóa conversation row → exact replay → active lease toàn
        session → cấp/takeover → flush. Caller phải commit ngay trước khi gọi LLM.
        Raw `TurnClaim` không bao giờ thoát boundary này.
        """

        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        conversation = await self.session.scalar(
            select(ConversationSessionRow)
            .where(
                ConversationSessionRow.session_id == conversation_id,
                ConversationSessionRow.customer_id == customer_id,
            )
            .with_for_update()
        )
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.archived_at is not None:
            raise ConversationArchivedError(str(conversation_id))
        existing = await self.session.scalar(
            select(ConversationTurnOutcomeRow).where(
                ConversationTurnOutcomeRow.session_id == conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == client_turn_id,
            )
        )
        if existing is not None:
            if existing.status != TurnOutcomeStatus.IN_PROGRESS.value:
                # Terminal-visible: COMPLETED/WAITING_REVIEW/REJECTED/EXPIRED → replay.
                # FAILED cũng terminal-visible tại repository; HTTP map 409 riêng.
                return TerminalReplay(_normalized_turn_result(_outcome(existing)))
            if existing.claim_token is not None and existing.lease_expires_at is not None:
                if existing.lease_expires_at > self.clock.now():
                    return LeaseBusy(retry_after_seconds=2)
                # Lease của CHÍNH lượt này hết hạn, nhưng một lượt KHÁC trong phiên
                # có thể đã chiếm phiên trong lúc đó. Takeover thẳng ở đây là tạo
                # HAI chủ lease cùng lúc và vỡ luật nối tiếp theo phiên:
                #   A hết hạn → B (mã khác) chiếm phiên → A thử lại mã cũ → A cũng
                #   chiếm → A và B cùng chạy, cùng ghi.
                # Nên phải hỏi lại phiên trước khi giành lại.
                if await self._active_lease_of_other_turn(conversation_id, client_turn_id) is not None:
                    return LeaseBusy(retry_after_seconds=2)
                # Lease hết hạn và phiên không còn ai giữ → takeover: token mới,
                # giữ nguyên turn_number.
                now = self.clock.now()
                existing.claim_token = uuid4()
                existing.claimed_at = now
                existing.lease_expires_at = now + timedelta(seconds=lease_seconds)
                existing.updated_at = now
                conversation.last_activity_at = now
                conversation.updated_at = now
                await self.session.flush()
                return _lease(existing)
            # Live TurnClaim cũ không có lease → busy (hàng cũ không lease).
            return LeaseBusy(retry_after_seconds=2)
        # Active lease toàn session chặn turn khác ID chạy song song.
        if await self._active_lease_of_other_turn(conversation_id, client_turn_id) is not None:
            return LeaseBusy(retry_after_seconds=2)
        last_turn = await self.session.scalar(
            select(func.max(ConversationTurnOutcomeRow.turn_number)).where(
                ConversationTurnOutcomeRow.session_id == conversation_id
            )
        )
        now = self.clock.now()
        row = ConversationTurnOutcomeRow(
            outcome_id=uuid4(),
            session_id=conversation_id,
            client_turn_id=client_turn_id,
            turn_number=int(last_turn or 0) + 1,
            status=TurnOutcomeStatus.IN_PROGRESS.value,
            answer=None,
            pending_question=None,
            terminal_reason=None,
            lookup_facts=[],
            error_category=None,
            review_id=None,
            message_id=None,
            claim_token=uuid4(),
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            created_at=now,
            updated_at=now,
        )
        conversation.last_activity_at = now
        conversation.updated_at = now
        self.session.add(row)
        await self.session.flush()
        return _lease(row)

    async def _active_lease_of_other_turn(
        self, conversation_id: UUID, client_turn_id: UUID
    ) -> ConversationTurnOutcomeRow | None:
        """Lượt KHÁC trong cùng phiên còn giữ lease sống, hoặc `None`.

        Một phiên một hàng trạng thái, nên hai lượt chạy song song là mở lại đúng
        lớp lỗi mất-ghi mà lease sinh ra để chặn. Loại trừ chính `client_turn_id`
        vì lượt này có đường riêng (replay/takeover) ở trên.
        """

        return await self.session.scalar(
            select(ConversationTurnOutcomeRow).where(
                ConversationTurnOutcomeRow.session_id == conversation_id,
                ConversationTurnOutcomeRow.client_turn_id != client_turn_id,
                ConversationTurnOutcomeRow.status == TurnOutcomeStatus.IN_PROGRESS.value,
                ConversationTurnOutcomeRow.lease_expires_at > self.clock.now(),
            )
        )

    async def assert_core_turn_lease(self, lease: CoreTurnLease) -> None:
        """Xác nhận token còn là owner hợp lệ (session, client turn, token, chưa hết hạn)."""

        row = await self.session.scalar(
            select(ConversationTurnOutcomeRow).where(
                ConversationTurnOutcomeRow.session_id == lease.session_id,
                ConversationTurnOutcomeRow.client_turn_id == lease.client_turn_id,
            )
        )
        if row is None:
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason="missing_outcome",
            )
        if row.status != TurnOutcomeStatus.IN_PROGRESS.value:
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason=f"terminal_{row.status}",
            )
        if row.claim_token != lease.claim_token:
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason="token_replaced",
            )
        if row.lease_expires_at is None or row.lease_expires_at <= self.clock.now():
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason="lease_expired",
            )

    async def get(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome | None:
        """Read an outcome only through its authenticated conversation owner."""

        owned = await self.session.scalar(
            select(ConversationSessionRow.session_id).where(
                ConversationSessionRow.session_id == conversation_id,
                ConversationSessionRow.customer_id == customer_id,
            )
        )
        if owned is None:
            raise ConversationNotFoundError(str(conversation_id))
        row = await self.session.scalar(
            select(ConversationTurnOutcomeRow).where(
                ConversationTurnOutcomeRow.session_id == conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == client_turn_id,
            )
        )
        if (
            row is not None
            and row.status == TurnOutcomeStatus.IN_PROGRESS.value
            and row.lease_expires_at is not None
            and row.lease_expires_at <= self.clock.now()
        ):
            raise CoreTurnLeaseStaleError(
                session_id=str(conversation_id),
                client_turn_id=str(client_turn_id),
                reason="lease_expired",
            )
        return _outcome(row) if row is not None else None

    async def latest(
        self,
        conversation_id: UUID,
        customer_id: str,
        *,
        exclude_client_turn_id: UUID | None = None,
    ) -> TurnOutcome | None:
        """Read the newest outcome only through its authenticated conversation owner.

        `exclude_client_turn_id` bỏ qua ĐÚNG một lượt — dùng khi người gọi muốn
        hỏi "lượt TRƯỚC thế nào". `chain.run_turn` gọi `memory.start_turn` từ
        rất sớm, nên hàng của lượt đang chạy đã nằm trong bảng (status
        `IN_PROGRESS`, chưa có `pending_question`) trước mọi lần đọc sau đó —
        không loại nó ra thì "lượt trước" luôn chính là lượt hiện tại.

        Bug thật 2026-08-26: `bot_asked_last_turn` vì thế trả `False` ở **188/188**
        lượt trên prod, khiến ba cờ "đây là câu trả lời" không bao giờ mở được cửa
        phạm vi. Khách đáp "không cần" cho câu hỏi tính năng thì bị trả lời như
        một câu ngoài phạm vi.
        """

        owned = await self.session.scalar(
            select(ConversationSessionRow.session_id).where(
                ConversationSessionRow.session_id == conversation_id,
                ConversationSessionRow.customer_id == customer_id,
            )
        )
        if owned is None:
            raise ConversationNotFoundError(str(conversation_id))
        statement = select(ConversationTurnOutcomeRow).where(ConversationTurnOutcomeRow.session_id == conversation_id)
        if exclude_client_turn_id is not None:
            statement = statement.where(ConversationTurnOutcomeRow.client_turn_id != exclude_client_turn_id)
        row = await self.session.scalar(statement.order_by(ConversationTurnOutcomeRow.created_at.desc()).limit(1))
        return _outcome(row) if row is not None else None

    async def finalize(self, outcome: TurnOutcome) -> TurnOutcome:
        """Finalize a claimed turn once while preserving an existing terminal result."""

        row = await self.session.scalar(
            select(ConversationTurnOutcomeRow)
            .where(
                ConversationTurnOutcomeRow.session_id == outcome.conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == outcome.client_turn_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ConversationNotFoundError(str(outcome.conversation_id))
        if row.status != TurnOutcomeStatus.IN_PROGRESS.value:
            return _outcome(row)
        row.status = outcome.status.value
        row.answer = redact_sensitive(outcome.answer) if outcome.answer else None
        row.pending_question = redact_sensitive(outcome.pending_question) if outcome.pending_question else None
        row.terminal_reason = outcome.terminal_reason
        row.lookup_facts = [dict(item) for item in outcome.lookup_facts]
        row.recommendations = [dict(item) for item in outcome.recommendations]
        row.result_payload = dict(outcome.result_payload) if outcome.result_payload is not None else None
        row.error_category = outcome.error_category
        row.review_id = outcome.review_id
        row.message_id = outcome.message_id
        row.updated_at = self.clock.now()
        await self.session.flush()
        return _outcome(row)

    async def fail(
        self,
        conversation_id: UUID,
        client_turn_id: UUID,
        *,
        error_category: str,
    ) -> TurnOutcome:
        """Persist a safe immutable failure without transcript or exception text."""

        row = await self.session.scalar(
            select(ConversationTurnOutcomeRow)
            .where(
                ConversationTurnOutcomeRow.session_id == conversation_id,
                ConversationTurnOutcomeRow.client_turn_id == client_turn_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ConversationNotFoundError(str(conversation_id))
        if row.status == TurnOutcomeStatus.IN_PROGRESS.value:
            row.status = TurnOutcomeStatus.FAILED.value
            row.error_category = error_category
            row.updated_at = self.clock.now()
            await self.session.flush()
        return _outcome(row)

    async def set_review_terminal(
        self,
        review_id: UUID,
        *,
        status: TurnOutcomeStatus,
        message_id: UUID | None = None,
        delivered_content: str | None = None,
    ) -> TurnOutcome | None:
        """Advance a waiting review outcome during approve/reject/expiry."""

        row = await self.session.scalar(
            select(ConversationTurnOutcomeRow)
            .where(ConversationTurnOutcomeRow.review_id == review_id)
            .with_for_update()
        )
        if row is None:
            return None
        if row.status == TurnOutcomeStatus.WAITING_REVIEW.value:
            row.status = status.value
            row.message_id = message_id
            if status is TurnOutcomeStatus.COMPLETED:
                row.answer = redact_sensitive(delivered_content) if delivered_content else row.answer
                row.pending_question = None
            elif status in {TurnOutcomeStatus.REJECTED, TurnOutcomeStatus.EXPIRED}:
                row.answer = None
                row.pending_question = None
                row.terminal_reason = status.value
            row.result_payload = serialize_turn_result(
                _normalized_turn_result(replace(_outcome(row), result_payload=None))
            )
            row.updated_at = self.clock.now()
            await self.session.flush()
        return _outcome(row)


@dataclass(frozen=True, slots=True)
class SqlAlchemyConversationMemoryRepository:
    """Append and load memory while enforcing session ownership on every call."""

    session: AsyncSession
    clock: ClockPort

    async def find_by_client_turn(
        self, session_id: str, customer_id: str, client_turn_id: UUID
    ) -> tuple[ConversationMessage, ...]:
        """Return already-persisted roles for an idempotent client turn."""

        await self._assert_owner(session_id, customer_id, lock=False)
        rows = (
            await self.session.scalars(
                select(ConversationMessageRow)
                .where(
                    ConversationMessageRow.session_id == UUID(session_id),
                    ConversationMessageRow.client_turn_id == client_turn_id,
                )
                .order_by(ConversationMessageRow.turn_index)
            )
        ).all()
        return tuple(_message(row) for row in rows)

    async def append(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        client_turn_id: UUID | None,
    ) -> ConversationMessage:
        """Append one visible message, allocating its index under a session lock."""

        safe = ConversationMessage(role=role, content=redact_sensitive(content), turn_index=1)
        identifier = UUID(session_id)
        await self._assert_owner(session_id, customer_id, lock=True)
        if client_turn_id is not None:
            existing = await self.session.scalar(
                select(ConversationMessageRow).where(
                    ConversationMessageRow.session_id == identifier,
                    ConversationMessageRow.client_turn_id == client_turn_id,
                    ConversationMessageRow.role == role,
                )
            )
            if existing is not None:
                return _message(existing)
        last_index = await self.session.scalar(
            select(func.max(ConversationMessageRow.turn_index)).where(ConversationMessageRow.session_id == identifier)
        )
        row = ConversationMessageRow(
            message_id=uuid4(),
            session_id=identifier,
            client_turn_id=client_turn_id,
            role=str(safe.role),
            content=safe.content,
            turn_index=int(last_index or 0) + 1,
            created_at=self.clock.now(),
        )
        self.session.add(row)
        await self.session.flush()
        return _message(row)

    async def load_recent(
        self, session_id: str, customer_id: str, limit: int
    ) -> tuple[ConversationSummary | None, tuple[ConversationMessage, ...]]:
        """Load the summary plus newest messages after its coverage marker."""

        await self._assert_owner(session_id, customer_id, lock=False)
        identifier = UUID(session_id)
        summary_row = await self.session.get(ConversationSummaryRow, identifier)
        through = summary_row.summarized_through_turn if summary_row is not None else 0
        rows = list(
            (
                await self.session.scalars(
                    select(ConversationMessageRow)
                    .where(
                        ConversationMessageRow.session_id == identifier,
                        ConversationMessageRow.turn_index > through,
                    )
                    .order_by(ConversationMessageRow.turn_index.desc())
                    .limit(max(1, limit))
                )
            ).all()
        )
        rows.reverse()
        summary = (
            ConversationSummary(
                summary_row.content,
                summary_row.summarized_through_turn,
                summary_row.prompt_version,
                summary_row.model_name,
            )
            if summary_row is not None
            else None
        )
        return summary, tuple(_message(row) for row in rows)

    async def append_delivery(self, session_id: UUID, content: str, delivery_id: UUID) -> ConversationMessage:
        """Append one trusted HITL delivery once after its approval gate."""

        safe = ConversationMessage(role="ASSISTANT", content=redact_sensitive(content), turn_index=1)
        owner = await self.session.scalar(
            select(ConversationSessionRow.session_id)
            .where(ConversationSessionRow.session_id == session_id)
            .with_for_update()
        )
        if owner is None:
            raise ValueError("conversation session does not exist")
        existing = await self.session.scalar(
            select(ConversationMessageRow).where(
                ConversationMessageRow.session_id == session_id,
                ConversationMessageRow.review_id == delivery_id,
                ConversationMessageRow.role == "ASSISTANT",
            )
        )
        if existing is not None:
            return _message(existing)
        last_index = await self.session.scalar(
            select(func.max(ConversationMessageRow.turn_index)).where(ConversationMessageRow.session_id == session_id)
        )
        row = ConversationMessageRow(
            message_id=uuid4(),
            session_id=session_id,
            client_turn_id=None,
            review_id=delivery_id,
            role=str(safe.role),
            content=safe.content,
            turn_index=int(last_index or 0) + 1,
            created_at=self.clock.now(),
        )
        self.session.add(row)
        await self.session.flush()
        return _message(row)

    async def save_summary(self, session_id: str, customer_id: str, summary: ConversationSummary) -> None:
        """Advance the summary marker; an older worker cannot move it backwards."""

        await self._assert_owner(session_id, customer_id, lock=True)
        statement = insert(ConversationSummaryRow).values(
            session_id=UUID(session_id),
            content=redact_sensitive(summary.content),
            summarized_through_turn=summary.summarized_through_turn,
            prompt_version=summary.prompt_version,
            model_name=summary.model_name,
            updated_at=self.clock.now(),
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[ConversationSummaryRow.session_id],
                set_={
                    "content": statement.excluded.content,
                    "summarized_through_turn": statement.excluded.summarized_through_turn,
                    "prompt_version": statement.excluded.prompt_version,
                    "model_name": statement.excluded.model_name,
                    "updated_at": statement.excluded.updated_at,
                },
                where=(statement.excluded.summarized_through_turn >= ConversationSummaryRow.summarized_through_turn),
            )
        )

    async def _assert_owner(self, session_id: str, customer_id: str, *, lock: bool) -> None:
        statement = select(ConversationSessionRow.customer_id).where(
            ConversationSessionRow.session_id == UUID(session_id)
        )
        if lock:
            statement = statement.with_for_update()
        owner = await self.session.scalar(statement)
        if owner != customer_id:
            raise SessionOwnershipError(session_id=session_id, customer_id=customer_id)


def _message(row: ConversationMessageRow) -> ConversationMessage:
    return ConversationMessage(
        role=row.role,
        content=row.content,
        turn_index=row.turn_index,
        message_id=row.message_id,
        conversation_id=row.session_id,
        client_turn_id=row.client_turn_id,
        review_id=row.review_id,
        created_at=row.created_at,
    )


def _conversation(row: ConversationSessionRow) -> Conversation:
    state = ConversationState.ARCHIVED if row.archived_at is not None else ConversationState.ACTIVE
    return Conversation(
        conversation_id=row.session_id,
        customer_id=row.customer_id,
        state=state,
        created_at=row.created_at,
        last_activity_at=row.last_activity_at,
        archived_at=row.archived_at,
    )


def _outcome(row: ConversationTurnOutcomeRow) -> TurnOutcome:
    return TurnOutcome(
        conversation_id=row.session_id,
        client_turn_id=row.client_turn_id,
        turn_number=row.turn_number,
        status=TurnOutcomeStatus(row.status),
        answer=row.answer,
        pending_question=row.pending_question,
        terminal_reason=row.terminal_reason,
        lookup_facts=tuple(row.lookup_facts or []),
        recommendations=tuple(row.recommendations or []),
        result_payload=row.result_payload,
        error_category=row.error_category,
        review_id=row.review_id,
        message_id=row.message_id,
    )


def _lease(row: ConversationTurnOutcomeRow) -> CoreTurnLease:
    if row.claim_token is None or row.claimed_at is None or row.lease_expires_at is None:
        raise RuntimeError("live outcome row missing lease fields")
    return CoreTurnLease(
        session_id=row.session_id,
        client_turn_id=row.client_turn_id,
        turn_number=row.turn_number,
        claim_token=row.claim_token,
        claimed_at=row.claimed_at,
        lease_expires_at=row.lease_expires_at,
    )
