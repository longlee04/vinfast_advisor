"""Use case quan ly `offer_adjustment_policies` cho man Admin.

Tach khoi vehicle_service vi trach nhiem khac han: day la CRUD cau hinh bien
do duyet (ADMIN), khong phai doc catalog. `OfferPolicyPort` duoc dinh nghia o
day de agents chi phu thuoc vao contract, khong import truc tiep products.
"""

from __future__ import annotations

from typing import Protocol

from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.offer_policy import (
    OfferAdjustmentPolicy,
    validate_policy_bounds,
)


class OfferPolicyRepository(Protocol):
    """Port luu/dua offer_adjustment_policies."""

    async def list(self) -> list[OfferAdjustmentPolicy]: ...

    async def get(self, promotion_type: str) -> OfferAdjustmentPolicy | None: ...

    async def create(self, policy: OfferAdjustmentPolicy, *, created_by: str) -> OfferAdjustmentPolicy: ...

    async def update(
        self,
        promotion_type: str,
        updates: dict[str, object],
        *,
        updated_by: str,
    ) -> OfferAdjustmentPolicy | None: ...

    async def delete(self, promotion_type: str) -> bool: ...


class OfferPolicyService:
    """CRUD cau hinh bien do, validate bounds truoc khi luu."""

    def __init__(self, repo: OfferPolicyRepository) -> None:
        self._repo = repo

    async def list(self, *, is_admin: bool) -> list[OfferAdjustmentPolicy]:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        return await self._repo.list()

    async def get(self, promotion_type: str, *, is_admin: bool) -> OfferAdjustmentPolicy:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        policy = await self._repo.get(promotion_type)
        if policy is None:
            raise ProductNotFoundError(f"offer policy {promotion_type!r} not found")
        return policy

    async def create(self, policy: OfferAdjustmentPolicy, *, created_by: str, is_admin: bool) -> OfferAdjustmentPolicy:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        validate_policy_bounds(policy)
        return await self._repo.create(policy, created_by=created_by)

    async def update(
        self,
        promotion_type: str,
        updates: dict[str, object],
        *,
        updated_by: str,
        is_admin: bool,
    ) -> OfferAdjustmentPolicy:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        existing = await self._repo.get(promotion_type)
        if existing is None:
            raise ProductNotFoundError(f"offer policy {promotion_type!r} not found")
        merged = existing.model_copy(update=updates)
        validate_policy_bounds(merged)
        result = await self._repo.update(promotion_type, updates, updated_by=updated_by)
        if result is None:
            raise ProductNotFoundError(f"offer policy {promotion_type!r} not found")
        return result

    async def delete(self, promotion_type: str, *, is_admin: bool) -> None:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        deleted = await self._repo.delete(promotion_type)
        if not deleted:
            raise ProductNotFoundError(f"offer policy {promotion_type!r} not found")
