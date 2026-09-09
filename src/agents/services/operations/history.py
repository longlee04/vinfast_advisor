"""[A8-3] Use case lịch sử tư vấn — ai được đọc hồ sơ của ai.

Quyết định phân quyền nằm ở service, không rải ở từng route: thêm một route mới
mà quên điều kiện là chỗ rò rỉ âm thầm, còn ở đây thì mọi đường đọc đều đi qua
cùng một hàm.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.auth.domain.authorization import Role


class HistoryAccessDeniedError(Exception):
    """Người gọi không được phép đọc hồ sơ của khách này."""


@dataclass(frozen=True)
class SessionHistoryItem:
    """Một phiên tư vấn của khách, kèm trạng thái duyệt cuối cùng."""

    session_id: str
    started_at: datetime
    run_count: int
    last_review_status: str | None


@dataclass(frozen=True)
class CustomerActivityDto:
    id: str
    kind: str
    date: str
    title: str
    description: str
    status: str
    tone: str
    icon: str


@dataclass(frozen=True)
class CustomerAccountSummaryDto:
    session_count: int
    booking_count: int
    comparison_count: int
    approved_recommendations_count: int
    activities: list[CustomerActivityDto]


class HistoryStore(Protocol):
    """Phần dữ liệu lịch sử mà use case này cần."""

    async def is_handled_by(self, customer_id: str, advisor_id: str) -> bool: ...

    async def list_sessions(self, customer_id: str) -> list[SessionHistoryItem]: ...

    async def get_customer_summary(self, customer_id: str) -> CustomerAccountSummaryDto: ...


class HistoryTransaction(Protocol):
    history: HistoryStore


class HistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[HistoryTransaction]: ...


class HistoryOperations:
    """Use case lịch sử tư vấn (A8-3)."""

    def __init__(self, unit_of_work: HistoryUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_for_customer(self, customer_id: str, *, requester_id: str, role: Role) -> list[SessionHistoryItem]:
        """Lịch sử của một khách, phiên gần nhất trước; sai quyền thì chặn trước khi đọc."""
        async with self._unit_of_work.transaction() as transaction:
            if not await self._may_read(transaction, customer_id, requester_id, role):
                raise HistoryAccessDeniedError(customer_id)
            return await transaction.history.list_sessions(customer_id)

    async def get_summary(self, customer_id: str, *, requester_id: str, role: Role) -> CustomerAccountSummaryDto:
        """Thống kê tổng quan và hoạt động gần nhất của khách hàng."""
        async with self._unit_of_work.transaction() as transaction:
            if not await self._may_read(transaction, customer_id, requester_id, role):
                raise HistoryAccessDeniedError(customer_id)
            return await transaction.history.get_customer_summary(customer_id)

    async def _may_read(self, transaction: HistoryTransaction, customer_id: str, requester_id: str, role: Role) -> bool:
        if role is Role.ADMIN:
            return True
        if role is Role.CUSTOMER:
            return requester_id == customer_id
        return await transaction.history.is_handled_by(customer_id, requester_id)
