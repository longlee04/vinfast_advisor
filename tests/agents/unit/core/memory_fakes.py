"""Fake `ConversationMemoryServicePort` TRUNG THỰC cho test lõi v2.

Vì sao cần: mọi fake `commit_core_turn` trước đây chỉ ghi lại `kwargs` rồi trả
`result` về. Chúng vì thế bỏ qua ĐÚNG cái thứ hàng thật làm — dựng một
`TurnOutcome` và để `__post_init__` soát. Kết quả là bước 3 giao đi một lỗi mà
5000 test đơn vị đều xanh: lượt `Silent` (TVV đang cầm phiên) trả
`answer=None, terminal_reason=None, status=COMPLETED`, và hàng thật ném
`ValueError: completed turn outcome requires a customer result` — tức MỌI lượt
trong phiên HITL đều chết ở bước ghi.

`HonestMemory` chép đúng ba phép hàng thật làm trước khi chạm database
(`ConversationMemoryService.commit_core_turn`): chọn `status`, rút nội dung đã
gửi khách, dựng `TurnOutcome`. Không chép phần I/O — đó là việc của test tích hợp.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.agents.contracts import TurnResult
from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus
from src.agents.errors import CoreTurnLeaseStaleError
from src.agents.services.conversation_memory import StartedMemoryTurn

#: Chín trường sống sót qua `agent_turn_outcomes`. Mọi thẻ khác rơi mất trên
#: đường về — đúng lý do `_restore_turn_fields` tồn tại.
PERSISTED_FIELDS: tuple[str, ...] = (
    "session_id",
    "answer",
    "pending_question",
    "terminal_reason",
    "lookup_facts",
    "awaiting_review",
    "review_id",
    "turn_status",
    "recommendations",
)


def delivered_content(result: TurnResult) -> str | None:
    """Bản sao `conversation_memory._delivered_content` — `answer` trước, rồi `pending_question`."""

    if result.answer:
        return result.answer
    if result.pending_question:
        return result.pending_question
    return None


def build_outcome(
    *, session_id: str, client_turn_id: UUID, result: TurnResult, review_id: UUID | None, turn_number: int = 1
) -> TurnOutcome:
    """Dựng đúng `TurnOutcome` mà `commit_core_turn` dựng — để `__post_init__` chạy."""

    status = (
        TurnOutcomeStatus.WAITING_REVIEW
        if result.awaiting_review or review_id is not None
        else TurnOutcomeStatus.COMPLETED
    )
    return TurnOutcome(
        conversation_id=UUID(session_id),
        client_turn_id=client_turn_id,
        turn_number=turn_number,
        status=status,
        answer=result.answer,
        pending_question=result.pending_question,
        terminal_reason=result.terminal_reason,
        lookup_facts=(),
        recommendations=(),
        review_id=review_id,
    )


class HonestMemory:
    """Ghi lại lượt VÀ soát nó đúng cách hàng thật soát."""

    def __init__(self) -> None:
        self.committed: list[dict[str, Any]] = []
        self.outcomes: list[TurnOutcome] = []
        self.appended: list[str] = []
        self.persist_flags: list[bool] = []
        self.finalized: list[dict[str, Any]] = []
        self.assert_lease_calls: list[Any] = []
        self.fail_lease_assert = False
        self.fail_lease_on_call: int | None = None
        self.lease_assert_reason = "token_replaced"

    async def assert_core_turn_lease(self, lease: Any) -> None:
        self.assert_lease_calls.append(lease)
        should_fail = self.fail_lease_assert or (
            self.fail_lease_on_call is not None and len(self.assert_lease_calls) == self.fail_lease_on_call
        )
        if should_fail:
            raise CoreTurnLeaseStaleError(
                session_id=str(lease.session_id),
                client_turn_id=str(lease.client_turn_id),
                reason=self.lease_assert_reason,
            )

    async def start_turn(self, **kwargs: Any) -> StartedMemoryTurn:
        self.persist_flags.append(bool(kwargs.get("persist_message", True)))
        return StartedMemoryTurn(context="")

    async def append_user_message(self, *, user_message: str, **_kwargs: Any) -> None:
        self.appended.append(user_message)

    async def commit_core_turn(self, **kwargs: Any) -> TurnResult:
        self.committed.append(kwargs)
        result: TurnResult = kwargs["result"]
        lease: Any = kwargs.get("lease")
        if lease is not None:
            session_id = str(lease.session_id)
            client_turn_id = lease.client_turn_id
            turn_number = lease.turn_number
        else:
            session_id = kwargs["session_id"]
            client_turn_id = kwargs["client_turn_id"]
            turn_number = 1
        self.outcomes.append(
            build_outcome(
                session_id=session_id,
                client_turn_id=client_turn_id,
                result=result,
                review_id=result.review_id,
                turn_number=turn_number,
            )
        )
        # [PR1 T2] USER message ghi TRONG transaction commit — đúng thật commit_core_turn
        # append USER qua `transaction.memory.append`.
        self.appended.append(kwargs["user_message"])
        # Chỉ chín trường sống sót — giữ nguyên hình dạng fake cũ của bước 3.
        return TurnResult(**{name: getattr(result, name) for name in PERSISTED_FIELDS})

    async def finalize_turn(self, **kwargs: Any) -> TurnResult:
        self.finalized.append(kwargs)
        return kwargs["result"]


__all__ = ["PERSISTED_FIELDS", "HonestMemory", "build_outcome", "delivered_content"]
