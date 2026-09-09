"""[Lớp 4] Tiêu thụ câu trả lời của khách cho một câu xác nhận ý định.

Chạy TRƯỚC `classify_scope` và trước cả bước trích slot, cùng chỗ và cùng lý do
với A7-10 (`services/pending_slot.py`): "đúng rồi" đứng riêng là một tin nhắn hai
chữ không khớp intent nào, và guardrail phạm vi sẽ gắn `OUT_OF_SCOPE` rồi kết
thúc lượt. Guardrail không sai — nó chỉ không biết câu đó đang trả lời cái gì.

Khác A7-10 ở một điểm quyết định: khi khách xác nhận, lượt KHÔNG dừng lại. Câu
"đúng" của khách được thay bằng câu hệ thống đã suy ra, rồi lượt chạy tiếp toàn
bộ pipeline như thể khách vừa gõ câu đó. Dừng ở đây sẽ khiến khách gật đầu xong
không nhận được câu trả lời nào.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.pending_intent_confirmation import (
    ConfirmationAnswer,
    ConfirmationResolution,
    PendingIntentConfirmation,
    read_confirmation,
)
from src.agents.logging import get_agent_logger
from src.agents.prompts.nlu_replies import clarify_message

logger = get_agent_logger("agent.nlu.confirmation")


@dataclass(slots=True)
class PendingIntentConfirmationServiceImpl:
    """Đọc bản ghi xác nhận đang chờ và quyết định lượt này đi đâu."""

    #: Mẫu xe gợi ý khi khách phủ nhận suy đoán. Truyền vào chứ không tự dựng:
    #: danh sách này phải khớp với thứ `NluPipelineServiceImpl` đang gợi ý, và
    #: nguồn của nó là danh mục catalog chứ không phải một hằng số ở đây.
    suggestions: tuple[str, ...] = ()

    def resolve(
        self,
        *,
        payload: Mapping[str, object] | None,
        user_message: str,
        canonical: CanonicalText,
        now: datetime | None = None,
    ) -> ConfirmationResolution:
        """Quyết định lượt này có phải câu trả lời cho câu xác nhận vừa đặt không."""

        pending = PendingIntentConfirmation.from_payload(payload)
        if pending is None:
            return ConfirmationResolution()

        moment = now or datetime.now(UTC)
        if pending.is_expired(moment):
            # Hết hạn dọn NGAY LÚC ĐỌC, không cần cron — cùng cách A7-10 làm.
            logger.info("confirmation het han, da xoa: %r", pending.proposed_text[:80])
            return ConfirmationResolution(clear_pending=True)

        answer = read_confirmation(user_message, canonical)
        if answer is ConfirmationAnswer.AFFIRMED:
            logger.info("confirmation duoc xac nhan: %r", pending.proposed_text[:80])
            return ConfirmationResolution(substitute_message=pending.proposed_text, clear_pending=True)
        if answer is ConfirmationAnswer.DENIED:
            # Hiểu sai thì hỏi lại bằng câu MỞ, không đề xuất tiếp một suy đoán
            # thứ hai từ cùng bộ bằng chứng vừa bị bác — bằng chứng không đổi
            # thì suy đoán thứ hai cũng sai theo đúng kiểu đó.
            logger.info("confirmation bi phu nhan: %r", pending.proposed_text[:80])
            return ConfirmationResolution(reply=clarify_message(self.suggestions), clear_pending=True)

        # Khách nói sang chuyện khác: bỏ bản ghi, để câu mới chạy pipeline thường.
        # Không đếm retry như A7-10: câu xác nhận chỉ hỏi một lần (xem
        # `MAX_CONFIRMATION_TURNS`), nên không có lượt hỏi lại nào để đếm.
        logger.info("confirmation bi bo qua, khach doi chu de: %r", user_message[:80])
        return ConfirmationResolution(clear_pending=True)


__all__ = ["PendingIntentConfirmationServiceImpl"]
