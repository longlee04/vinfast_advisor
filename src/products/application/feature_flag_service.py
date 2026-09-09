"""Use case quan ly vehicle_feature_flags cho man Admin.

Tach khoi `vehicle_service` vi trach nhiem khac han: day la luong duyet du
lieu (PENDING -> APPROVED/REJECTED), khong phai doc catalog. A10-4/A10-5 se
dung lai chinh service nay thay vi viet code path thu hai.
"""

from __future__ import annotations

from src.products.application import FeatureFlagDetail, FeatureFlagRepository, PageParams
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.values import VerificationStatus

_ALLOWED_DECISIONS = frozenset({VerificationStatus.APPROVED.value, VerificationStatus.REJECTED.value})


class FeatureFlagService:
    def __init__(self, repo: FeatureFlagRepository) -> None:
        self._repo = repo

    async def list_pending(
        self, page: PageParams, *, is_admin: bool, vehicle_id: str | None = None
    ) -> list[FeatureFlagDetail]:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        return await self._repo.list_flags(
            page,
            verification_status=VerificationStatus.PENDING.value,
            vehicle_id=vehicle_id,
        )

    async def count_pending(self, *, is_admin: bool, vehicle_id: str | None = None) -> int:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        return await self._repo.count_flags(verification_status=VerificationStatus.PENDING.value, vehicle_id=vehicle_id)

    async def review(
        self,
        vehicle_id: str,
        feature_code: str,
        decision: str,
        actor_id: str,
        *,
        is_admin: bool,
    ) -> FeatureFlagDetail:
        """Duyet hoac tu choi mot flag.

        Chi nhan APPROVED/REJECTED — khong co duong dua nguoc ve PENDING, va
        khong dong vao cot `status` (YES/NO/UNKNOWN). Mot flag UNKNOWN duoc
        duyet van la UNKNOWN: A1-3 quy dinh UNKNOWN khong duoc suy thanh NO.
        """
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        normalized = str(decision).strip().upper()
        if normalized not in _ALLOWED_DECISIONS:
            raise ValueError(f"decision phai la APPROVED hoac REJECTED, nhan duoc: {decision!r}")
        result = await self._repo.review_flag(vehicle_id, feature_code, normalized, actor_id)
        if result is None:
            raise ProductNotFoundError(f"Feature flag ({vehicle_id!r}, {feature_code!r}) not found")
        return result
