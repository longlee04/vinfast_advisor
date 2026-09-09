"""Chuyển một lượt sang tư vấn viên trong ĐÚNG MỘT giao dịch.

Trước đây ba việc — tạo run, đẩy hàng đợi duyệt, chốt outcome — nằm ở ba chỗ gọi
khác nhau. Hỏng giữa chừng để lại một mục duyệt **mồ côi**: tư vấn viên thấy việc
cần làm, còn khách không có lượt nào ứng với nó, và lần gửi lại sinh ra mục thứ
hai. Gói cả ba vào một `transaction()` nên hoặc có đủ, hoặc không có gì.

Ba đường vào hàng duyệt, nhưng chỉ còn HAI transaction, và mỗi đường nguyên tử:

- **Trước LLM và ngữ nghĩa** — `handoff()` dưới đây: chưa có outcome nào cho lượt,
  nên nó tạo run + mục duyệt + outcome cùng lúc.
- **Guardrail cạn lượt** — lượt đã chạy hết graph và `chain` sắp chốt outcome, nên
  mục duyệt được ghi TRONG transaction đó (`ConversationMemoryService.finalize_turn`
  nhận `AdvisorReviewRequest`). `EnqueueHitlNode` không còn chạm database.
- **Đường không có `client_turn_id`** (cũ, `client_turn_id` là field tuỳ chọn của
  API) — không có outcome để ghi kèm, nên `enqueue_review()` ghi một mình.

`DefaultHitlQueueService` đã bị gỡ: nó là cơ chế thứ hai ghi cùng một bảng bằng
một transaction rời, và chính nó để lại mục duyệt mồ côi khi bước chốt outcome
ngay sau đó hỏng.

Hai loại nội dung KHÔNG được lẫn:

- `advisor_content` — thứ tư vấn viên đọc. Với chốt trước LLM đó là lý do có kiểu
  cộng nguyên văn câu khách; với guardrail đó là bản nháp chưa kiểm chứng.
- câu khách đọc — luôn là một câu an toàn cố định, không bao giờ mang
  `advisor_content`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus
from src.agents.domain.values import HitlReason

if TYPE_CHECKING:
    from src.agents.ports import UnitOfWorkPort

#: Câu DUY NHẤT khách đọc khi lượt được chuyển người. Cố định, không mang bất kỳ
#: mảnh nội dung nội bộ nào — đây là chốt chặn cuối chống rò bản nháp.
HANDOFF_MESSAGE = (
    "Phần này anh tư vấn viên hỗ trợ tốt hơn ạ. Em chuyển Quý khách qua bạn em — Quý khách đợi em chút nhé."
)


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Kết quả một lần chuyển người, đủ để `chain` dựng `TurnResult`."""

    review_id: UUID | None
    answer: str
    awaiting_review: bool = True
    #: Luôn `None`. Chuyển người KHÔNG phải kết thúc lượt vì lỗi — đặt
    #: `terminal_reason` sẽ khiến đường trên rẽ vào nhánh chết.
    terminal_reason: str | None = None
    replayed: bool = False


class TurnHandoffService:
    """Điểm DUY NHẤT ghi một lần chuyển người xuống database."""

    def __init__(self, unit_of_work: UnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def handoff(
        self,
        *,
        session_id: str,
        customer_id: str,
        client_turn_id: UUID | None,
        reason: HitlReason,
        customer_message: str,
        advisor_content: str,
        run_id: UUID | None = None,
        snapshot: object | None = None,
    ) -> HandoffResult:
        """Ghi run + mục duyệt + outcome trong một transaction, hoặc không gì cả.

        `client_turn_id` khác `None` thì lượt đã chốt trước đó được **phát lại**:
        trả đúng `review_id` cũ và không ghi thêm gì. Không có khoá thì hành vi
        là best-effort — ở đây không hứa đúng-một-lần.
        """

        async with self._unit_of_work.transaction() as transaction:
            turn_number: int | None = None
            if client_turn_id is not None:
                claim = await transaction.outcomes.claim(UUID(session_id), customer_id, client_turn_id)
                if not claim.claimed:
                    # Lượt đã xong từ trước: phát lại y nguyên, tuyệt đối không
                    # tạo mục duyệt thứ hai cho cùng một câu của khách.
                    return HandoffResult(
                        review_id=claim.outcome.review_id,
                        answer=claim.outcome.answer or HANDOFF_MESSAGE,
                        awaiting_review=True,
                        replayed=True,
                    )
                # Số lượt lấy từ outcome vừa claim — không bao giờ hard-code 1.
                turn_number = claim.outcome.turn_number

            resolved_run = run_id
            if resolved_run is None:
                resolved_run = await transaction.runs.create_run(session_id)

            review_id = await transaction.review_queue.enqueue(
                resolved_run,
                UUID(session_id),
                advisor_content,
                snapshot=snapshot,
            )

            if client_turn_id is not None:
                assert turn_number is not None
                await transaction.outcomes.finalize(
                    TurnOutcome(
                        conversation_id=UUID(session_id),
                        client_turn_id=client_turn_id,
                        turn_number=turn_number,
                        status=TurnOutcomeStatus.WAITING_REVIEW,
                        answer=HANDOFF_MESSAGE,
                        review_id=review_id,
                    )
                )

            return HandoffResult(review_id=review_id, answer=HANDOFF_MESSAGE)

    async def enqueue_review(
        self,
        *,
        session_id: str,
        advisor_content: str,
        run_id: UUID | None = None,
        snapshot: object | None = None,
    ) -> UUID:
        """Ghi MỘT mục duyệt, không chạm outcome.

        Chỉ dành cho lượt không có `client_turn_id` — ở đó không tồn tại outcome
        để ghi kèm, nên "nguyên tử cùng outcome" là một lời hứa không có nội dung.
        Mọi lượt có khoá lượt đều đi qua transaction chốt outcome thay vì hàm này.
        """

        async with self._unit_of_work.transaction() as transaction:
            resolved_run = run_id
            if resolved_run is None:
                resolved_run = await transaction.runs.create_run(session_id)
            return await transaction.review_queue.enqueue(
                resolved_run,
                UUID(session_id),
                advisor_content,
                snapshot=snapshot,
            )


__all__ = ["HANDOFF_MESSAGE", "HandoffResult", "TurnHandoffService"]
