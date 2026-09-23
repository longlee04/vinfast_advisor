"""[Lớp 4] Câu xác nhận ý định đang chờ khách trả lời, sống qua nhiều lượt.

Anh em song sinh của `domain/pending_slot.py` (A7-10) nhưng KHÁC hẳn về ngữ
nghĩa, và đó là lý do nó là một cột riêng chứ không tái dùng cột cũ:

- `PendingSlotRequest` = "đang thiếu một GIÁ TRỊ, hỏi khách để điền vào form".
- `PendingIntentConfirmation` = "đã hiểu ra một Ý ĐỊNH nhưng chưa đủ chắc, hỏi
  khách xác nhận trước khi hành động".

Nhét cả hai vào một cột sẽ buộc `PendingSlotServiceImpl.resolve` phải phân biệt
hai loại payload ngay ở nhánh đầu tiên, và bộ trích slot rule-based của nó sẽ
được gọi trên một câu "đúng rồi ạ" — nơi nó chắc chắn không trích ra gì và sẽ
lặng lẽ tiêu một lượt hỏi lại trong `MAX_CLARIFY_TURNS`.

Câu trả lời cho nút bấm ("đúng" / "không phải") CHÍNH LÀ loại tin nhắn ngắn đứng
riêng mà `classify_scope` gắn `OUT_OF_SCOPE` — đúng con bug gốc của A7-10. Nên
bản ghi này phải được tiêu thụ TRƯỚC khi vào graph, cùng chỗ với A7-10
(`chain.run_turn`), không phải bằng một nhánh trong graph.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.pending_slot import PENDING_TTL

#: Dùng CHUNG hạn với pending slot: hai bản ghi cùng trả lời một câu hỏi bot vừa
#: đặt, nên "khách đã bỏ đi bao lâu thì coi như quên" là cùng một câu hỏi.
CONFIRMATION_TTL: Final[timedelta] = PENDING_TTL

#: Hỏi xác nhận đúng MỘT lần. Hỏi lại lần hai câu "ý anh/chị là VF 5 phải không"
#: không thêm thông tin nào cho khách — nếu lần đầu họ không xác nhận thì vấn đề
#: nằm ở chỗ hệ thống hiểu sai, không phải chỗ họ chưa nghe rõ.
MAX_CONFIRMATION_TURNS: Final[int] = 1

_AFFIRMATIONS: Final[frozenset[str]] = frozenset(
    {
        "dung",
        "dung roi",
        "dung r",
        "dung a",
        "dung vay",
        "chuan",
        "chuan roi",
        "phai",
        "phai roi",
        "chinh xac",
        "vang",
        "vang a",
        "da",
        "da dung",
        "ok",
        "oke",
        "okie",
        "okay",
        "co",
        "co a",
        "uh",
        "um",
        "u",
        "yes",
        "y",
        "1",
        "dong y",
    }
)

_DENIALS: Final[frozenset[str]] = frozenset(
    {
        "khong",
        "khong phai",
        "ko",
        "ko phai",
        "k",
        "kh",
        "sai",
        "sai roi",
        "chua phai",
        "khong dung",
        "ko dung",
        "no",
        "2",
        "khong a",
    }
)


class ConfirmationAnswer(StrEnum):
    """Ba cách khách phản hồi một câu xác nhận."""

    AFFIRMED = "AFFIRMED"
    DENIED = "DENIED"
    #: Không phải "có" cũng không phải "không" — khách nói sang chuyện khác. Đây
    #: là câu trả lời hợp lệ nhất trong ba, không phải lỗi: nó có nghĩa "bỏ câu
    #: xác nhận đi, xử lý câu mới của tôi".
    UNRELATED = "UNRELATED"


def read_confirmation(user_message: str, canonical: CanonicalText) -> ConfirmationAnswer:
    """Phân loại phản hồi của khách — rule-based, KHÔNG gọi LLM.

    So khớp TRÊN TOÀN BỘ câu đã chuẩn hoá, không tìm chuỗi con: "không" nằm
    trong "cho tôi xem xe không cần sạc nhà", và đọc câu đó thành một lời phủ
    nhận sẽ vứt mất nội dung khách vừa cung cấp.

    So trên `canonical.folded` — gate không tự normalize (AMENDMENT 2).
    """

    normalized = canonical.folded
    if not normalized:
        return ConfirmationAnswer.UNRELATED
    if normalized in _AFFIRMATIONS:
        return ConfirmationAnswer.AFFIRMED
    if normalized in _DENIALS:
        return ConfirmationAnswer.DENIED
    return ConfirmationAnswer.UNRELATED


@dataclass(frozen=True, slots=True)
class PendingIntentConfirmation:
    """Ý định bot đã suy ra và đang chờ khách xác nhận."""

    #: Câu sẽ được xử lý nếu khách xác nhận — bản đã rewrite, hoặc câu gốc khi
    #: Lớp 1 không áp dụng được. Lưu lại vì lượt sau khách chỉ gõ "đúng", và câu
    #: đó không mang nội dung nào để chạy lại pipeline.
    proposed_text: str
    intent_hint: str | None = None
    vehicle_names: tuple[str, ...] = ()
    confidence: float = 0.0
    asked_at: datetime | None = None
    turn_count: int = 0

    def is_expired(self, now: datetime, ttl: timedelta = CONFIRMATION_TTL) -> bool:
        """Quá hạn thì coi như không còn chờ gì.

        `asked_at` thiếu → coi là HẾT HẠN, cùng chiều an toàn với A7-10: bỏ sót
        một lần nối ngữ cảnh chỉ khiến khách nói lại, còn giữ một bản ghi không
        rõ tuổi thì mọi tin nhắn về sau bị đọc sai.
        """

        if self.asked_at is None:
            return True
        asked = self.asked_at if self.asked_at.tzinfo else self.asked_at.replace(tzinfo=UTC)
        return now - asked > ttl

    def exhausted(self, limit: int = MAX_CONFIRMATION_TURNS) -> bool:
        return self.turn_count >= limit

    def to_payload(self) -> dict[str, Any]:
        """Dạng JSON cho cột `conversation_sessions.pending_intent_confirmation`."""

        return {
            "proposed_text": self.proposed_text,
            "intent_hint": self.intent_hint,
            "vehicle_names": list(self.vehicle_names),
            "confidence": self.confidence,
            "asked_at": None if self.asked_at is None else self.asked_at.isoformat(),
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> PendingIntentConfirmation | None:
        """Dựng lại từ JSON; payload hỏng → `None` chứ không raise.

        Cùng lý do với `PendingSlotRequest.from_payload`: một `ValueError` ở đây
        làm chết lượt của khách vì một cột dữ liệu cũ.
        """

        if not payload:
            return None
        proposed = payload.get("proposed_text")
        if not isinstance(proposed, str) or not proposed.strip():
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
        names = payload.get("vehicle_names")
        intent_hint = payload.get("intent_hint")
        confidence = payload.get("confidence")
        turn_count = payload.get("turn_count")
        return cls(
            proposed_text=proposed,
            intent_hint=intent_hint if isinstance(intent_hint, str) else None,
            vehicle_names=tuple(name for name in (names or ()) if isinstance(name, str)),
            confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.0,
            asked_at=asked_at,
            turn_count=turn_count if isinstance(turn_count, int) else 0,
        )


@dataclass(frozen=True, slots=True)
class ConfirmationResolution:
    """Kết quả xử lý một lượt khi đang chờ xác nhận ý định.

    Ba kết cục, và chúng KHÁC nhau ở chỗ lượt đi tiếp hay dừng — nên không gộp
    được vào một cờ `handled` như `PendingResolution` của A7-10:

    - `substitute_message` khác `None`: khách đã xác nhận. Lượt CHẠY TIẾP như
      thường nhưng với câu đã suy ra thay cho chữ "đúng" — nếu dừng ở đây thì
      khách gật đầu xong không nhận được gì.
    - `reply` khác `None`: lượt DỪNG với câu này (khách vừa phủ nhận suy đoán).
    - Cả hai đều `None`: không có gì đang chờ, hoặc khách đã nói sang chuyện
      khác — lượt chạy pipeline thường trên chính câu họ vừa gõ.
    """

    #: Câu thay thế, đưa tiếp vào pipeline thay cho câu xác nhận của khách.
    substitute_message: str | None = None
    #: Câu trả khách và kết thúc lượt.
    reply: str | None = None
    pending: PendingIntentConfirmation | None = None
    clear_pending: bool = False


__all__ = [
    "CONFIRMATION_TTL",
    "MAX_CONFIRMATION_TURNS",
    "ConfirmationAnswer",
    "ConfirmationResolution",
    "PendingIntentConfirmation",
    "read_confirmation",
]
