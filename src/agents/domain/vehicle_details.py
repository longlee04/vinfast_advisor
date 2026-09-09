"""Thẻ chi tiết xe — đưa dữ liệu ĐÃ XÁC MINH ra ngoài mà không đi qua văn xuôi.

Khảo sát 2026-08-28: `frontend/src/components/consultation/` có 12 component,
**không cái nào** nhận thông số. Khách chốt xe xong, câu trả lời về dưới dạng chữ
trong `answer` và `RichText` render nó — nên khách nhận một bảng thông số dạng
markdown, đúng thứ đo được trên prod.

**Cổng tin cậy (vòng rà soát #4).** Bản đầu đổ thẳng `highlights` / `features` /
`safety_systems` của `VehicleOverview` ra thẻ. Ba trường ấy là **trích đoạn RAG
thô** từ `vehicle_documents`, lọc duy nhất bằng `VehicleDocumentRow.status ==
"ACTIVE"` — trạng thái của TÀI LIỆU, không phải dấu duyệt cho từng câu khẳng
định. Một đoạn brochure cũ vẫn `ACTIVE`, và vẫn hiện lên như "tính năng của xe".

Nên thẻ chỉ chở thứ đọc thẳng từ danh mục: **giá · kích thước · vận hành · màu**.
Mỗi con số có một hàng trong `products`, không phải một đoạn văn được xếp hạng
gần đúng.

NỢ ĐÃ BIẾT: tính năng và an toàn sẽ quay lại khi nối `vehicle_feature_flags`
(`status == "YES"`) vào seam này — đó mới là nguồn có dấu duyệt cho từng tính
năng. Chưa nối được ở đây vì `VehicleOverview` không mang cờ tính năng.

Một luật xuyên suốt: **thiếu dữ liệu là BỎ BỚT.** Không ô rỗng, không chữ giữ
chỗ, không `UNKNOWN`. Một thẻ trống còn tệ hơn không có thẻ — khách bấm vào một
khoảng trắng và không hiểu mình vừa làm gì sai.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.agents.contracts import SpecGroup, VehicleDetailsView
from src.agents.domain.catalog_reply import COMFORT_CODES, INFOTAINMENT_CODES, SAFETY_CODES
from src.agents.domain.vehicle_overview import VehicleOverview

#: Nhãn hiển thị cho từng mã tính năng đã duyệt. Mã KHÔNG có nhãn ở đây sẽ không
#: xuất hiện — cùng luật với bảng thông số: thà thiếu một dòng còn hơn xếp nó vào
#: nhóm sai.
_FEATURE_LABELS: Mapping[str, str] = {
    "ADAS_SUITE": "Hỗ trợ lái",
    "ANTI_THEFT": "Chống trộm",
    "BLUETOOTH": "Kết nối",
    "ESIM": "Kết nối",
    "GPS": "Định vị",
    "MOBILE_APP": "Ứng dụng",
    "PANORAMIC_ROOF": "Cửa sổ trời",
}


def _dimension_rows(overview: VehicleOverview) -> tuple[tuple[str, str], ...]:
    dims = overview.dimensions
    if dims is None:
        return ()
    labelled = (
        ("Dài", dims.length_mm),
        ("Rộng", dims.width_mm),
        ("Cao", dims.height_mm),
        ("Chiều dài cơ sở", dims.wheelbase_mm),
        # Khoảng sáng gầm là số khách Việt hỏi nhiều nhất khi lo đường ngập —
        # bản trước đọc bốn chiều rồi bỏ quên nó dù dữ liệu có sẵn.
        ("Khoảng sáng gầm", dims.ground_clearance_mm),
    )
    return tuple((label, f"{value} mm") for label, value in labelled if value is not None)


def _price_rows(overview: VehicleOverview) -> tuple[tuple[str, str], ...]:
    return tuple(
        (variant.variant_name, f"{variant.amount_vnd:,.0f} đồng".replace(",", "."))
        for variant in overview.price_variants
    )


def _engine_rows(overview: VehicleOverview) -> tuple[tuple[str, str], ...]:
    """Vận hành theo TỪNG phiên bản: hai phiên bản khác công suất là chuyện thường."""

    specs = overview.engine_specs
    if specs is None:
        return ()
    rows: list[tuple[str, str]] = []
    for variant in specs.variants:
        labelled = (
            ("công suất", variant.motor_power_kw, "kW"),
            ("mô-men xoắn", variant.torque_nm, "Nm"),
            ("dẫn động", variant.drivetrain, ""),
        )
        for name, value, unit in labelled:
            if value is None:
                continue
            text = f"{value:,.0f} {unit}".replace(",", ".") if unit else str(value)
            rows.append((f"{variant.variant_name} — {name}", text.strip()))
    return tuple(rows)


def _colour_rows(overview: VehicleOverview) -> tuple[tuple[str, str], ...]:
    """Chỉ `names` — đó là danh mục. `evidence_items` là RAG, không lấy."""

    colours = overview.colors
    if colours is None or not colours.names:
        return ()
    return (("Màu ngoại thất", ", ".join(colours.names)),)


def _feature_rows(features: Mapping[str, str], codes: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Các tính năng xe THẬT SỰ có trong một nhóm, theo đúng thứ tự khai.

    `features` chỉ chứa tính năng `status='YES'` và `verification_status='APPROVED'`
    (xem `contracts.VehicleFacts.features`) — đó là dấu duyệt mà trích đoạn RAG
    không có, và là lý do khối này được phép quay lại thẻ.
    """

    return tuple(
        (label, name)
        for code in codes
        if (name := features.get(code)) and (label := _FEATURE_LABELS.get(code))
    )


def build_vehicle_details(
    overview: VehicleOverview | None,
    *,
    features: Mapping[str, str] | None = None,
) -> VehicleDetailsView | None:
    """Thẻ chi tiết, hoặc `None` khi không có gì đáng hiện.

    `None` khi mọi nhóm đều rỗng — đó là "không có gì để nói", và im lặng ở đây
    trung thực hơn một cái thẻ trắng. Một `VehicleOverview` chỉ có trích đoạn RAG
    cũng rơi vào nhánh này: RAG một mình KHÔNG dựng nổi thẻ.
    """

    if overview is None:
        return None
    flags = features or {}
    groups = tuple(
        SpecGroup(title=title, rows=rows)
        for title, rows in (
            ("Giá bán", _price_rows(overview)),
            ("Kích thước", _dimension_rows(overview)),
            ("Vận hành", _engine_rows(overview)),
            ("Màu sắc", _colour_rows(overview)),
            ("An toàn", _feature_rows(flags, SAFETY_CODES)),
            ("Tiện nghi & Kết nối", _feature_rows(flags, INFOTAINMENT_CODES + COMFORT_CODES)),
        )
        if rows
    )
    if not groups:
        return None
    return VehicleDetailsView(vehicle_name=overview.vehicle_name, spec_groups=groups)
