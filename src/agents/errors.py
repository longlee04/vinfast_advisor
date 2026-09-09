"""Agent application errors."""

from __future__ import annotations


class SessionOwnershipError(Exception):
    """Raised when an authenticated customer accesses another customer's session."""

    def __init__(self, *, session_id: str, customer_id: str) -> None:
        self.session_id = session_id
        self.customer_id = customer_id
        super().__init__(f"customer {customer_id!r} does not own session {session_id!r}")


class ConversationNotFoundError(Exception):
    """Privacy-safe absence used for missing and foreign-owned conversations."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__("conversation not found")


class ConversationArchivedError(Exception):
    """Raised when a new turn targets an archived conversation."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__("conversation is archived")


class TurnInProgressError(Exception):
    """Raised when another worker already owns the same idempotency key."""


class TurnFailedError(Exception):
    """Raised when an idempotency key already has an immutable failed outcome."""

    def __init__(self, category: str | None) -> None:
        self.category = category
        super().__init__("turn previously failed")


class CoreTurnLeaseStaleError(Exception):
    """Raised when a worker's lease token is no longer the active owner.

    Token bị thay thế (takeover) hoặc lease đã hết hạn: worker này KHÔNG được
    thực hiện side effect và KHÔNG được commit. `expected` giữ lý do để transport
    chọn mã HTTP đúng (409 TURN_LEASE_EXPIRED).
    """

    def __init__(self, *, session_id: str, client_turn_id: str, reason: str) -> None:
        self.session_id = session_id
        self.client_turn_id = client_turn_id
        self.reason = reason
        super().__init__(f"core turn lease stale ({reason})")


class CoreTurnTimeoutError(Exception):
    """Raised when a leased core turn exceeds the hard budget 20s.

    Worker KHÔNG finalize FAILED; outcome stays IN_PROGRESS until lease expiry.
    Route maps to 503 TURN_TIMEOUT + Retry-After: 5.
    """

    def __init__(self, *, session_id: str, client_turn_id: str) -> None:
        self.session_id = session_id
        self.client_turn_id = client_turn_id
        super().__init__(f"core turn hard timeout: session={session_id} turn={client_turn_id}")


class TurnPersistenceError(Exception):
    """Lượt chạy xong nhưng KHÔNG ghi được — không được trả kết quả như đã xong.

    Dùng cho các đường đóng lượt ngoài `commit_core_turn` (lượt bị chặn nội dung).
    Trước đây chúng nuốt lỗi ghi rồi vẫn trả câu trả lời, nên khách thấy một lượt
    "hoàn tất" mà cơ sở dữ liệu không có dòng nào — gửi lại cùng mã lượt thì gặp
    trạng thái lạ. Thà báo thử-lại-được còn hơn nói dối là đã xong.
    """

    def __init__(self, *, session_id: str, client_turn_id: str) -> None:
        self.session_id = session_id
        self.client_turn_id = client_turn_id
        super().__init__(f"khong ghi duoc luot {client_turn_id} cua phien {session_id}")
