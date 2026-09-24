"""Quản trị ưu đãi (plan Customer 360 Phase 5C): luật luôn hợp lệ khi lưu, ACTIVE chỉ qua kích hoạt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.products.application.promotion_admin_service import PromotionAdminError, PromotionAdminService

NOW = datetime(2026, 9, 24, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def list(self, status):  # noqa: ANN001, ANN201
        return [row for row in self.rows.values() if status in (None, row["status"])]

    async def get(self, promotion_id):  # noqa: ANN001, ANN201
        return self.rows.get(promotion_id)

    async def code_exists(self, promotion_code):  # noqa: ANN001, ANN201
        return any(row["promotion_code"] == promotion_code for row in self.rows.values())

    async def insert(self, values):  # noqa: ANN001, ANN201
        row = {"promotion_id": f"p{len(self.rows) + 1}", "eligibility_rules": {}, "valid_to": None, **values}
        self.rows[row["promotion_id"]] = row
        return row

    async def update(self, promotion_id, values):  # noqa: ANN001, ANN201
        if promotion_id not in self.rows:
            return None
        self.rows[promotion_id].update(values)
        return self.rows[promotion_id]


@pytest.fixture
def service() -> PromotionAdminService:
    return PromotionAdminService(FakeRepository(), clock=lambda: NOW)


@pytest.mark.asyncio
async def test_uu_dai_moi_luon_unverified_va_chi_kich_hoat_khi_luat_hop_le(service: PromotionAdminService) -> None:
    created = await service.create(
        {
            "promotion_code": "HN-10",
            "title": "HN",
            "eligibility_rules": {"field": "registration_province", "in": ["HN"]},
        },
        "admin-1",
    )
    assert created["status"] == "UNVERIFIED"
    activated = await service.activate(created["promotion_id"], "admin-1")
    assert (activated["status"], activated["approved_by"]) == ("ACTIVE", "admin-1")


@pytest.mark.asyncio
async def test_luat_sai_bi_tu_choi_luc_luu(service: PromotionAdminService) -> None:
    with pytest.raises(PromotionAdminError) as error:
        await service.create({"promotion_code": "X", "eligibility_rules": {"field": "income", "gte": 1}}, "admin-1")
    assert error.value.code == "INVALID_RULES" and "UNKNOWN_FIELD:income" in error.value.errors[0]


@pytest.mark.asyncio
async def test_metadata_crawler_phai_dung_luat_truoc_khi_kich_hoat(service: PromotionAdminService) -> None:
    repository = service.repository
    await repository.insert(
        {"promotion_code": "VNPOST-2026", "status": "ACTIVE", "eligibility_rules": {"eligible_group": "VNPOST"}}
    )
    with pytest.raises(PromotionAdminError) as error:
        await service.activate("p1", "admin-1")
    assert error.value.code == "INVALID_RULES"
    listed = await service.list()
    assert listed[0]["rules_valid"] is False


@pytest.mark.asyncio
async def test_khong_patch_thang_len_active_trung_ma_va_het_han(service: PromotionAdminService) -> None:
    created = await service.create({"promotion_code": "A", "valid_to": NOW - timedelta(days=1)}, "admin-1")
    with pytest.raises(PromotionAdminError, match="USE_ACTIVATE"):
        await service.update(created["promotion_id"], {"status": "ACTIVE"}, "admin-1")
    with pytest.raises(PromotionAdminError, match="DUPLICATE_CODE"):
        await service.create({"promotion_code": "A"}, "admin-1")
    with pytest.raises(PromotionAdminError, match="EXPIRED"):
        await service.activate(created["promotion_id"], "admin-1")
    cancelled = await service.cancel(created["promotion_id"], "admin-1")
    assert cancelled["status"] == "CANCELLED"
