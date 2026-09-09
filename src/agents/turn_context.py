"""Ngữ cảnh của lượt đang chạy — chỉ những giá trị adapter cần mà port không mang.

Một `ContextVar` chứ không phải biến toàn cục: hai lượt chạy song song trên cùng
event loop phải thấy hai `session_id` khác nhau (PRD 8.5 — 50 phiên đồng thời).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_SESSION_ID: ContextVar[UUID | None] = ContextVar("agent_turn_session_id", default=None)


@contextmanager
def bind_session(session_id: str | UUID) -> Iterator[None]:
    """Gắn `session_id` cho khối lệnh của đúng một lượt, rồi trả lại giá trị cũ.

    `session_id` không phải UUID hợp lệ thì bỏ qua việc gắn thay vì làm vỡ lượt:
    lượt thật luôn dùng UUID hệ thống sinh ra (`conversation_sessions.session_id`
    là cột UUID), chỉ test cũ còn dùng chuỗi giả kiểu "s" làm khoá state thuần.
    """

    try:
        identifier = session_id if isinstance(session_id, UUID) else UUID(str(session_id))
    except ValueError:
        identifier = None
    token = _SESSION_ID.set(identifier)
    try:
        yield
    finally:
        _SESSION_ID.reset(token)


def current_session_id() -> UUID | None:
    """Phiên của lượt đang chạy, hoặc `None` khi gọi ngoài một lượt."""

    return _SESSION_ID.get()
