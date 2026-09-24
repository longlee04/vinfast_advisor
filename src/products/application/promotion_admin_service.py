"""Quản trị ưu đãi cho Admin (plan Customer 360 Phase 5C): tạo/sửa/huỷ, dựng luật, duyệt UNVERIFIED → ACTIVE.

Luật `eligibility_rules` kiểm bằng `domain.eligibility_rules.validate_rules` ở MỌI lần lưu — Admin
không thể lưu một luật mà bộ đánh giá sẽ coi là INVALID. Kích hoạt đòi luật hợp lệ: metadata
crawler phải được dựng thành luật trước khi ưu đãi được phép đến tay khách.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.products.domain.eligibility_rules import validate_rules

EDITABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "promotion_type",
        "discount_amount_vnd",
        "discount_percent",
        "eligibility_rules",
        "valid_from",
        "valid_to",
        "gift_group",
        "stackable",
        "priority",
        "max_uses",
        "requires_advisor_approval",
        "advisor_max_discount_vnd",
    }
)
#: Trạng thái Admin được đặt trực tiếp qua PATCH. ACTIVE chỉ qua `activate` (kiểm luật).
_PATCHABLE_STATUSES = frozenset({"DRAFT", "UNVERIFIED", "EXPIRED", "CANCELLED"})


class PromotionAdminError(ValueError):
    def __init__(self, code: str, errors: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.errors = errors


class PromotionAdminRepository(Protocol):
    async def list(self, status: str | None) -> list[dict[str, Any]]: ...
    async def get(self, promotion_id: str) -> dict[str, Any] | None: ...
    async def code_exists(self, promotion_code: str) -> bool: ...
    async def insert(self, values: Mapping[str, Any]) -> dict[str, Any]: ...
    async def update(self, promotion_id: str, values: Mapping[str, Any]) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class PromotionAdminService:
    repository: PromotionAdminRepository
    clock: Callable[[], datetime]

    def _check_rules(self, values: Mapping[str, Any]) -> None:
        if "eligibility_rules" in values:
            errors = validate_rules(values["eligibility_rules"] or {})
            if errors:
                raise PromotionAdminError("INVALID_RULES", tuple(errors))

    async def list(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = await self.repository.list(status)
        return [{**row, "rules_valid": not validate_rules(row.get("eligibility_rules") or {})} for row in rows]

    async def create(self, values: Mapping[str, Any], actor: str) -> dict[str, Any]:
        self._check_rules(values)
        code = str(values.get("promotion_code") or "").strip()
        if not code:
            raise PromotionAdminError("MISSING_CODE")
        if await self.repository.code_exists(code):
            raise PromotionAdminError("DUPLICATE_CODE")
        now = self.clock()
        payload = {key: values[key] for key in EDITABLE_FIELDS if key in values}
        # Ưu đãi mới luôn bắt đầu CHƯA KIỂM — chỉ `activate` mới đưa lên ACTIVE.
        return await self.repository.insert(
            {
                **payload,
                "promotion_code": code,
                "status": "UNVERIFIED",
                "created_by": actor,
                "created_at": now,
                "updated_at": now,
            }
        )

    async def update(self, promotion_id: str, values: Mapping[str, Any], actor: str) -> dict[str, Any]:
        self._check_rules(values)
        payload: dict[str, Any] = {key: values[key] for key in EDITABLE_FIELDS if key in values}
        if "status" in values:
            if values["status"] not in _PATCHABLE_STATUSES:
                raise PromotionAdminError("USE_ACTIVATE")
            payload["status"] = values["status"]
        payload["updated_at"] = self.clock()
        updated = await self.repository.update(promotion_id, payload)
        if updated is None:
            raise PromotionAdminError("NOT_FOUND")
        return updated

    async def activate(self, promotion_id: str, actor: str) -> dict[str, Any]:
        current = await self.repository.get(promotion_id)
        if current is None:
            raise PromotionAdminError("NOT_FOUND")
        errors = validate_rules(current.get("eligibility_rules") or {})
        if errors:
            raise PromotionAdminError("INVALID_RULES", tuple(errors))
        now = self.clock()
        if current.get("valid_to") is not None and current["valid_to"] < now:
            raise PromotionAdminError("EXPIRED")
        updated = await self.repository.update(
            promotion_id, {"status": "ACTIVE", "approved_by": actor, "approved_at": now, "updated_at": now}
        )
        assert updated is not None
        return updated

    async def cancel(self, promotion_id: str, actor: str) -> dict[str, Any]:
        """Xoá MỀM (CANCELLED): ưu đãi đã gửi vẫn truy vết được."""

        return await self.update(promotion_id, {"status": "CANCELLED"}, actor)


__all__ = ["EDITABLE_FIELDS", "PromotionAdminError", "PromotionAdminService"]
