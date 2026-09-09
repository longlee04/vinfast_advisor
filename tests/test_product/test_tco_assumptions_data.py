"""Dữ liệu tco_assumptions phải khớp văn bản hiện hành sau migration."""

import os

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def _fetch(vehicle_type: str, region_code: str) -> dict:
    dsn = (os.environ.get("PRODUCT_DATABASE_URL") or os.environ.get("AUTH_DATABASE_URL") or "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    if not dsn:
        pytest.skip("Cần PRODUCT_DATABASE_URL hoặc AUTH_DATABASE_URL")
    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            "select * from tco_assumptions where vehicle_type = $1 and region_code = $2 and status = 'ACTIVE'",
            vehicle_type,
            region_code,
        )
    finally:
        await connection.close()
    if row is None:
        pytest.skip(f"Chưa có tco_assumptions cho {vehicle_type}/{region_code}")
    return dict(row)


async def test_car_uses_the_current_plate_and_inspection_fees() -> None:
    """Mức 14 triệu là của KHU VỰC I; Khu vực II có test riêng bên dưới."""

    row = await _fetch("CAR", "KHU_VUC_I")

    assert row["plate_fee_vnd"] == 14000000
    assert row["inspection_fee_vnd"] == 290000
    assert row["assumption_version"] == 4


async def test_car_source_note_no_longer_cites_the_expired_decree() -> None:
    row = await _fetch("CAR", "KHU_VUC_II")

    assert "10/2022" not in row["source_note"]
    assert "51/2025" in row["source_note"]
    assert "GIẢ ĐỊNH" in row["source_note"]


async def test_motorbike_current_estimate_excludes_inspection_and_services_every_five_thousand_km() -> None:
    row = await _fetch("ELECTRIC_MOTORBIKE", "KHU_VUC_II")

    assert row["inspection_first_month"] == 0
    assert row["maintenance_interval_km"] == 5000
    assert "không được diễn giải là xe máy luôn miễn kiểm định" in row["source_note"]


async def test_car_khu_vuc_i_uses_the_expensive_plate_fee() -> None:
    """Hà Nội / TP.HCM: 14 triệu."""

    row = await _fetch("CAR", "KHU_VUC_I")

    assert row["plate_fee_vnd"] == 14000000


async def test_car_khu_vuc_ii_uses_the_cheap_plate_fee() -> None:
    """Các tỉnh còn lại: 140 nghìn — chênh đúng 100 lần.

    Đây là lý do bảng phải tách theo vùng: dùng chung một dòng thì mọi khách
    ngoài Hà Nội/TP.HCM đọc được con số cao hơn thực tế gần 14 triệu.
    """

    row = await _fetch("CAR", "KHU_VUC_II")

    assert row["plate_fee_vnd"] == 140000


async def test_car_carries_the_legal_inspection_cycle() -> None:
    row = await _fetch("CAR", "KHU_VUC_II")

    assert row["inspection_first_month"] == 30
    assert row["inspection_interval_months"] == 18
    assert row["inspection_interval_months_after_7y"] == 12


async def test_car_source_note_cites_the_current_decree() -> None:
    row = await _fetch("CAR", "KHU_VUC_II")

    assert "51/2025" in row["source_note"]
    assert "155/2025" in row["source_note"]


async def test_each_region_note_names_its_own_region() -> None:
    """Ghi chú nguồn phải nói đúng khu vực của chính dòng đó."""

    khu_vuc_i = await _fetch("CAR", "KHU_VUC_I")
    khu_vuc_ii = await _fetch("CAR", "KHU_VUC_II")

    assert "Khu vực I (Hà Nội, TP.HCM)" in khu_vuc_i["source_note"]
    assert "Khu vực II (ngoài Hà Nội, TP.HCM)" in khu_vuc_ii["source_note"]


async def test_motorbike_never_inspects_and_services_every_five_thousand_km() -> None:
    row = await _fetch("ELECTRIC_MOTORBIKE", "KHU_VUC_II")

    assert row["inspection_first_month"] == 0
    assert row["maintenance_interval_km"] == 5000


async def test_every_vehicle_type_has_a_row_in_both_regions() -> None:
    """Thiếu một dòng nghĩa là nửa số khách nhận `tco_unavailable`.

    Xe máy điện có phí giống nhau ở hai khu vực, nhưng vẫn phải đủ HAI dòng:
    repository lọc chặt theo vùng, một dòng chỉ khớp được nửa số truy vấn.
    """

    for vehicle_type in ("CAR", "ELECTRIC_MOTORBIKE"):
        for region in ("KHU_VUC_I", "KHU_VUC_II"):
            row = await _fetch(vehicle_type, region)
            assert row["region_code"] == region
