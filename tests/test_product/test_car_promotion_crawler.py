"""Tests for normalized car promotions from official VinFast policies."""

from __future__ import annotations

import csv
from pathlib import Path

from crawl.crawl_car_promotions import build_car_promotion_rows

SALES_POLICY_TEXT = """
Chính sách ưu đãi một số dòng xe
VF 3 Eco/Plus Miễn phí màu sơn nâng cao cho VIN 2025 trở về trước.
Chương trình Tri ân Khách hàng xe xăng VinFast chuyển đổi Xanh
Fadil 30.000.000 VNĐ Lux A2.0 60.000.000 VNĐ Lux SA2.0 80.000.000 VNĐ
Voucher có giá trị sử dụng đến hết 31/12/2026.
Chính sách Mua xe 0 Đồng
Khách hàng mua xe không cần vốn đối ứng, được cho vay lên tới 100% giá trị xe.
Từ ngày 04/01/2026 đến ngày 31/12/2026.
Khách hàng phục vụ trong ngành Công an và Quân đội
Mức ưu đãi: 5% MSRP. Từ ngày 04/02/2026 đến hết ngày 31/12/2026.
Khách hàng là CBNV của Tổng Công ty Bưu điện Việt Nam – VN Post
CBNV: 3% MSRP. CBLĐ: 5% MSRP. đến hết ngày 31/12/2026.
"""

VINCLUB_POLICY_TEXT = """
Chương trình ưu đãi VinClub Đặc Biệt
Được nhân 03 lần quyền lợi tương ứng với hạng thành viên.
Áp dụng đối với xe được xuất hóa đơn từ ngày 01/08/2026 đến hết ngày 31/10/2026.
Hạng Gold ưu đãi 1%. Hạng Platinum ưu đãi 2%. Hạng Diamond ưu đãi 3%.
"""


def _vehicle_csv(tmp_path: Path) -> Path:
    path = tmp_path / "vehicles.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["vehicle_id", "vehicle_type", "model_name", "status", "slug"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {"vehicle_id": "vf3", "vehicle_type": "CAR", "model_name": "VF 3", "status": "ACTIVE", "slug": "vf-3"},
                {
                    "vehicle_id": "vf8-eco",
                    "vehicle_type": "CAR",
                    "model_name": "VF 8",
                    "status": "ACTIVE",
                    "slug": "vf-8-eco",
                },
                {
                    "vehicle_id": "wild",
                    "vehicle_type": "CAR",
                    "model_name": "VF Wild",
                    "status": "ARCHIVED",
                    "slug": "vf-wild",
                },
                {
                    "vehicle_id": "bike",
                    "vehicle_type": "ELECTRIC_MOTORBIKE",
                    "model_name": "Evo",
                    "status": "ACTIVE",
                    "slug": "evo",
                },
            ]
        )
    return path


def test_builds_only_current_verified_promotions_with_stable_links(tmp_path: Path) -> None:
    promotions, links = build_car_promotion_rows(
        SALES_POLICY_TEXT,
        VINCLUB_POLICY_TEXT,
        vehicles_csv=_vehicle_csv(tmp_path),
        retrieved_at="2026-08-12T00:00:00+00:00",
    )

    assert {row["promotion_code"] for row in promotions} == {
        "VINCLUB-DAC-BIET-2026-08",
        "MUA-XE-0-DONG-2026",
        "CONG-AN-QUAN-DOI-2026",
        "VNPOST-2026",
        "TRI-AN-XE-XANG-VINFAST-2026",
        "VF3-MIEN-PHI-MAU-SON-NANG-CAO",
    }
    assert all(row["status"] == "ACTIVE" for row in promotions)
    assert all("source_url" in row["eligibility_rules"] for row in promotions)
    assert not any(link["vehicle_id"] in {"wild", "bike"} for link in links)

    general_codes = {
        "VINCLUB-DAC-BIET-2026-08",
        "MUA-XE-0-DONG-2026",
        "CONG-AN-QUAN-DOI-2026",
        "VNPOST-2026",
        "TRI-AN-XE-XANG-VINFAST-2026",
    }
    ids_by_code = {row["promotion_code"]: row["promotion_id"] for row in promotions}
    assert {link["promotion_id"] for link in links if link["vehicle_id"] == "vf8-eco"} == {
        ids_by_code[code] for code in general_codes
    }
    assert len([link for link in links if link["vehicle_id"] == "vf3"]) == 6


def test_rejects_a_policy_document_when_required_markers_disappear(tmp_path: Path) -> None:
    try:
        build_car_promotion_rows(
            "document changed",
            VINCLUB_POLICY_TEXT,
            vehicles_csv=_vehicle_csv(tmp_path),
            retrieved_at="2026-08-12T00:00:00+00:00",
        )
    except ValueError as error:
        assert "missing required policy marker" in str(error)
    else:
        raise AssertionError("crawler must fail closed when the source format changes")
