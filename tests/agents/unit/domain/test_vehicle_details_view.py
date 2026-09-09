"""Thẻ chi tiết xe — dữ liệu CÓ CẤU TRÚC, và chỉ từ nguồn đã xác minh.

Khảo sát 2026-08-28: `components/consultation/` có 12 component, **không cái nào**
nhận thông số. Khách chọn xe xong, câu trả lời về dưới dạng văn xuôi trong
`answer` và `RichText` render nó — nên khách nhận một bảng thông số dạng markdown.

**Cổng tin cậy (2026-08-28, vòng rà soát #4).** Bản đầu của thẻ đổ thẳng
`highlights`/`features`/`safety_systems` của `VehicleOverview` ra ngoài. Ba
trường đó là **trích đoạn RAG thô** từ `vehicle_documents`, lọc duy nhất bằng
`VehicleDocumentRow.status == "ACTIVE"` — tức chứng minh *tài liệu đang hoạt
động*, KHÔNG chứng minh *câu khẳng định này đã được duyệt*. Một đoạn brochure cũ
vẫn `ACTIVE` và vẫn lọt thành "tính năng của xe".

Nên thẻ giờ chỉ chở thứ đọc thẳng từ danh mục: giá, kích thước, vận hành, màu.
Mỗi con số ở đây có một hàng trong `products`, không phải một đoạn văn được xếp
hạng gần đúng.

Luật cũ giữ nguyên: **thiếu dữ liệu là BỎ BỚT**, không bao giờ là ô rỗng.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.vehicle_details import build_vehicle_details
from src.agents.domain.vehicle_overview import (
    ColorInfo,
    DimensionsInfo,
    EngineSpecs,
    EngineVariantSpecs,
    EvidenceItem,
    PriceVariant,
    VehicleOverview,
)


def _overview(**kwargs) -> VehicleOverview:
    base = {"vehicle_name": "VinFast VF 5 All New"}
    base.update(kwargs)
    return VehicleOverview(**base)


def _item(text: str, evidence_id: str = "ev-1") -> EvidenceItem:
    return EvidenceItem(content=text, evidence_id=evidence_id)


def _groups(view) -> dict[str, tuple]:
    return {group.title: group.rows for group in view.spec_groups}


def test_khong_co_gi_de_noi_thi_khong_dung_the() -> None:
    """Thẻ rỗng còn tệ hơn không có thẻ: khách bấm vào một khoảng trắng."""

    assert build_vehicle_details(None) is None
    assert build_vehicle_details(_overview()) is None


@pytest.mark.parametrize("field", ["highlights", "features", "safety_systems"])
def test_trich_doan_rag_khong_dung_noi_the(field: str) -> None:
    """RAG một mình KHÔNG đủ để dựng thẻ.

    Đây là chốt của vòng rà soát #4. `ACTIVE` là trạng thái của TÀI LIỆU; nó
    không nói gì về việc câu trong tài liệu đã được duyệt để nói với khách hay
    chưa. Trước bản này, một đoạn brochure cũ vẫn hiện lên như "tính năng xe".
    """

    assert build_vehicle_details(_overview(**{field: [_item("Cảnh báo điểm mù")]})) is None


def test_trich_doan_rag_khong_lot_vao_the_da_co_thong_so() -> None:
    """Có thông số thật thì dựng thẻ — nhưng RAG vẫn không được đi ké."""

    view = build_vehicle_details(
        _overview(
            dimensions=DimensionsInfo(length_mm=4238),
            features=[_item("Apple CarPlay")],
            safety_systems=[_item("Phanh ABS")],
            highlights=[_item("Thiết kế thể thao")],
        )
    )

    assert view is not None
    flat = " ".join(f"{label} {value}" for rows in _groups(view).values() for label, value in rows)
    assert "CarPlay" not in flat
    assert "ABS" not in flat
    assert "thể thao" not in flat


def test_gia_ban_doc_tu_danh_muc() -> None:
    view = build_vehicle_details(
        _overview(price_variants=[PriceVariant(
                vehicle_id=UUID("11111111-1111-1111-1111-111111111111"),
                variant_name="Eco",
                amount_vnd=Decimal("529000000"),
                price_type="STARTING_PRICE",
                region_code="VN",
            )])
    )

    assert view is not None
    assert _groups(view)["Giá bán"] == (("Eco", "529.000.000 đồng"),)


def test_kich_thuoc_co_ca_khoang_sang_gam() -> None:
    """Khoảng sáng gầm là số khách Việt hỏi nhiều nhất khi lo đường ngập.

    Bản trước đọc bốn chiều rồi bỏ quên nó, dù `DimensionsInfo` có sẵn.
    """

    view = build_vehicle_details(
        _overview(dimensions=DimensionsInfo(length_mm=4238, width_mm=1820, ground_clearance_mm=190))
    )

    assert view is not None
    assert ("Khoảng sáng gầm", "190 mm") in _groups(view)["Kích thước"]


def test_van_hanh_doc_tu_thong_so_dong_co() -> None:
    view = build_vehicle_details(
        _overview(
            engine_specs=EngineSpecs(
                variants=[
                    EngineVariantSpecs(
                        variant_name="Plus",
                        motor_power_kw=Decimal("130"),
                        torque_nm=Decimal("250"),
                        drivetrain="FWD",
                    )
                ]
            )
        )
    )

    assert view is not None
    rows = _groups(view)["Vận hành"]
    assert ("Plus — công suất", "130 kW") in rows
    assert ("Plus — mô-men xoắn", "250 Nm") in rows
    assert ("Plus — dẫn động", "FWD") in rows


def test_mau_lay_ten_danh_muc_khong_lay_trich_doan() -> None:
    """`ColorInfo.names` là danh mục; `evidence_items` là RAG — chỉ lấy vế đầu."""

    view = build_vehicle_details(
        _overview(colors=ColorInfo(names=["Trắng", "Đỏ"], evidence_items=[_item("Bảng màu 2024")]))
    )

    assert view is not None
    assert _groups(view)["Màu sắc"] == (("Màu ngoại thất", "Trắng, Đỏ"),)
    flat = " ".join(f"{label} {value}" for rows in _groups(view).values() for label, value in rows)
    assert "Bảng màu" not in flat


def test_nhom_thong_so_khong_bao_gio_rong() -> None:
    """Nhóm không có số nào thì KHÔNG xuất hiện, thay vì hiện một nhóm trống."""

    view = build_vehicle_details(_overview(dimensions=DimensionsInfo(length_mm=4238)))

    assert view is not None
    for group in view.spec_groups:
        assert group.rows, f"nhóm rỗng lọt ra: {group.title}"


def test_thieu_mot_so_thi_bo_rieng_dong_do() -> None:
    """Thiếu dữ liệu là bỏ bớt — không ô rỗng, không `UNKNOWN`."""

    view = build_vehicle_details(_overview(dimensions=DimensionsInfo(length_mm=4238, width_mm=None)))

    assert view is not None
    labels = {label for label, _ in _groups(view)["Kích thước"]}
    assert labels == {"Dài"}


def test_tinh_nang_doc_tu_co_da_duyet_chu_khong_tu_rag() -> None:
    """Trả lại khối tính năng — nhưng từ nguồn CÓ dấu duyệt.

    Vòng rà soát #4 gỡ `features`/`safety_systems` vì chúng là trích đoạn RAG,
    lọc duy nhất bằng `VehicleDocumentRow.status == "ACTIVE"`. Nguồn đúng là
    `VehicleFacts.features`: chỉ gồm tính năng `status='YES'` **và**
    `verification_status='APPROVED'` — mỗi dòng có một hàng trong catalog.
    """

    view = build_vehicle_details(
        _overview(features=[_item("Trích đoạn RAG không được vào")]),
        features={"ADAS_SUITE": "Gói ADAS", "BLUETOOTH": "Bluetooth"},
    )

    assert view is not None
    groups = _groups(view)
    assert ("Hỗ trợ lái", "Gói ADAS") in groups["An toàn"]
    assert ("Kết nối", "Bluetooth") in groups["Tiện nghi & Kết nối"]
    flat = " ".join(f"{label} {value}" for rows in groups.values() for label, value in rows)
    assert "RAG" not in flat


def test_ma_tinh_nang_la_khong_nam_trong_nhom_nao_thi_bo() -> None:
    """Thà thiếu một dòng còn hơn xếp nó vào nhóm sai.

    Cùng luật với bảng thông số ở `domain/catalog_reply`: mã chưa khai nhóm thì
    KHÔNG xuất hiện, chứ không dồn vào một nhóm "khác".
    """

    view = build_vehicle_details(
        _overview(dimensions=DimensionsInfo(length_mm=4238)),
        features={"MA_LA_HOAN_TOAN": "Thứ gì đó"},
    )

    assert view is not None
    flat = " ".join(f"{label} {value}" for rows in _groups(view).values() for label, value in rows)
    assert "Thứ gì đó" not in flat


def test_khong_co_co_nao_thi_khong_dung_nhom_rong() -> None:
    view = build_vehicle_details(_overview(dimensions=DimensionsInfo(length_mm=4238)), features={})

    assert view is not None
    assert "An toàn" not in _groups(view)
    assert "Tiện nghi & Kết nối" not in _groups(view)


def test_chi_co_co_tinh_nang_cung_du_dung_the() -> None:
    """Cờ đã duyệt là nguồn ĐỦ TIN — một mình nó dựng được thẻ, khác hẳn RAG."""

    view = build_vehicle_details(_overview(), features={"ADAS_SUITE": "Gói ADAS"})

    assert view is not None
    assert _groups(view)["An toàn"] == (("Hỗ trợ lái", "Gói ADAS"),)
