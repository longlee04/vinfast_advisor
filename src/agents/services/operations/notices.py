"""[A8-4] Use case thông báo nội bộ — trạng thái đã đọc lưu riêng từng người.

Service mở/đóng transaction qua unit of work (mục 6.4). Không import SQLAlchemy:
nó chỉ thấy các Protocol dưới đây.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class NoticeNotFoundError(Exception):
    """Đánh dấu đã đọc một notice không tồn tại — hỏng dữ liệu, không phải im lặng."""


@dataclass(frozen=True)
class NoticeSummary:
    """Một notice kèm trạng thái đã đọc của riêng người đang hỏi."""

    notice_id: UUID
    title: str
    content: str
    priority: str
    created_at: datetime
    read: bool


class NoticeStore(Protocol):
    """Phần `internal_notices` + `notice_reads` mà use case này cần."""

    async def create_notice(self, title: str, content: str, priority: str, created_by: str) -> UUID: ...

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None: ...

    async def exists(self, notice_id: UUID) -> bool: ...

    async def list_for(self, advisor_id: str) -> list[NoticeSummary]: ...


class NoticeTransaction(Protocol):
    notices: NoticeStore


class NoticeUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[NoticeTransaction]: ...


class NoticeOperations:
    """Use case vận hành thông báo nội bộ (A8-4)."""

    def __init__(self, unit_of_work: NoticeUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def publish(self, title: str, content: str, priority: str, created_by: str) -> UUID:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.notices.create_notice(title, content, priority, created_by)

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None:
        """Ghi trạng thái đã đọc của riêng `advisor_id`; gọi lại không sinh hàng thứ hai."""
        async with self._unit_of_work.transaction() as transaction:
            if not await transaction.notices.exists(notice_id):
                raise NoticeNotFoundError(str(notice_id))
            await transaction.notices.mark_read(notice_id, advisor_id)

    async def list_for(self, advisor_id: str) -> list[NoticeSummary]:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.notices.list_for(advisor_id)
