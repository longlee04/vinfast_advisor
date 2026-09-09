"""Crawl and normalize current official VinFast car promotions.

The source PDFs remain authoritative.  Normalization deliberately fails closed
when required policy markers disappear, so a redesigned or superseded document
cannot silently produce stale promotion rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from curl_cffi import requests
from pypdf import PdfReader

SALES_POLICY_URL = (
    "https://static-cms-prod.vinfastauto.com/"
    "20260805_thong-bao-chinh-sach-thuc-day-ban-hang-o-to-dien-thang-08.2026_0.pdf"
)
VINCLUB_POLICY_URL = (
    "https://static-cms-prod.vinfastauto.com/"
    "20260801_thong-bao-cs-khach-hang-than-thiet-vinclub-thang-08.2026.pdf"
)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VEHICLES = ROOT / "data-p150" / "catalog" / "vehicles.csv"
DEFAULT_PROMOTIONS = ROOT / "data-p150" / "catalog" / "promotions.csv"
DEFAULT_LINKS = ROOT / "data-p150" / "catalog" / "promotion_vehicles.csv"

PROMOTION_FIELDS = (
    "promotion_id",
    "promotion_code",
    "title",
    "description",
    "promotion_type",
    "discount_amount_vnd",
    "discount_percent",
    "region_code",
    "eligibility_rules",
    "status",
    "valid_from",
    "valid_to",
    "created_by",
    "approved_by",
    "approved_at",
    "created_at",
    "updated_at",
)
LINK_FIELDS = ("promotion_id", "vehicle_id", "created_at")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _require_markers(text: str, markers: tuple[str, ...]) -> None:
    normalized = _normalized(text)
    for marker in markers:
        if _normalized(marker) not in normalized:
            raise ValueError(f"missing required policy marker: {marker}")


def _promotion_id(code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vinfast-car-promotion:{code}"))


def _policy_rules(
    *, source_url: str, document_code: str, retrieved_at: str, conditions: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "document_code": document_code,
        "retrieved_at": retrieved_at,
        **conditions,
    }


def _promotion(
    *,
    code: str,
    title: str,
    description: str,
    promotion_type: str,
    valid_from: str,
    valid_to: str,
    rules: dict[str, Any],
    retrieved_at: str,
    discount_percent: str = "",
) -> dict[str, Any]:
    return {
        "promotion_id": _promotion_id(code),
        "promotion_code": code,
        "title": title,
        "description": description,
        "promotion_type": promotion_type,
        "discount_amount_vnd": "",
        "discount_percent": discount_percent,
        "region_code": "VN",
        "eligibility_rules": rules,
        "status": "ACTIVE",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "created_by": "vinfast_policy_crawler",
        "approved_by": "VinFast",
        "approved_at": valid_from,
        "created_at": retrieved_at,
        "updated_at": retrieved_at,
    }


def _active_saleable_cars(vehicles_csv: Path) -> list[dict[str, str]]:
    with vehicles_csv.open(newline="", encoding="utf-8") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row.get("vehicle_type") == "CAR"
            and row.get("status") == "ACTIVE"
            and row.get("model_name") != "VF Wild"
        ]


def build_car_promotion_rows(
    sales_policy_text: str,
    vinclub_policy_text: str,
    *,
    vehicles_csv: Path = DEFAULT_VEHICLES,
    retrieved_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return verified promotion and vehicle-link rows from official policy text."""

    _require_markers(
        sales_policy_text,
        (
            "Miễn phí màu sơn nâng cao",
            "Mua xe 0 Đồng",
            "Công an và Quân đội",
            "VN Post",
            "Tri ân Khách hàng xe xăng VinFast chuyển đổi Xanh",
            "31/12/2026",
        ),
    )
    _require_markers(
        vinclub_policy_text,
        ("VinClub Đặc Biệt", "nhân 03 lần", "31/10/2026"),
    )

    sales_document = "202600805_ThongbaoCSthucdaybanhangotodienVinFasttaiVN"
    vinclub_document = "20260801_ThongbaoCSKHTTVinClubThang082026VN"
    promotions = [
        _promotion(
            code="VINCLUB-DAC-BIET-2026-08",
            title="Ưu đãi VinClub Đặc Biệt",
            description=(
                "Nhân ba quyền lợi VinClub theo hạng thành viên; khách chưa có hạng "
                "được hưởng quyền lợi tương đương hạng Gold theo chính sách."
            ),
            promotion_type="OTHER",
            valid_from="2026-08-01T00:00:00Z",
            valid_to="2026-10-31T23:59:59Z",
            rules=_policy_rules(
                source_url=VINCLUB_POLICY_URL,
                document_code=vinclub_document,
                retrieved_at=retrieved_at,
                conditions={
                    "customer_type": "INDIVIDUAL_RETAIL",
                    "invoice_window": ["2026-08-01", "2026-10-31"],
                    "benefit_multiplier": 3,
                    "base_tier_percent": {"GOLD": 1, "PLATINUM": 2, "DIAMOND": 3},
                },
            ),
            retrieved_at=retrieved_at,
        ),
        _promotion(
            code="MUA-XE-0-DONG-2026",
            title="Chính sách Mua xe 0 Đồng",
            description="Hỗ trợ khoản vay lên tới 100% giá trị xe theo điều kiện tín dụng.",
            promotion_type="FINANCING",
            valid_from="2026-01-04T00:00:00Z",
            valid_to="2026-12-31T23:59:59Z",
            rules=_policy_rules(
                source_url=SALES_POLICY_URL,
                document_code=sales_document,
                retrieved_at=retrieved_at,
                conditions={"maximum_financing_percent": 100, "subject_to_credit_approval": True},
            ),
            retrieved_at=retrieved_at,
        ),
        _promotion(
            code="CONG-AN-QUAN-DOI-2026",
            title="Ưu đãi dành cho Công an và Quân đội",
            description="Giảm 5% MSRP cho người đủ điều kiện và thân nhân theo chính sách.",
            promotion_type="PERCENT_DISCOUNT",
            discount_percent="5",
            valid_from="2026-02-04T00:00:00Z",
            valid_to="2026-12-31T23:59:59Z",
            rules=_policy_rules(
                source_url=SALES_POLICY_URL,
                document_code=sales_document,
                retrieved_at=retrieved_at,
                conditions={"eligible_group": "POLICE_MILITARY_AND_QUALIFYING_RELATIVES"},
            ),
            retrieved_at=retrieved_at,
        ),
        _promotion(
            code="VNPOST-2026",
            title="Ưu đãi dành cho CBNV VNPost",
            description="Giảm 3% MSRP cho CBNV hoặc 5% MSRP cho cán bộ lãnh đạo đủ điều kiện.",
            promotion_type="PERCENT_DISCOUNT",
            valid_from="2026-08-05T00:00:00Z",
            valid_to="2026-12-31T23:59:59Z",
            rules=_policy_rules(
                source_url=SALES_POLICY_URL,
                document_code=sales_document,
                retrieved_at=retrieved_at,
                conditions={"eligible_group": "VNPOST", "discount_percent_by_role": {"EMPLOYEE": 3, "LEADER": 5}},
            ),
            retrieved_at=retrieved_at,
        ),
        _promotion(
            code="TRI-AN-XE-XANG-VINFAST-2026",
            title="Tri ân khách hàng xe xăng VinFast chuyển đổi Xanh",
            description="Voucher 30–80 triệu đồng tùy dòng xe xăng VinFast từng sở hữu.",
            promotion_type="OTHER",
            valid_from="2026-08-05T00:00:00Z",
            valid_to="2026-12-31T23:59:59Z",
            rules=_policy_rules(
                source_url=SALES_POLICY_URL,
                document_code=sales_document,
                retrieved_at=retrieved_at,
                conditions={
                    "must_be_first_owner_of_vinfast_ice_vehicle": True,
                    "voucher_vnd_by_owned_model": {"FADIL": 30_000_000, "LUX_A2.0": 60_000_000, "LUX_SA2.0": 80_000_000},
                    "maximum_vouchers": 2,
                },
            ),
            retrieved_at=retrieved_at,
        ),
        _promotion(
            code="VF3-MIEN-PHI-MAU-SON-NANG-CAO",
            title="VF 3 miễn phí màu sơn nâng cao",
            description="Miễn phí màu sơn nâng cao cho VF 3 Eco/Plus có VIN từ năm 2025 trở về trước.",
            promotion_type="GIFT",
            valid_from="2026-03-25T00:00:00Z",
            valid_to="",
            rules=_policy_rules(
                source_url=SALES_POLICY_URL,
                document_code=sales_document,
                retrieved_at=retrieved_at,
                conditions={"model": "VF 3", "maximum_vin_year": 2025, "until_further_notice": True},
            ),
            retrieved_at=retrieved_at,
        ),
    ]

    cars = _active_saleable_cars(vehicles_csv)
    ids_by_code = {row["promotion_code"]: row["promotion_id"] for row in promotions}
    vf3_id = next((car["vehicle_id"] for car in cars if car["model_name"] == "VF 3"), None)
    links = [
        {"promotion_id": ids_by_code[code], "vehicle_id": car["vehicle_id"], "created_at": retrieved_at}
        for code in ids_by_code
        if code != "VF3-MIEN-PHI-MAU-SON-NANG-CAO"
        for car in cars
    ]
    if vf3_id is not None:
        links.append(
            {
                "promotion_id": ids_by_code["VF3-MIEN-PHI-MAU-SON-NANG-CAO"],
                "vehicle_id": vf3_id,
                "created_at": retrieved_at,
            }
        )
    return promotions, links


def fetch_pdf_text(url: str) -> str:
    """Download an official PDF and return its extracted text."""

    response = requests.get(url, impersonate="chrome", timeout=60)
    response.raise_for_status()
    reader = PdfReader(BytesIO(response.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            if isinstance(output.get("eligibility_rules"), dict):
                output["eligibility_rules"] = json.dumps(
                    output["eligibility_rules"], ensure_ascii=False, separators=(",", ":")
                )
            writer.writerow(output)


def merge_outputs(
    promotions: list[dict[str, Any]],
    links: list[dict[str, str]],
    *,
    promotions_csv: Path = DEFAULT_PROMOTIONS,
    links_csv: Path = DEFAULT_LINKS,
) -> None:
    """Merge stable crawler rows without changing unrelated promotions."""

    new_codes = {row["promotion_code"] for row in promotions}
    new_ids = {str(row["promotion_id"]) for row in promotions}
    old_promotions = [
        row for row in _read_csv(promotions_csv) if row.get("promotion_code") not in new_codes
    ]
    old_links = [row for row in _read_csv(links_csv) if row.get("promotion_id") not in new_ids]
    _write_csv(
        promotions_csv,
        PROMOTION_FIELDS,
        old_promotions + sorted(promotions, key=lambda row: str(row["promotion_code"])),
    )
    _write_csv(
        links_csv,
        LINK_FIELDS,
        old_links
        + sorted(links, key=lambda row: (row["promotion_id"], row["vehicle_id"])),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicles", type=Path, default=DEFAULT_VEHICLES)
    parser.add_argument("--promotions", type=Path, default=DEFAULT_PROMOTIONS)
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC).isoformat()
    promotions, links = build_car_promotion_rows(
        fetch_pdf_text(SALES_POLICY_URL),
        fetch_pdf_text(VINCLUB_POLICY_URL),
        vehicles_csv=args.vehicles,
        retrieved_at=retrieved_at,
    )
    merge_outputs(promotions, links, promotions_csv=args.promotions, links_csv=args.links)
    print(f"Wrote {len(promotions)} car promotions and {len(links)} vehicle links")


if __name__ == "__main__":
    main()
