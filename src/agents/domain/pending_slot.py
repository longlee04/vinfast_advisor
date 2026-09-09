"""[A7-10] Slot đang chờ khách trả lời, sống qua nhiều lượt.

Bug đã quan sát: bot hỏi "Quý khách đăng ký xe ở tỉnh/thành nào?", khách đáp
"hà nội", và câu đó bị `classify_scope` gắn OUT_OF_SCOPE rồi kết thúc lượt. Một
tin nhắn hai chữ đứng riêng thì đúng là không khớp intent nào — nhưng nó KHÔNG
đứng riêng, nó là câu trả lời cho câu hỏi bot vừa đặt. Cái thiếu là chỗ ghi lại
"đang chờ slot nào, cho intent nào".

`province` cố ý KHÔNG nằm trong `SlotName`: cây slot A3-1 là các slot của luồng
tư vấn chọn xe, còn tỉnh chỉ dùng cho phép tính giá lăn bánh. Nhét nó vào đó sẽ
kéo theo cả `require_complete`, `build_criteria` và Lớp 1 — bốn chỗ phải hiểu một
khái niệm chúng không dùng.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from src.agents.domain.focus_policy import DEFAULT_CONVERSATION_FOCUS_POLICY

#: [GIẢ ĐỊNH] Hệ thống chưa có cơ chế TTL/session timeout dùng chung, nên đặt
#: riêng 15 phút cho pending. Khách bỏ ngang rồi quay lại sau nửa tiếng mà vẫn bị
#: coi là đang trả lời câu hỏi cũ thì tin nhắn mới của họ bị đọc sai. Hết hạn được
#: dọn NGAY LÚC ĐỌC, không cần cron job riêng.
PENDING_TTL: Final[timedelta] = DEFAULT_CONVERSATION_FOCUS_POLICY.pending_question_ttl

#: [GIẢ ĐỊNH] Hỏi lại tối đa 2 lượt cùng một slot (`turn_count` 0 → 1) rồi mới bỏ.
#: Tránh cùng lúc hai lỗi ngược nhau: bỏ pending ngay lần trích thất bại đầu (khách
#: chỉ đang trả lời mơ hồ, không đổi chủ đề), và hỏi vòng vô tận (khách thật sự đã
#: chuyển sang chuyện khác).
MAX_CLARIFY_TURNS: Final[int] = 1


@dataclass(frozen=True, slots=True)
class PendingSlotRequest:
    """Slot đang chờ khách trả lời, gắn với một intent cụ thể."""

    intent: str
    missing_slot: str
    partial_form: Mapping[str, Any] = field(default_factory=dict)
    asked_at: datetime | None = None
    turn_count: int = 0

    def is_expired(self, now: datetime, ttl: timedelta = PENDING_TTL) -> bool:
        """Quá hạn thì coi như không còn chờ gì.

        `asked_at` thiếu (dữ liệu cũ, hoặc ghi lỗi) → coi là HẾT HẠN. Chiều an
        toàn: bỏ sót một lần nối ngữ cảnh chỉ khiến khách phải nói lại, còn giữ
        một pending không rõ tuổi thì mọi tin nhắn về sau bị đọc sai.
        """

        if self.asked_at is None:
            return True
        asked = self.asked_at if self.asked_at.tzinfo else self.asked_at.replace(tzinfo=UTC)
        return now - asked > ttl

    def exhausted(self, limit: int = MAX_CLARIFY_TURNS) -> bool:
        """Đã hỏi lại đủ số lần cho phép mà vẫn không trích được."""

        return self.turn_count >= limit

    def clarified(self) -> PendingSlotRequest:
        """Bản ghi cho lượt hỏi lại kế tiếp."""

        return replace(self, turn_count=self.turn_count + 1)

    def filled_with(self, value: object) -> dict[str, Any]:
        """Form sau khi điền giá trị khách vừa cung cấp."""

        return {**dict(self.partial_form), self.missing_slot: value}

    def to_payload(self) -> dict[str, Any]:
        """Dạng JSON để lưu vào cột `conversation_sessions.pending_slot_request`."""

        return {
            "intent": self.intent,
            "missing_slot": self.missing_slot,
            "partial_form": dict(self.partial_form),
            "asked_at": None if self.asked_at is None else self.asked_at.isoformat(),
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> PendingSlotRequest | None:
        """Dựng lại từ JSON; payload hỏng → `None` chứ không raise.

        Một `ValueError` ở đây sẽ làm chết lượt của khách vì một cột dữ liệu cũ.
        Trả `None` nghĩa là "không có pending" — lượt chạy như bình thường.
        """

        if not payload:
            return None
        intent = payload.get("intent")
        missing_slot = payload.get("missing_slot")
        if not isinstance(intent, str) or not isinstance(missing_slot, str):
            return None
        raw_asked_at = payload.get("asked_at")
        asked_at: datetime | None = None
        if isinstance(raw_asked_at, str):
            try:
                asked_at = datetime.fromisoformat(raw_asked_at)
            except ValueError:
                asked_at = None
        elif isinstance(raw_asked_at, datetime):
            asked_at = raw_asked_at
        partial = payload.get("partial_form")
        turn_count = payload.get("turn_count")
        return cls(
            intent=intent,
            missing_slot=missing_slot,
            partial_form=dict(partial) if isinstance(partial, Mapping) else {},
            asked_at=asked_at,
            turn_count=turn_count if isinstance(turn_count, int) else 0,
        )


__all__ = [
    "MAX_CLARIFY_TURNS",
    "PENDING_TTL",
    "PendingSlotRequest",
]
