"""Tư vấn viên tự nhận / trả khách, hàng chờ khách chưa ai phụ trách, tự nhả khách bị bỏ quên.

Thay cho màn phân công của Admin: người chịu trách nhiệm với khách là tư vấn viên (luật ở
`domain/customer_ownership.py`). Service chỉ lắp ráp — quyết định nằm ở domain, tính
nguyên tử nằm ở database.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.agents.domain.customer_ownership import (
    REASON_SELF_RELEASE,
    REASON_STALE,
    VIA_CLAIM,
    VIA_TAKEOVER,
    ClaimOutcome,
    claim_outcome,
    stale_before,
)
from src.agents.domain.pii import mask_email, mask_phone


class CustomerOwnershipRepository(Protocol):
    async def try_claim(self, customer_id: str, advisor_id: str, via: str, now: datetime) -> tuple[bool, str | None]:
        """Ghi người phụ trách nếu khách chưa có ai. Trả (đã ghi?, người đang phụ trách)."""
        ...

    async def release(self, customer_id: str, advisor_ids: Sequence[str], reason: str, now: datetime) -> bool: ...
    async def release_stale(self, before: datetime, reason: str, now: datetime) -> list[str]: ...
    async def pool(self, limit: int) -> list[dict[str, Any]]: ...
    async def customer_of_session(self, session_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ClaimResult:
    outcome: ClaimOutcome
    owner: str | None


class CustomerOwnershipOperations:
    def __init__(self, repository: CustomerOwnershipRepository, clock: Callable[[], datetime]) -> None:
        self._repository = repository
        self._clock = clock

    async def claim(self, customer_id: str, *, advisor_id: str, requester_ids: Sequence[str]) -> ClaimResult:
        """Bấm "Nhận khách" ở hàng chờ."""

        inserted, owner = await self._repository.try_claim(customer_id, advisor_id, VIA_CLAIM, self._clock())
        return ClaimResult(claim_outcome(inserted, owner, tuple(requester_ids)), owner)

    async def claim_on_takeover(self, session_id: str, *, advisor_id: str) -> ClaimResult | None:
        """Tiếp quản hội thoại: khách chưa có ai phụ trách thì thuộc về người tiếp quản.

        Khách ẩn danh (`anon-…`) không có hồ sơ lâu dài nên không nhận. Khách đã có người khác
        phụ trách thì giữ nguyên — tiếp quản một phiên không phải là giành khách.
        """

        customer_id = await self._repository.customer_of_session(session_id)
        if customer_id is None or customer_id.startswith("anon-"):
            return None
        inserted, owner = await self._repository.try_claim(customer_id, advisor_id, VIA_TAKEOVER, self._clock())
        return ClaimResult(claim_outcome(inserted, owner, (advisor_id,)), owner)

    async def release(self, customer_id: str, *, requester_ids: Sequence[str]) -> bool:
        """Người đang phụ trách trả khách về hàng chờ. Người khác gọi → `False`."""

        return await self._repository.release(customer_id, list(requester_ids), REASON_SELF_RELEASE, self._clock())

    async def release_stale(self) -> list[str]:
        """Sweep định kỳ: nhả khách không có hoạt động tư vấn viên trong N ngày."""

        now = self._clock()
        return await self._repository.release_stale(stale_before(now), REASON_STALE, now)

    async def pool(self, limit: int = 50) -> list[dict[str, Any]]:
        """Hàng chờ khách chưa ai phụ trách — danh sách nên SĐT luôn che."""

        rows = await self._repository.pool(limit)
        return [
            {
                **row,
                "phone": mask_phone(row["phone"]) if row.get("phone") else None,
                "email": mask_email(row["email"]) if row.get("email") else None,
            }
            for row in rows
        ]


__all__ = ["ClaimResult", "CustomerOwnershipOperations", "CustomerOwnershipRepository"]
