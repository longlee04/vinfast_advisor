"""Conversation working-memory use case with best-effort summarization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.agents.contracts import (
    Citation,
    RecommendedVehicleView,
    TurnResult,
    VehicleFacts,
)
from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    ConfirmedBottleneckEvidence,
    SignalInsert,
)
from src.agents.domain.conversation_memory import (
    ConversationSummary,
    CoreTurnLease,
    LeaseAcquired,
    TerminalReplay,
    TurnBusy,
    TurnOutcome,
    TurnOutcomeStatus,
    WorkingMemoryProjection,
    build_working_memory_projection,
    render_working_memory_projection,
    sanitize_summary,
    stabilize_vehicle_summary,
)
from src.agents.domain.turn_result_payload import deserialize_turn_result, serialize_turn_result
from src.agents.domain.turn_trace import TurnTrace
from src.agents.domain.values import SlotValue, VehicleType
from src.agents.errors import TurnFailedError, TurnInProgressError
from src.agents.logging import get_agent_logger
from src.agents.ports import ConversationSummarizerPort, UnitOfWorkPort
from src.agents.services.output_guard import normalize_customer_result
from src.agents.services.slot_codec import coerce_slots

logger = get_agent_logger("agent.services.conversation_memory")


@dataclass(frozen=True, slots=True)
class AdvisorReviewRequest:
    """Một mục hàng duyệt CHỜ được ghi cùng transaction với outcome của lượt.

    `EnqueueHitlNode` dựng nội dung nhưng KHÔNG tự ghi xuống database. Trước đây
    node ghi ngay bằng transaction riêng, còn outcome của lượt được chốt ở một
    transaction sau đó — bước sau hỏng thì mục duyệt thành **mồ côi**: tư vấn
    viên thấy một việc phải làm, khách không có lượt nào ứng với nó, và lần gửi
    lại sinh thêm mục thứ hai. Hoãn việc ghi tới `finalize_turn` khiến hai bản
    ghi hoặc cùng có, hoặc cùng không.
    """

    run_id: UUID
    content: str
    snapshot: object | None = None


@dataclass(frozen=True, slots=True)
class StartedMemoryTurn:
    """Working context or a completed response found by idempotency key."""

    context: str
    replayed_assistant: str | None = None
    replayed_result: TurnResult | None = None
    projection: WorkingMemoryProjection | None = None
    outcome: TurnOutcome | None = None
    anchor_client_turn_id: UUID | None = None
    confirmed_evidence: tuple[ConfirmedBottleneckEvidence, ...] = ()


class ConversationMemoryService:
    """Keep visible transcript durable without holding DB sessions during LLM calls."""

    def __init__(
        self,
        unit_of_work: UnitOfWorkPort,
        summarizer: ConversationSummarizerPort,
        *,
        recent_limit: int = 8,
        max_context_chars: int = 4_000,
        sleep: Callable[[float], Any] | None = None,
        jitter: Callable[[], float] | None = None,
        after_core_turn: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        #: Customer 360 (plan Phase 4): gọi SAU khi lượt đã commit và đã tóm tắt, ngoài
        #: transaction. Hỏng thì log — không bao giờ làm hỏng lượt khách. `None` = không làm gì.
        self._after_core_turn = after_core_turn
        self._summarizer = summarizer
        self._recent_limit = recent_limit
        self._max_context_chars = max_context_chars
        #: `sleep` tách khỏi `asyncio.sleep` để test wait policy bằng fake, không
        #: sleep thật (T1.7/T1.8). Mặc định rỗng `None` → không chờ giữa các lần
        #: retry ngoài test; prod cắm `asyncio.sleep` ở composition.
        self._sleep = sleep
        #: Nhiễu ngẫu nhiên nhỏ giữa hai lần thử giành lượt. Tiêm được để test
        #: chạy tất định (mặc định 0 khi không cắm).
        self._jitter = jitter or (lambda: 0.0)

    async def begin_core_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID,
        wait_timeout_seconds: float = 5.0,
    ) -> LeaseAcquired | TerminalReplay | TurnBusy:
        """Claim lease trước moderation/LLM; wait tối đa 3 lần/5s với backoff+jitter.

        Repository không sleep; vòng lặp nằm ở tầng service này. DB/connectivity
        failure không retry — exception thoát ngay để transport trả 503.
        """

        lease_seconds = 25
        attempts = 0
        deadline = wait_timeout_seconds
        while attempts < 3:
            async with self._unit_of_work.transaction() as transaction:
                acquired = await transaction.outcomes.acquire_core_turn_lease(
                    UUID(session_id),
                    customer_id,
                    client_turn_id,
                    lease_seconds=lease_seconds,
                )
            if isinstance(acquired, CoreTurnLease):
                return LeaseAcquired(acquired)
            if isinstance(acquired, TerminalReplay):
                return acquired
            # LeaseBusy
            attempts += 1
            if attempts >= 3:
                break
            if self._sleep is None:
                continue
            # Ngân sách chờ phải TIÊU DẦN, không phải một con số trang trí: trước
            # đây `deadline` gán 5s rồi giữ nguyên, nên `min(1.0*attempts, deadline)`
            # luôn lấy vế trái và tổng chờ thật chỉ 1+2=3s, khác hẳn luật đã chốt.
            #
            # Nhiễu nhỏ để hai request bấm đúp không va nhau lần thứ hai; tiêm được
            # nên test vẫn tất định.
            delay = min(1.0 * attempts + self._jitter(), deadline)
            if delay <= 0:
                break
            await self._sleep(delay)
            deadline -= delay
        return TurnBusy(
            retry_after_seconds=2,
            recovery_url=f"/api/v1/conversations/{session_id}/turns/{client_turn_id}",
        )

    async def assert_core_turn_lease(self, lease: CoreTurnLease) -> None:
        """Re-check lease ngay trước side-effecting action và trước commit."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.outcomes.assert_core_turn_lease(lease)

    async def start_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID | None,
        user_message: str,
        slots: dict[str, SlotValue],
        pending_features: tuple[str, ...] = (),
        persist_message: bool = True,
    ) -> StartedMemoryTurn:
        """Claim/append a user turn then build working memory outside the transaction.

        `persist_message=False` tách bookkeeping (claim, anchor, evidence) khỏi content:
        lượt vẫn được claim để idempotent, nhưng text KHÔNG ghi vào transcript. Caller
        (chain) gọi `append_user_message` sau khi moderation pass. Dùng cho lượt có thể
        bị chặn (T9 moderation reorder) — nội dung độc không bao giờ nằm transcript.
        """

        if client_turn_id is not None:
            async with self._unit_of_work.transaction() as transaction:
                outcomes = getattr(transaction, "outcomes", None)
                if outcomes is not None:
                    claim = await outcomes.claim(UUID(session_id), customer_id, client_turn_id)
                    if not claim.claimed:
                        if claim.outcome.status is TurnOutcomeStatus.IN_PROGRESS:
                            raise TurnInProgressError()
                        if claim.outcome.status is TurnOutcomeStatus.FAILED:
                            raise TurnFailedError(claim.outcome.error_category)
                        return StartedMemoryTurn(
                            context="",
                            replayed_assistant=claim.outcome.answer or claim.outcome.pending_question,
                            replayed_result=_turn_result(claim.outcome),
                        )
                    current = None
                    if persist_message:
                        current = await transaction.memory.append(
                            session_id,
                            customer_id,
                            "USER",
                            user_message,
                            client_turn_id,
                        )
                    summary, recent = await transaction.memory.load_recent(session_id, customer_id, self._recent_limit)
                    previous = (
                        tuple(message for message in recent if message.turn_index != current.turn_index)
                        if current is not None
                        else tuple(recent)
                    )
                    anchor = await transaction.bottleneck_signals.latest_recommendation_anchor(
                        UUID(session_id), client_turn_id
                    )
                    evidence = (
                        await transaction.bottleneck_signals.confirmed_evidence(UUID(session_id), anchor)
                        if anchor is not None
                        else ()
                    )
                    projection = build_working_memory_projection(
                        slots=slots,
                        summary=summary,
                        recent_messages=previous,
                        pending_features=pending_features,
                        current_user_message=user_message,
                        max_chars=self._max_context_chars,
                    )
                    return StartedMemoryTurn(
                        context=render_working_memory_projection(projection),
                        projection=projection,
                        outcome=claim.outcome,
                        anchor_client_turn_id=anchor,
                        confirmed_evidence=evidence,
                    )
            async with self._unit_of_work.transaction() as transaction:
                existing = await transaction.memory.find_by_client_turn(session_id, customer_id, client_turn_id)
            assistant = next((message.content for message in existing if message.role == "ASSISTANT"), None)
            if assistant is not None:
                return StartedMemoryTurn(context="", replayed_assistant=assistant)

        async with self._unit_of_work.transaction() as transaction:
            current = None
            if persist_message:
                current = await transaction.memory.append(
                    session_id,
                    customer_id,
                    "USER",
                    user_message,
                    client_turn_id,
                )
            summary, recent = await transaction.memory.load_recent(session_id, customer_id, self._recent_limit)
        previous = (
            tuple(message for message in recent if message.turn_index != current.turn_index)
            if current is not None
            else tuple(recent)
        )
        projection = build_working_memory_projection(
            slots=slots,
            summary=summary,
            recent_messages=previous,
            pending_features=pending_features,
            current_user_message=user_message,
            max_chars=self._max_context_chars,
        )
        return StartedMemoryTurn(
            context=render_working_memory_projection(projection),
            projection=projection,
        )

    async def append_user_message(
        self,
        *,
        session_id: str,
        customer_id: str,
        user_message: str,
        client_turn_id: UUID | None,
    ) -> None:
        """Persist a user message that already passed moderation (T9 reorder).

        `start_turn(..., persist_message=False)` đã claim lượt; hàm này ghi text vào
        transcript sau khi moderation pass. Lượt bị chặn không bao giờ gọi tới đây.
        """

        async with self._unit_of_work.transaction() as transaction:
            await transaction.memory.append(
                session_id,
                customer_id,
                "USER",
                user_message,
                client_turn_id,
            )

    async def finalize_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID,
        user_message: str,
        result: TurnResult,
        slots: dict[str, SlotValue],
        advisor_review: AdvisorReviewRequest | None = None,
    ) -> TurnResult:
        """Atomically persist slots, exact outcome and only a final visible response.

        `advisor_review` khác `None` thì mục hàng duyệt được ghi TRONG CÙNG
        transaction này và `review_id` sinh ra đi thẳng vào outcome — mục duyệt và
        lượt của khách không bao giờ tồn tại lệch nhau.
        """

        delivered = _delivered_content(result)
        assistant = None
        review_id = result.review_id
        status = (
            TurnOutcomeStatus.WAITING_REVIEW
            if result.awaiting_review or review_id is not None or advisor_review is not None
            else TurnOutcomeStatus.COMPLETED
        )
        async with self._unit_of_work.transaction() as transaction:
            if advisor_review is not None:
                review_id = await transaction.review_queue.enqueue(
                    advisor_review.run_id,
                    UUID(session_id),
                    advisor_review.content,
                    snapshot=advisor_review.snapshot,
                )
            resolved = coerce_slots(slots)
            for slot_name, value in resolved.items():
                await transaction.sessions.upsert_slot(session_id, slot_name, value)
            if status is TurnOutcomeStatus.COMPLETED and delivered is not None:
                assistant = await transaction.memory.append(
                    session_id,
                    customer_id,
                    "ASSISTANT",
                    delivered,
                    client_turn_id,
                )
            # Legacy path không có lease: turn_number lấy từ outcome đã claim.
            existing = await transaction.outcomes.get(UUID(session_id), customer_id, client_turn_id)
            existing_turn_number = existing.turn_number if existing is not None else 1
            outcome = TurnOutcome(
                conversation_id=UUID(session_id),
                client_turn_id=client_turn_id,
                turn_number=existing_turn_number,
                status=status,
                answer=result.answer,
                pending_question=result.pending_question,
                terminal_reason=result.terminal_reason,
                lookup_facts=tuple(_fact_payload(fact) for fact in result.lookup_facts),
                recommendations=tuple(_recommendation_payload(item) for item in result.recommendations),
                result_payload=serialize_turn_result(
                    _redact_unapproved(
                        normalize_customer_result(
                            replace(
                                result,
                                review_id=review_id,
                                awaiting_review=review_id is not None,
                                turn_status=status.value,
                            )
                        ),
                        waiting_review=status is TurnOutcomeStatus.WAITING_REVIEW,
                    )
                ),
                review_id=review_id,
                message_id=assistant.message_id if assistant is not None else None,
            )
            finalized = await transaction.outcomes.finalize(outcome)
            detection = result.bottleneck_detection
            anchor = result.bottleneck_anchor_client_turn_id
            if isinstance(detection, BottleneckDetected) and anchor is not None:
                await transaction.bottleneck_signals.insert(
                    SignalInsert(
                        session_id=UUID(session_id),
                        client_turn_id=client_turn_id,
                        anchor_client_turn_id=anchor,
                        label=detection.label,
                        evidence_quote=detection.evidence_quote,
                        model_name=detection.model_name,
                        prompt_version=detection.prompt_version,
                    )
                )
            if assistant is not None:
                previous_summary, recent = await transaction.memory.load_recent(
                    session_id, customer_id, self._recent_limit
                )
            else:
                previous_summary, recent = None, ()
        if assistant is not None:
            await self._update_summary(
                session_id=session_id,
                customer_id=customer_id,
                user_message=user_message,
                delivered_assistant=delivered or "",
                assistant_turn_index=assistant.turn_index,
                previous_summary=previous_summary,
                recent=recent,
            )
        return _turn_result(finalized)

    async def commit_core_turn(
        self,
        *,
        lease: CoreTurnLease,
        customer_id: str,
        user_message: str,
        result: TurnResult,
        core_state: object,
        trace: TurnTrace,
        advisor_review: AdvisorReviewRequest | None = None,
        ownership_transition: object | None = None,
        retry_context: object | None = None,
    ) -> TurnResult:
        """Chốt MỘT lượt của lõi v2 trong MỘT transaction (spec mục 4 + 7).

        `lease` mang session_id, client_turn_id, turn_number. USER message được
        ghi TRONG transaction này, cùng lúc với ASSISTANT/outcome/state/trace —
        không còn `_persist_user_message` riêng trước act (PR1 T2).

        `advisor_review` giữ cho đường HITL hiện tại; PR2 (T4) sẽ thay bằng
        `ownership_transition`.

        Khác `finalize_turn` đúng hai việc: ghi thêm `conversation_core_state` và
        `turn_traces` **bên trong** cùng transaction. Đó là cả lý do phương thức
        này tồn tại: `ConversationServiceImpl.record_turn_trace` cố ý mở
        transaction RIÊNG (bảng quan sát của lõi cũ, không được làm hỏng lượt),
        còn lõi v2 cần vệt và trạng thái cùng có hoặc cùng không — hàng state ghi
        được mà vệt mất là mất luôn khả năng giải thích lượt đó.

        Vệt nằm TRONG transaction nên nó cũng làm hỏng được lượt. Đánh đổi có
        chủ ý và chỉ trong giai đoạn chạy song song: `conversation_core_state`
        ghi được mà `turn_traces` mất thì bộ đo ở bước 4 đọc ra một lịch sử có lỗ
        và kết luận sai về việc lõi v2 thắng hay thua.
        """

        session_id = str(lease.session_id)
        client_turn_id = lease.client_turn_id
        turn_number = lease.turn_number
        delivered = _delivered_content(result)
        assistant = None
        review_id = result.review_id
        status = (
            TurnOutcomeStatus.WAITING_REVIEW
            if result.awaiting_review or review_id is not None or advisor_review is not None
            else TurnOutcomeStatus.COMPLETED
        )
        async with self._unit_of_work.transaction() as transaction:
            # HÀNG RÀO chống thợ cũ: kiểm lease NGAY TRONG transaction ghi, trước
            # dòng chữ đầu tiên. Kiểm ở ngoài (`assert_core_turn_lease` riêng) chỉ
            # là lớp chặn sớm — giữa lúc kiểm xong và lúc ghi, lease có thể đã hết
            # hạn và bị lượt khác giành mất; khi đó thợ cũ vẫn ghi đè USER/
            # ASSISTANT/state/vệt của thợ mới. Kiểm trong CÙNG transaction thì
            # lease hỏng là cả khối cùng quay đầu, không sót một dòng nào.
            await transaction.outcomes.assert_core_turn_lease(lease)
            # Ghi USER message TRONG transaction — không còn _persist_user_message riêng.
            await transaction.memory.append(session_id, customer_id, "USER", user_message, client_turn_id)
            if advisor_review is not None:
                review_id = await transaction.review_queue.enqueue(
                    advisor_review.run_id,
                    UUID(session_id),
                    advisor_review.content,
                    snapshot=advisor_review.snapshot,
                )
            for slot_name, value in coerce_slots(core_state.slots).items():
                await transaction.sessions.upsert_slot(session_id, slot_name, value)
            if delivered is not None:
                assistant = await transaction.memory.append(
                    session_id, customer_id, "ASSISTANT", delivered, client_turn_id
                )
            outcome = TurnOutcome(
                conversation_id=UUID(session_id),
                client_turn_id=client_turn_id,
                turn_number=turn_number,
                status=status,
                answer=result.answer,
                pending_question=result.pending_question,
                terminal_reason=result.terminal_reason,
                lookup_facts=tuple(_fact_payload(fact) for fact in result.lookup_facts),
                recommendations=tuple(_recommendation_payload(item) for item in result.recommendations),
                result_payload=serialize_turn_result(
                    _redact_unapproved(
                        normalize_customer_result(
                            replace(
                                result,
                                review_id=review_id,
                                awaiting_review=review_id is not None,
                                turn_status=status.value,
                            )
                        ),
                        waiting_review=status is TurnOutcomeStatus.WAITING_REVIEW,
                    )
                ),
                review_id=review_id,
                message_id=assistant.message_id if assistant is not None else None,
            )
            finalized = await transaction.outcomes.finalize(outcome)
            await transaction.core_state.save(core_state)
            await transaction.turn_traces.record(trace)
            if assistant is not None:
                previous_summary, recent = await transaction.memory.load_recent(
                    session_id, customer_id, self._recent_limit
                )
            else:
                previous_summary, recent = None, ()
        if assistant is not None:
            await self._update_summary_best_effort(
                session_id=session_id,
                customer_id=customer_id,
                user_message=user_message,
                delivered_assistant=delivered or "",
                assistant_turn_index=assistant.turn_index,
                previous_summary=previous_summary,
                recent=recent,
            )
        await self._notify_after_core_turn(session_id, customer_id, core_state.turn_count)
        return replace(_turn_result(finalized), review_id=review_id, awaiting_review=review_id is not None)

    async def notify_turn_committed(self, *, session_id: str, customer_id: str, turn_count: int) -> None:
        """Báo việc nền (Customer 360) rằng một lượt đã lưu xong — cho CẢ đường lưu cũ.

        Route `/agent/turn` mà frontend gọi đi đường `finalize_turn` (không lease), không qua
        `commit_core_turn`; trước đây móc chỉ nằm trong `commit_core_turn` nên khách chat thật
        KHÔNG bao giờ được gắn cơ hội/lưu hồ sơ (lượt dev 2026-09-24, plan §21).
        """

        await self._notify_after_core_turn(session_id, customer_id, turn_count)

    async def _notify_after_core_turn(self, session_id: str, customer_id: str, turn_count: int) -> None:
        if self._after_core_turn is None:
            return
        try:
            await self._after_core_turn(session_id=session_id, customer_id=customer_id, turn_count=turn_count)
        except Exception:  # noqa: BLE001 — việc nền của TVV không được chạm tới khách
            logger.warning("commit_core_turn: hook customer360 that bai", exc_info=True)

    async def _update_summary_best_effort(
        self,
        *,
        session_id: str,
        customer_id: str,
        user_message: str,
        delivered_assistant: str,
        assistant_turn_index: int,
        previous_summary: ConversationSummary | None,
        recent: tuple,
    ) -> None:
        """Tóm tắt hội thoại — chạy SAU transaction, hỏng thì ghi log chứ không ném.

        Món nợ I5 của bước 3: `commit_core_turn` không đụng `conversation_summaries`
        chút nào, trong khi `finalize_turn` (lõi cũ) vẫn cập nhật mỗi lượt. Hậu quả
        chỉ lộ ở phiên DÀI: `start_turn` dựng ngữ cảnh từ `summary` + N tin nhắn
        gần nhất, nên phiên lõi v2 quá N lượt là quên sạch phần đầu — im lặng, và
        chỉ thấy được khi khách hỏi lại một thứ đã nói.

        Cả hai lõi cập nhật tóm tắt theo CÙNG một cách: best-effort, SAU khi
        transaction của lượt đã commit — `finalize_turn` cũng gọi `_update_summary`
        bên NGOÀI khối `async with` của nó. Khác biệt trước bản vá này chỉ là lõi
        v2 không gọi gì cả, không phải là hai lõi đặt tóm tắt ở hai chỗ khác nhau.

        NGOÀI transaction là chủ ý, y như `finalize_turn`: tóm tắt gọi LLM, mà giữ
        một transaction Postgres mở suốt một lần gọi mạng là cách chắc nhất để
        khoá hàng và cạn pool. Lượt đã chốt xong rồi; tóm tắt hỏng thì lượt sau
        vẫn đọc được các tin nhắn chưa tóm tắt.
        """

        try:
            await self._update_summary(
                session_id=session_id,
                customer_id=customer_id,
                user_message=user_message,
                delivered_assistant=delivered_assistant,
                assistant_turn_index=assistant_turn_index,
                previous_summary=previous_summary,
                recent=recent,
            )
        except Exception:
            logger.warning("commit_core_turn: cap nhat tom tat that bai", exc_info=True)

    async def fail_turn(
        self,
        *,
        session_id: str,
        client_turn_id: UUID,
        error_category: str,
    ) -> None:
        """Persist only a safe failure category for a claimed turn."""

        async with self._unit_of_work.transaction() as transaction:
            await transaction.outcomes.fail(UUID(session_id), client_turn_id, error_category=error_category)

    async def complete_turn(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID | None,
        user_message: str,
        delivered_assistant: str,
    ) -> None:
        """Persist delivered output, then update summary without risking chat delivery."""

        async with self._unit_of_work.transaction() as transaction:
            assistant = await transaction.memory.append(
                session_id,
                customer_id,
                "ASSISTANT",
                delivered_assistant,
                client_turn_id,
            )
            previous_summary, recent = await transaction.memory.load_recent(session_id, customer_id, self._recent_limit)
        await self._update_summary(
            session_id=session_id,
            customer_id=customer_id,
            user_message=user_message,
            delivered_assistant=delivered_assistant,
            assistant_turn_index=assistant.turn_index,
            previous_summary=previous_summary,
            recent=recent,
        )

    async def _update_summary(
        self,
        *,
        session_id: str,
        customer_id: str,
        user_message: str,
        delivered_assistant: str,
        assistant_turn_index: int,
        previous_summary: ConversationSummary | None,
        recent: tuple,
    ) -> None:
        previous_parts = [previous_summary.content] if previous_summary is not None else []
        current_user_turn = max(
            (
                message.turn_index
                for message in recent
                if message.role == "USER" and message.turn_index < assistant_turn_index
            ),
            default=assistant_turn_index,
        )
        unsummarized_prefix = [message for message in recent if message.turn_index < current_user_turn]
        if unsummarized_prefix:
            previous_parts.append(
                "Tin nhắn chưa tóm tắt:\n"
                + "\n".join(f"{message.role}: {message.content}" for message in unsummarized_prefix)
            )
        previous = "\n\n".join(previous_parts)
        try:
            candidate = await self._summarizer.summarize(
                previous_summary=previous,
                user_message=user_message,
                assistant_response=delivered_assistant,
            )
            cleaned = sanitize_summary(
                candidate,
                source_text=f"{previous}\n{user_message}\n{delivered_assistant}",
            )
            cleaned = stabilize_vehicle_summary(
                candidate=cleaned,
                previous_summary=previous,
                user_message=user_message,
            )
            if not cleaned:
                return
            summary = ConversationSummary(
                cleaned,
                assistant_turn_index,
                model_name=str(getattr(self._summarizer, "model_name", "unspecified")),
            )
            async with self._unit_of_work.transaction() as transaction:
                await transaction.memory.save_summary(session_id, customer_id, summary)
        except (TimeoutError, RuntimeError, ValueError):
            # Transcript is already durable. The next turn can still use unsummarized messages.
            return


def _delivered_content(result: TurnResult) -> str | None:
    if result.answer:
        return result.answer
    if result.pending_question:
        return result.pending_question
    if result.lookup_facts:
        rendered: list[str] = []
        for vehicle in result.lookup_facts:
            price = (
                str(vehicle.starting_price_vnd) if vehicle.starting_price_vnd is not None else "chưa có giá hiệu lực"
            )
            rendered.append(f"{vehicle.display_name}: {price}")
        return "; ".join(rendered)
    return None


def _fact_payload(fact: VehicleFacts) -> dict[str, object]:
    return {
        "vehicle_id": str(fact.vehicle_id),
        "display_name": fact.display_name,
        "vehicle_type": fact.vehicle_type.value,
        "starting_price_vnd": (str(fact.starting_price_vnd) if fact.starting_price_vnd is not None else None),
        "specs": dict(fact.specs),
    }


def _recommendation_payload(view: RecommendedVehicleView) -> dict[str, object]:
    return {
        "vehicle_id": str(view.vehicle_id),
        "rank": view.rank,
        "display_name": view.display_name,
        "image_url": view.image_url,
        "starting_price_vnd": view.starting_price_vnd,
        "pitch": view.pitch,
        "citations": [
            {
                "index": citation.index,
                "evidence_id": str(citation.evidence_id),
                "source_record": citation.source_record,
            }
            for citation in view.citations
        ],
    }


def _recommendation_view(payload: Mapping[str, object]) -> RecommendedVehicleView | None:
    try:
        citations = tuple(
            Citation(
                index=int(citation["index"]),
                evidence_id=UUID(str(citation["evidence_id"])),
                source_record=str(citation["source_record"]),
            )
            for citation in payload.get("citations") or ()
        )
    except (KeyError, TypeError, ValueError):
        return None
    try:
        return RecommendedVehicleView(
            vehicle_id=UUID(str(payload["vehicle_id"])),
            rank=int(payload["rank"]),
            display_name=str(payload["display_name"]),
            image_url=payload.get("image_url") if isinstance(payload.get("image_url"), str) else None,
            starting_price_vnd=(
                payload.get("starting_price_vnd") if isinstance(payload.get("starting_price_vnd"), str) else None
            ),
            pitch=str(payload["pitch"]),
            citations=citations,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _redact_unapproved(result: TurnResult, *, waiting_review: bool) -> TurnResult:
    """Bài chào bán CHƯA QUA DUYỆT không được rời hệ — kể cả trong `result_payload`.

    Trước [PR1 T3] chỉ đường replay che pitch (`_turn_result`), vì replay dựng lại
    kết quả từ cột typed. Nay `result_payload` giữ nguyên văn khách nhìn thấy và
    replay ĐỌC NÓ TRƯỚC, nên bài chưa duyệt persist thô là ra thẳng tới khách.

    Che tại chỗ GHI chứ không chỉ chỗ đọc: payload đã sạch thì mọi đường đọc sau
    này (replay, recovery HTTP, HITL refresh) đều an toàn mà không phải nhớ gọi
    lại phép chiếu.
    """

    if not waiting_review and not result.terminal_reason:
        return result
    return replace(
        result,
        recommendations=[replace(view, pitch="", citations=()) for view in result.recommendations],
    )


def _turn_result(outcome: TurnOutcome) -> TurnResult:
    if outcome.result_payload is not None:
        return normalize_customer_result(deserialize_turn_result(outcome.result_payload, outcome))
    facts: list[VehicleFacts] = []
    for payload in outcome.lookup_facts:
        try:
            raw_price = payload.get("starting_price_vnd")
            facts.append(
                VehicleFacts(
                    vehicle_id=UUID(str(payload["vehicle_id"])),
                    display_name=str(payload["display_name"]),
                    vehicle_type=VehicleType(str(payload["vehicle_type"])),
                    starting_price_vnd=(Decimal(str(raw_price)) if raw_price is not None else None),
                    specs=dict(payload.get("specs") or {}),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    recommendations = [
        view for payload in outcome.recommendations if (view := _recommendation_view(payload)) is not None
    ]
    # Cùng phép chiếu với đường GHI (`_redact_unapproved`): outcome cũ persist
    # TRƯỚC khi chỗ ghi biết che vẫn phải sạch khi đọc lại.
    # [Todo 9] Project ở biên replay: outcome cũ persist TRƯỚC mapper (raw) vẫn
    # phải trả bản sạch, đọc được cho khách. Idempotent nên outcome đã project
    # (đường finalize_turn mới) không đổi gì.
    return _redact_unapproved(
        normalize_customer_result(
            TurnResult(
                session_id=str(outcome.conversation_id),
                answer=outcome.answer,
                pending_question=outcome.pending_question,
                terminal_reason=outcome.terminal_reason,
                lookup_facts=facts,
                awaiting_review=outcome.status is TurnOutcomeStatus.WAITING_REVIEW,
                review_id=outcome.review_id,
                turn_status=outcome.status.value,
                recommendations=recommendations,
            )
        ),
        waiting_review=outcome.status is TurnOutcomeStatus.WAITING_REVIEW,
    )
