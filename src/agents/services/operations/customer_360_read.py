"""Đọc Customer 360 cho HTTP: hồ sơ, danh sách cơ hội, picker, số liệu Admin (plan Phase 4).

Quyền (plan §2.7): Admin xem tất cả ở chế độ chỉ xem; TVV chỉ xem khách đang được giao cho
mình (khớp id HOẶC email — quy ước `domain/staff_access.staff_identifiers`). SĐT đầy đủ chỉ
cho TVV phụ trách; bằng chứng luôn qua `redact_pii`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol

from src.agents.domain.customer360_flags import (
    FLAG_ATTACH,
    FLAG_EXTRACTOR,
    FLAG_OFFER_LIFECYCLE,
    FLAG_OFFER_RULES,
    FLAG_UI,
    is_globally_on,
)
from src.agents.domain.customer_overview import Viewer, build_overview
from src.agents.domain.heat_score import HEAT_VERSION, HOT_THRESHOLD, WARM_THRESHOLD
from src.agents.domain.pii import mask_phone, redact_pii
from src.agents.domain.sales_stage import STAGE_ORDER
from src.agents.services.operations.customer_360 import FlagReader


class CustomerAccessDeniedError(Exception):
    """Người xem không phải Admin và không phụ trách khách này."""


class Customer360DisabledError(Exception):
    """Cờ `customer360_ui` đang TẮT — frontend dùng màn dự phòng."""


class Customer360Query(Protocol):
    async def load_profile(self, customer_id: str) -> Any: ...
    async def owner(self, kind: str, ref: str) -> tuple[str, set[str]] | None: ...
    async def list_opportunities(
        self, *, advisor_ids: Sequence[str] | None, band: str | None, limit: int
    ) -> list[dict[str, Any]]: ...
    async def picker(self, query: str | None, limit: int) -> list[dict[str, Any]]: ...
    async def metrics(self, now: datetime, window_days: int) -> dict[str, Any]: ...
    async def extraction_quality(self, since: datetime) -> dict[str, Any]: ...


class Customer360ReadOperations:
    def __init__(self, query: Customer360Query, flags: FlagReader | None, clock: Callable[[], datetime]) -> None:
        self._query = query
        self._flags = flags
        self._clock = clock

    async def _on(self, name: str) -> bool:
        return self._flags is not None and is_globally_on(await self._flags.load(name))

    async def meta(self) -> dict[str, Any]:
        return {
            "enabled": {
                "ui": await self._on(FLAG_UI),
                "attach": await self._on(FLAG_ATTACH),
                "extractor": await self._on(FLAG_EXTRACTOR),
                "offer_rules": await self._on(FLAG_OFFER_RULES),
                "offer_lifecycle": await self._on(FLAG_OFFER_LIFECYCLE),
            },
            "stages": [stage.value for stage in STAGE_ORDER],
            "heat_thresholds": {"hot": HOT_THRESHOLD, "warm": WARM_THRESHOLD},
            "heat_version": HEAT_VERSION,
        }

    async def _require_ui(self) -> None:
        if not await self._on(FLAG_UI):
            raise Customer360DisabledError

    async def check_access(self, kind: str, ref: str, *, requester_ids: Sequence[str], is_admin: bool) -> str | None:
        """Khách sở hữu `ref`, hoặc `None` nếu không tồn tại. Không có quyền → raise."""

        owner = await self._query.owner(kind, ref)
        if owner is None:
            return None
        customer_id, advisors = owner
        if not is_admin and not advisors.intersection(requester_ids):
            raise CustomerAccessDeniedError
        return customer_id

    async def overview(self, customer_id: str, *, requester_ids: Sequence[str], is_admin: bool) -> dict[str, Any]:
        await self._require_ui()
        bundle = await self._query.load_profile(customer_id)
        assigned = bundle.header.assigned_advisor_id
        is_assigned = assigned is not None and assigned in requester_ids
        if not is_admin and not is_assigned:
            raise CustomerAccessDeniedError
        return build_overview(
            bundle.header,
            bundle.opportunities,
            bundle.facts,
            bundle.sessions,
            Viewer(is_admin=is_admin, is_assigned_advisor=is_assigned),
        )

    async def list_opportunities(
        self, *, requester_ids: Sequence[str], is_admin: bool, band: str | None, limit: int
    ) -> list[dict[str, Any]]:
        await self._require_ui()
        return await self._query.list_opportunities(
            advisor_ids=None if is_admin else list(requester_ids), band=band, limit=limit
        )

    async def picker(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        rows = await self._query.picker(query, limit)
        # Màn phân công là màn DANH SÁCH: luôn che SĐT (plan §2.7).
        return [{**row, "phone": mask_phone(row["phone"]) if row.get("phone") else None} for row in rows]

    async def metrics(self, window_days: int = 30) -> dict[str, Any]:
        return await self._query.metrics(self._clock(), window_days)

    async def extraction_quality(self, window_days: int = 30) -> dict[str, Any]:
        """Tỉ lệ insight bị báo sai theo field, gắn phiên bị sửa theo người quyết (RULE/LLM).

        Bằng chứng trong mẫu luôn qua `redact_pii` — màn Admin không lộ liên hệ khách.
        """

        result = await self._query.extraction_quality(self._clock() - timedelta(days=window_days))
        result["samples"] = [
            {**sample, "evidence_quote": redact_pii(sample.get("evidence_quote") or "")} for sample in result["samples"]
        ]
        return result


__all__ = ["Customer360DisabledError", "Customer360ReadOperations", "CustomerAccessDeniedError"]
