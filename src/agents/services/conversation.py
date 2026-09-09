"""Conversation session and slot use case."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from src.agents.core.state import CoreState
from src.agents.domain.conversation_memory import (
    Conversation,
    ConversationPage,
    MessagePage,
    TurnOutcome,
    decode_conversation_cursor,
    decode_message_cursor,
)
from src.agents.domain.conversation_memory import (
    # DTO cục bộ ở cuối file trùng TÊN với bản domain; đặt bí danh để mỗi chỗ
    # dùng nói rõ nó cần bản nào.
    ConversationMessage as TranscriptMessage,
)
from src.agents.domain.feature_selection import UNKNOWN_QUESTION
from src.agents.domain.turn_trace import TurnTrace
from src.agents.domain.values import SlotName, SlotValue
from src.agents.ports import UnitOfWorkPort
from src.agents.services.slot_codec import coerce_slots, coerce_vehicle_type, encode_slots


class ConversationLifecycleService:
    """Authenticated lifecycle boundary used by the public Conversation API."""

    def __init__(self, unit_of_work: UnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def create(self, customer_id: str) -> Conversation:
        """Create one server-owned conversation ID."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.conversations.create(customer_id)

    async def list_owned(
        self,
        customer_id: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        include_archived: bool = False,
    ) -> ConversationPage:
        """List a stable page of the authenticated customer's conversations."""

        decoded = decode_conversation_cursor(cursor) if cursor else None
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.conversations.list_owned(
                customer_id,
                limit=limit,
                cursor=decoded,
                include_archived=include_archived,
            )

    async def detail(self, conversation_id: UUID, customer_id: str) -> Conversation:
        """Load one owned active or archived conversation."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.conversations.get_owned(conversation_id, customer_id)

    async def messages(
        self,
        conversation_id: UUID,
        customer_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> MessagePage:
        """Load one chronological page of visible transcript messages."""

        decoded = decode_message_cursor(cursor) if cursor else None
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.conversations.read_messages(
                conversation_id, customer_id, limit=limit, cursor=decoded
            )

    async def archive(self, conversation_id: UUID, customer_id: str) -> Conversation:
        """Archive one owned conversation."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.conversations.archive(conversation_id, customer_id)

    async def delete(self, conversation_id: UUID, customer_id: str) -> None:
        """Delete one owned conversation and its cascading Agent memory."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.conversations.delete(conversation_id, customer_id)

    async def turn_outcome(self, conversation_id: UUID, customer_id: str, client_turn_id: UUID) -> TurnOutcome | None:
        """Recover the durable state of one previously submitted client turn."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.outcomes.get(conversation_id, customer_id, client_turn_id)


class ConversationServiceImpl:
    """Load and persist authenticated conversation state through one transaction per turn.

    Biên ngoài (state/graph) dùng khoá chuỗi; biên trong (repository) dùng
    `SlotName`. Đổi kiểu ở đúng chỗ này, không rải ra node (mục 6.5b).
    """

    def __init__(self, unit_of_work: UnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def open_session(self, session_id: str, customer_id: str) -> None:
        """Mở phiên cho đúng chủ sở hữu trước khi lượt đọc bất cứ thứ gì của phiên.

        Khách gửi thẳng `session_id` tự sinh vào `POST /agent/turn`, nên lượt đầu
        phải tự tạo hàng phiên. `ensure_session` vẫn là chỗ chặn chiếm phiên: nó
        raise khi `customer_id` không khớp chủ hiện tại.
        """

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.ensure_session(session_id, customer_id, None)

    async def load_slots(self, session_id: str, customer_id: str) -> dict[str, SlotValue]:
        """Load persisted slot values for a conversation session."""

        async with self._unit_of_work.transaction() as transaction:
            stored = await transaction.sessions.get_slots(session_id, customer_id)
        return encode_slots(stored)

    async def load_active_offers(self, session_id: str) -> list[dict]:
        async with self._unit_of_work.transaction() as transaction:
            offers = await transaction.session_offers.active_for_session(session_id)
        return [
            {
                "offer_id": str(offer.offer_id),
                "promotion_code": offer.promotion_code,
                "display_name": offer.display_name,
                "value_snapshot": offer.value_snapshot,
                "status": offer.status,
                "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
            }
            for offer in offers
        ]

    async def load_handoff_state(self, session_id: str) -> bool:
        """Phiên có đang chờ NGƯỜI xử lý không (`PENDING_HANDOFF` hoặc `HUMAN`).

        Đầu dò `getattr` ở `chain._handoff_active` đọc method này: cài xong là
        máy trạng thái sở hữu hội thoại `AI → PENDING_HANDOFF → HUMAN → AI` chạy,
        không cần sửa `chain`.
        """

        async with self._unit_of_work.transaction() as transaction:
            ownership = await transaction.sessions.get_ownership(session_id)
        return ownership in {"PENDING_HANDOFF", "HUMAN"}

    async def core_state_exists(self, session_id: str) -> bool:
        """Phiên này đã có trạng thái lõi v2 chưa (spec mục 8).

        Hai lõi KHÔNG chia sẻ trạng thái. Một phiên đã bắt đầu bằng v2 thì phải
        đi hết bằng v2, kể cả khi cờ phần trăm bị hạ xuống giữa chừng — nếu
        không, khách đang ở giữa một câu hỏi treo sẽ rơi sang lõi cũ không biết
        gì về nó.
        """

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.core_state.exists(session_id)

    async def load_core_state(self, session_id: str) -> CoreState | None:
        """Trạng thái lõi v2 của phiên, hoặc `None` ở lượt đầu."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.core_state.load(session_id)

    async def save_core_state(self, state: CoreState) -> None:
        """Ghi trạng thái lõi v2 NGOÀI một lượt chat (đợt 8: thẻ lái thử chọn vị trí).

        Lượt chat ghi state trong `commit_core_turn` cùng transaction với tin
        nhắn; endpoint thẻ không có tin nhắn nào, chỉ có state — nên cần một cửa
        ghi riêng, cùng repository, cùng phép upsert.
        """

        async with self._unit_of_work.transaction() as transaction:
            await transaction.core_state.save(state)

    async def set_handoff_pending(self, session_id: str) -> bool:
        """Đánh dấu phiên vừa vào hàng duyệt, chờ TVV (PENDING_HANDOFF)."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.set_ownership(session_id, "PENDING_HANDOFF")

    async def resolve_handoff(self, session_id: str) -> bool:
        """TVV duyệt/từ chối xong → trả quyền sở hữu phiên về AI."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.set_ownership(session_id, "AI")

    async def record_turn_trace(self, trace: TurnTrace) -> None:
        """Ghi vệt quyết định của một lượt (Sếp 2026-08-26).

        Transaction RIÊNG, chạy sau khi lượt đã chốt: bảng này để quan sát, nên
        nó không được phép kéo theo lượt nào hỏng. `chain` đã bọc lỗi ở chỗ gọi.
        """

        async with self._unit_of_work.transaction() as transaction:
            await transaction.turn_traces.record(trace)

    async def save_turn(self, session_id: str, customer_id: str, slots: Mapping[str, SlotValue]) -> None:
        """Create or refresh an owned session, then replace values supplied by this turn."""

        resolved = coerce_slots(slots)
        vehicle_type_hint = coerce_vehicle_type(resolved.get(SlotName.VEHICLE_TYPE))
        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.ensure_session(session_id, customer_id, vehicle_type_hint)
            for slot_name, value in resolved.items():
                await transaction.sessions.upsert_slot(session_id, slot_name, value)

    async def restart_advisory(self, session_id: str) -> None:
        """Atomically discard advisory slots, retries, pending input, and task focus."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.restart_advisory(session_id)

    async def create_run(self, session_id: str, slots: Mapping[str, SlotValue] | None = None) -> UUID:
        """Create one durable run for a turn that enters retrieval.

        `slots` (khi có) được ghi TRƯỚC khi tạo run, cùng transaction: một slot
        (thường là `vehicle_type`) có thể vừa được suy trong CHÍNH lượt này rồi
        đi thẳng vào retrieve — `save_turn` (điểm ghi cuối lượt) chạy SAU khi
        `graph.ainvoke` (gồm cả node `score` đọc lại slot từ DB) đã kết thúc,
        nên nếu không ghi ở đây thì `score` đọc DB sẽ không thấy giá trị vừa suy.
        """

        resolved = coerce_slots(slots) if slots else {}
        async with self._unit_of_work.transaction() as transaction:
            for slot_name, value in resolved.items():
                await transaction.sessions.upsert_slot(session_id, slot_name, value)
            return await transaction.runs.create_run(session_id)

    async def begin_idempotent_turn(
        self,
        session_id: str,
        customer_id: str,
        client_turn_id: str,
        user_message: str,
    ) -> str | None:
        """Reserve a client turn and return an existing answer on replay.

        The user message is inserted in its own short transaction before the
        graph runs. A unique `(conversation_id, client_turn_id)` index makes
        the reservation durable and prevents duplicate user messages.
        """

        if not client_turn_id.strip():
            raise ValueError("client_turn_id must not be empty")
        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.ensure_session(session_id, customer_id, None)
            existing = await transaction.messages.find_user_by_client_turn(UUID(session_id), client_turn_id)
            if existing is not None:
                answer = await transaction.messages.find_assistant_after(UUID(session_id), existing[1])
                return answer[1] if answer is not None else None
            await transaction.messages.add(
                session_id=UUID(session_id),
                role="USER",
                content=user_message,
                client_turn_id=client_turn_id,
            )
        return None

    async def append_message(
        self,
        session_id: str,
        customer_id: str,
        role: str,
        content: str,
        durable_for_review_id: UUID | None = None,
    ) -> UUID:
        """Append one authenticated durable message to an owned session."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.ensure_session(session_id, customer_id, None)
            return await transaction.messages.add(
                session_id=UUID(session_id),
                role=role,
                content=content,
                durable_for_review_id=durable_for_review_id,
            )

    async def list_messages(self, session_id: str, customer_id: str, limit: int = 100) -> list[ConversationMessage]:
        """Return durable messages after enforcing session ownership."""

        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.get_slots(session_id, customer_id)
            rows = await transaction.messages.list_for_session(UUID(session_id), limit)
        return [ConversationMessage(*row) for row in rows]

    async def list_conversations(self, customer_id: str) -> list[ConversationSummary]:
        """List all customer conversations, newest activity first."""

        async with self._unit_of_work.transaction() as transaction:
            rows = await transaction.sessions.list_owned_sessions(customer_id)
        return [_summary_from_row(row) for row in rows]

    async def delete_conversation(self, session_id: str, customer_id: str) -> bool:
        """Delete one owned conversation and its cascaded state."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.delete_session(UUID(session_id), customer_id)

    async def delete_all_conversations(self, customer_id: str) -> int:
        """Delete every conversation owned by one customer."""

        async with self._unit_of_work.transaction() as transaction:
            rows = await transaction.sessions.list_owned_sessions(customer_id)
            deleted = 0
            for row in rows:
                deleted += int(await transaction.sessions.delete_session(row.session_id, customer_id))
            return deleted

    async def delete_conversation_messages(self, session_id: str, customer_id: str) -> int:
        """Clear transcript content while retaining the session and slots."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.delete_messages(UUID(session_id), customer_id)

    async def archive_conversation(self, session_id: str, customer_id: str) -> bool:
        """Archive one owned conversation."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.archive_session(UUID(session_id), customer_id)

    async def list_staff_conversations(
        self, *, requester_id: str, role: str, customer_id: str | None = None
    ) -> list[ConversationSummary]:
        """List all admin conversations or only advisor-assigned conversations."""

        async with self._unit_of_work.transaction() as transaction:
            rows = await transaction.sessions.list_staff_sessions(
                requester_id=requester_id, role=role, customer_id=customer_id
            )
            return [await _enrich_summary(transaction, row) for row in rows]

    async def staff_conversation_detail(
        self, session_id: str, *, requester_id: str, role: str
    ) -> tuple[ConversationSummary, list[ConversationMessage]] | None:
        """Load full transcript for authenticated staff (admin or advisor)."""

        async with self._unit_of_work.transaction() as transaction:
            row = await transaction.sessions.get_session(UUID(session_id))
            if row is None:
                return None
            if (
                role.lower() != "admin"
                and row.assigned_advisor_id is not None
                and row.assigned_advisor_id != requester_id
            ):
                return None
            messages = await transaction.messages.list_for_session(UUID(session_id), 200)
            summary = await _enrich_summary(transaction, row)
        return summary, [ConversationMessage(*item) for item in messages]

    async def join_advisor(self, session_id: str, advisor_id: str) -> bool:
        """Atomically claim a conversation for the current advisor."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.claim_session(UUID(session_id), advisor_id)

    async def advisor_reply(
        self, session_id: str, advisor_id: str, content: str, client_message_id: str | None = None
    ) -> UUID:
        """Persist one assigned advisor message."""

        async with self._unit_of_work.transaction() as transaction:
            row = await transaction.sessions.get_session(UUID(session_id))
            if row is None:
                raise PermissionError("conversation not found")
            if row.assigned_advisor_id is None or row.assigned_advisor_id != advisor_id:
                await transaction.sessions.claim_session(UUID(session_id), advisor_id)
            return await transaction.messages.add(
                session_id=UUID(session_id),
                role="ADVISOR",
                content=content,
                client_turn_id=client_message_id,
            )

    async def close_advisor_chat(self, session_id: str, advisor_id: str) -> bool:
        """Close an assigned advisor chat."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.close_session(UUID(session_id), advisor_id)

    async def staff_delete_conversation(self, session_id: str) -> bool:
        """Delete a conversation as staff."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.delete_session(UUID(session_id), None)

    async def is_advisor_active(self, session_id: str) -> bool:
        """Kiểm tra xem phiên có tư vấn viên đang phụ trách trực tiếp không."""

        try:
            async with self._unit_of_work.transaction() as transaction:
                row = await transaction.sessions.get_session(UUID(session_id))
                return row is not None and row.assigned_advisor_id is not None and row.status == "ACTIVE"
        except Exception:
            return False

    async def release_to_agent(self, session_id: str) -> bool:
        """Chuyển phiên tư vấn từ Advisor lại cho AI Agent."""

        async with self._unit_of_work.transaction() as transaction:
            released = await transaction.sessions.release_session_to_agent(UUID(session_id))
            if released:
                await transaction.messages.add(
                    session_id=UUID(session_id),
                    role="ASSISTANT",
                    content="Tư vấn viên đã hoàn tất hỗ trợ và chuyển lại cuộc trò chuyện cho trợ lý ảo VinFast. Em có thể hỗ trợ gì tiếp theo cho anh/chị ạ?",
                )
            return released

    async def last_pending_question(
        self, session_id: str, customer_id: str, client_turn_id: UUID | None = None
    ) -> str | None:
        """Lượt gần nhất bot có đặt câu hỏi nào không (Sếp 2026-08-26).

        `classify_scope` dùng để quyết định có cho ba cờ "đây là câu TRẢ LỜI"
        (`customer_declined`, `customer_delegates_choice`,
        `customer_answered_vaguely`) mở cửa phạm vi hay không. Không có câu hỏi
        nào đang chờ thì một lời "từ chối" hay "nhờ chọn hộ" là vô nghĩa — và
        đúng đó là lỗ rò `"tư vấn giúp tôi cách nấu phở"`.

        Đọc `TurnOutcome.pending_question` chứ KHÔNG đọc pending slot: lượt hỏi
        tính năng (`nodes/narrow`) không đăng ký slot nào, mà nó chính là ca bẫy
        3.5 sinh ra để cứu.
        """

        try:
            async with self._unit_of_work.transaction() as transaction:
                outcome = await transaction.outcomes.latest(
                    UUID(session_id),
                    customer_id,
                    # PHẢI loại lượt đang chạy: `chain.run_turn` gọi
                    # `memory.start_turn` từ rất sớm nên hàng của nó đã nằm trong
                    # bảng (chưa có `pending_question`) trước lần đọc này. Không
                    # loại thì "lượt trước" chính là lượt hiện tại và hàm luôn
                    # trả `False` — đo trên prod: 188/188 lượt.
                    exclude_client_turn_id=client_turn_id,
                )
        except Exception:
            # Không đọc được thì coi như CÓ hỏi — chiều an toàn ở đây là để lượt
            # chảy tiếp, vì chặn nhầm làm khách mất câu trả lời. Trả một chuỗi
            # rỗng-nghĩa thay vì `None`: người gọi chỉ cần biết "có hỏi", còn suy
            # mã tính năng từ nó thì ra tập rỗng, không gán bừa cho khách.
            return UNKNOWN_QUESTION
        return outcome.pending_question if outcome is not None else None

    async def load_pending_slot(self, session_id: str) -> dict | None:
        """A7-10: slot đang chờ khách trả lời."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.load_pending_slot(session_id)

    async def save_pending_slot(self, session_id: str, payload: Mapping | None) -> None:
        """A7-10: ghi hoặc xoá pending slot."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.save_pending_slot(session_id, payload)

    async def load_pending_intent_confirmation(self, session_id: str) -> dict | None:
        """Lớp 4: câu xác nhận ý định đang chờ khách trả lời."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.load_pending_intent_confirmation(session_id)

    async def save_pending_intent_confirmation(self, session_id: str, payload: Mapping | None) -> None:
        """Lớp 4: ghi hoặc xoá bản ghi xác nhận ý định."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.save_pending_intent_confirmation(session_id, payload)

    async def load_active_task(self, session_id: str) -> dict | None:
        """Load the focused structured task for cross-turn continuation."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.load_active_task(session_id)

    async def save_active_task(self, session_id: str, payload: Mapping | None) -> None:
        """Persist or clear the focused structured task."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.save_active_task(session_id, payload)

    async def load_quote_decision(self, session_id: str) -> tuple[dict | None, datetime | None]:
        """A7-5: đánh giá của báo giá gần nhất, để lượt xác nhận tái dùng."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.load_quote_decision(session_id)

    async def save_quote_decision(self, session_id: str, evaluation: Mapping[str, object], sent_at: datetime) -> None:
        """A7-5: ghi bộ nhớ báo giá. Chỉ gọi khi lượt vừa dựng đánh giá MỚI."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.save_quote_decision(session_id, evaluation, sent_at)

    async def load_latest_outcome(self, conversation_id: UUID, customer_id: str) -> TurnOutcome | None:
        """Todo 8: outcome gần nhất của phiên — nguồn bằng chứng phản hồi cảm xúc."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.outcomes.latest(conversation_id, customer_id)

    async def load_user_location(self, session_id: str) -> dict | None:
        """Vị trí khách đã chia sẻ trong phiên, hoặc `None`."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.load_user_location(session_id)

    async def save_user_location(self, session_id: str, payload: Mapping | None) -> None:
        """Ghi đè hoặc xoá vị trí khách của phiên."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.save_user_location(session_id, payload)

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> Sequence[TranscriptMessage]:
        """Đọc transcript gần nhất của phiên cho ProfileSnapshotService."""

        async with self._unit_of_work.transaction() as transaction:
            page = await transaction.conversations.read_messages(
                conversation_id=UUID(session_id),
                customer_id=customer_id,
                limit=limit,
                cursor=None,
            )
            return page.items


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """Stable application DTO for a durable message."""

    message_id: UUID
    role: str
    content: str
    client_turn_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Conversation list item shared by customer and staff APIs."""

    session_id: UUID
    customer_id: str
    status: str
    assigned_advisor_id: str | None
    last_activity_at: datetime
    #: `conversation_sessions.ownership`: AI | PENDING_HANDOFF | HUMAN. Danh sách
    #: TVV cần nó để gắn "chờ tư vấn viên" — cột `status` DB chỉ có ACTIVE/COMPLETED.
    ownership: str = "AI"
    #: Đợt 9 — màn TVV với phiên lõi v2: tin cuối (cắt ngắn) và slot đã hiểu
    #: (`conversation_core_state.slots`, khoá chuỗi). Trước đây cả hai rỗng nên
    #: TVV mở danh sách chỉ thấy id và giờ, không biết khách đang cần gì.
    last_message_preview: str = ""
    slots: Mapping[str, Any] = field(default_factory=dict)


#: Trần độ dài dòng xem trước — đủ đọc ý, không kéo cả bài đề xuất vào danh sách.
PREVIEW_MAX_CHARS = 120


async def _enrich_summary(transaction: Any, row: object) -> ConversationSummary:
    """Tóm tắt phiên + tin cuối + slot lõi v2. Thiếu cửa nào (fake/DB cũ) thì bỏ phần đó, không chết."""

    summary = _summary_from_row(row)
    preview = ""
    slots: dict[str, Any] = {}
    latest = getattr(getattr(transaction, "messages", None), "latest_content", None)
    if latest is not None:
        try:
            content = await latest(summary.session_id)
        except Exception:  # noqa: BLE001 — danh sách TVV không được chết vì một dòng xem trước
            content = None
        text = " ".join((content or "").split())
        preview = text if len(text) <= PREVIEW_MAX_CHARS else text[: PREVIEW_MAX_CHARS - 1].rstrip() + "…"
    core_state = getattr(transaction, "core_state", None)
    if core_state is not None:
        try:
            state = await core_state.load(str(summary.session_id))
        except Exception:  # noqa: BLE001
            state = None
        if state is not None:
            slots = {getattr(key, "value", str(key)): value for key, value in state.slots.items()}
    return replace(summary, last_message_preview=preview, slots=slots)


def _summary_from_row(row: object) -> ConversationSummary:
    return ConversationSummary(
        session_id=row.session_id,
        customer_id=row.customer_id,
        status=row.status,
        assigned_advisor_id=row.assigned_advisor_id,
        last_activity_at=row.last_activity_at,
        ownership=str(getattr(row, "ownership", None) or "AI"),
    )


class AskTrackingServiceImpl:
    """Đếm số lần agent đã hỏi từng slot trong một phiên (prompt mục 4)."""

    def __init__(self, unit_of_work: UnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def load_ask_counts(self, session_id: str) -> dict[str, int]:
        """Số lần đã hỏi từng slot, khoá là chuỗi thô cho biên state/graph."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.sessions.get_ask_counts(session_id)

    async def record_ask(self, session_id: str, slot_name: str) -> None:
        """Ghi nhận lượt này vừa hỏi `slot_name`."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.bump_ask_count(session_id, slot_name)

    async def clear_ask(self, session_id: str, slot_name: str) -> None:
        """Khách đã trả lời slot này: đếm về 0 (prompt mục 4)."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.sessions.reset_ask_count(session_id, slot_name)
