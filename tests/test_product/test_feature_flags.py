"""API quan ly vehicle_feature_flags — duyet PENDING, khong dung UNKNOWN thanh NO."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.products.application import FeatureFlagDetail, FeatureFlagRepository, PageParams
from src.products.application.feature_flag_service import FeatureFlagService
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError


def _flag(
    vehicle_id: str = "v-1",
    feature_code: str = "PANORAMIC_ROOF",
    status: str = "YES",
    verification_status: str = "PENDING",
) -> FeatureFlagDetail:
    return FeatureFlagDetail(
        vehicle_id=vehicle_id,
        feature_code=feature_code,
        status=status,
        verification_status=verification_status,
        vehicle_name="VinFast VF 8",
        feature_name="Cua so troi toan canh",
        confidence=None,
        updated_by=None,
        updated_at=datetime(2026, 8, 6, tzinfo=UTC),
    )


class FakeFeatureFlagRepository(FeatureFlagRepository):
    def __init__(self, flags: list[FeatureFlagDetail] | None = None) -> None:
        self._flags = {(f.vehicle_id, f.feature_code): f for f in (flags or [])}

    async def list_flags(self, page, *, verification_status=None, vehicle_id=None):
        items = list(self._flags.values())
        if verification_status is not None:
            items = [f for f in items if f.verification_status == verification_status]
        if vehicle_id is not None:
            items = [f for f in items if f.vehicle_id == vehicle_id]
        return items[page.skip : page.skip + page.limit]

    async def count_flags(self, *, verification_status=None, vehicle_id=None):
        items = list(self._flags.values())
        if verification_status is not None:
            items = [f for f in items if f.verification_status == verification_status]
        if vehicle_id is not None:
            items = [f for f in items if f.vehicle_id == vehicle_id]
        return len(items)

    async def review_flag(self, vehicle_id, feature_code, decision, actor_id):
        key = (vehicle_id, feature_code)
        current = self._flags.get(key)
        if current is None:
            return None
        updated = replace(current, verification_status=decision, updated_by=actor_id)
        self._flags[key] = updated
        return updated


@pytest.mark.asyncio
async def test_list_pending_returns_only_pending_flags() -> None:
    repo = FakeFeatureFlagRepository([_flag(), _flag(feature_code="ADAS", verification_status="APPROVED")])
    service = FeatureFlagService(repo)

    items = await service.list_pending(PageParams(skip=0, limit=10), is_admin=True)

    assert len(items) == 1
    assert items[0].feature_code == "PANORAMIC_ROOF"


@pytest.mark.asyncio
async def test_list_pending_requires_admin() -> None:
    service = FeatureFlagService(FakeFeatureFlagRepository([_flag()]))

    with pytest.raises(ProductPermissionError):
        await service.list_pending(PageParams(skip=0, limit=10), is_admin=False)


@pytest.mark.asyncio
async def test_approve_sets_verification_status_and_records_actor() -> None:
    repo = FakeFeatureFlagRepository([_flag()])
    service = FeatureFlagService(repo)

    result = await service.review("v-1", "PANORAMIC_ROOF", "APPROVED", actor_id="admin-1", is_admin=True)

    assert result.verification_status == "APPROVED"
    assert result.updated_by == "admin-1"


@pytest.mark.asyncio
async def test_reject_sets_rejected_status() -> None:
    repo = FakeFeatureFlagRepository([_flag()])
    service = FeatureFlagService(repo)

    result = await service.review("v-1", "PANORAMIC_ROOF", "REJECTED", actor_id="admin-1", is_admin=True)

    assert result.verification_status == "REJECTED"


@pytest.mark.asyncio
async def test_review_rejects_unknown_decision() -> None:
    service = FeatureFlagService(FakeFeatureFlagRepository([_flag()]))

    with pytest.raises(ValueError):
        await service.review("v-1", "PANORAMIC_ROOF", "MAYBE", actor_id="admin-1", is_admin=True)


@pytest.mark.asyncio
async def test_review_cannot_set_back_to_pending() -> None:
    # Duyet la hanh dong mot chieu: khong co duong dua ve PENDING qua API nay.
    service = FeatureFlagService(FakeFeatureFlagRepository([_flag()]))

    with pytest.raises(ValueError):
        await service.review("v-1", "PANORAMIC_ROOF", "PENDING", actor_id="admin-1", is_admin=True)


@pytest.mark.asyncio
async def test_review_requires_admin() -> None:
    service = FeatureFlagService(FakeFeatureFlagRepository([_flag()]))

    with pytest.raises(ProductPermissionError):
        await service.review("v-1", "PANORAMIC_ROOF", "APPROVED", actor_id="advisor-1", is_admin=False)


@pytest.mark.asyncio
async def test_review_missing_flag_raises_not_found() -> None:
    service = FeatureFlagService(FakeFeatureFlagRepository([]))

    with pytest.raises(ProductNotFoundError):
        await service.review("v-1", "KHONG_TON_TAI", "APPROVED", actor_id="admin-1", is_admin=True)


@pytest.mark.asyncio
async def test_unknown_status_flag_is_still_listed() -> None:
    # A1-3: xe UNKNOWN cho feature bat buoc VAN o trong ket qua kem co canh bao.
    # Duyet mot flag UNKNOWN khong duoc bien no thanh NO.
    repo = FakeFeatureFlagRepository([_flag(status="UNKNOWN")])
    service = FeatureFlagService(repo)

    result = await service.review("v-1", "PANORAMIC_ROOF", "APPROVED", actor_id="admin-1", is_admin=True)

    assert result.status == "UNKNOWN"
