"""Tach du lieu tco_assumptions theo hai khu vuc le phi bien so.

Revision ID: a1b2c3d4e5f6
Revises: f7e8d9c0b1a2
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7e8d9c0b1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Phiên bản mới. Bảng đang ở version 3 — KHÔNG dùng 2 như bản kế hoạch ban đầu
# viết, vì lùi số hiệu làm `order_by(assumption_version desc)` ở repository chọn
# nhầm dòng cũ.
_NEW_VERSION = 4
_OLD_VERSION = 3

_CAR_SOURCE_II = (
    "[GIẢ ĐỊNH] Giá điện EVN bậc 5 bình quân 3.150 VND/kWh, biểu giá thực tế lũy tiến "
    "2.143-4.285 VND/kWh gồm VAT; Lệ phí trước bạ ô tô điện 0% theo Nghị định "
    "51/2025/NĐ-CP (đến 28/2/2027) và Nghị định 202/2026/NĐ-CP (đến 31/12/2030); "
    "Lệ phí biển số Khu vực II (ngoài Hà Nội, TP.HCM) theo Thông tư 155/2025/TT-BTC; "
    "Phí đăng kiểm 250.000 dịch vụ + 40.000 lệ phí cấp giấy chứng nhận, chu kỳ 30 tháng "
    "lần đầu, 18 tháng các lần sau, 12 tháng khi xe quá 7 năm; Bảo hiểm TNDS theo Nghị "
    "định 67/2023/NĐ-CP; Phí đường bộ theo Nghị định 364/2025/NĐ-CP; Chi phí bảo dưỡng "
    "CHUA CO NGUON CHINH THUC - VinFast khong cong bo bang gia"
)
_MOTORBIKE_SOURCE = (
    "[GIẢ ĐỊNH] Giá điện EVN bậc 5 bình quân 3.150 VND/kWh, biểu giá thực tế lũy tiến "
    "2.143-4.285 VND/kWh gồm VAT; Lệ phí trước bạ xe máy 2% theo Nghị định 10/2022/NĐ-CP "
    "sửa đổi bởi Nghị định 175/2025/NĐ-CP; Xe máy điện KHONG phải đăng kiểm định kỳ theo "
    "quy định hiện hành — con số 0 lần đăng kiểm phản ánh dữ liệu tại thời điểm này và "
    "không được diễn giải là xe máy luôn miễn kiểm định; "
    "Bảo hiểm TNDS theo Nghị định 67/2023/NĐ-CP; Xe máy điện được miễn phí sử dụng đường "
    "bộ; Chu kỳ bảo dưỡng 5.000 km theo lịch công bố trên vinfastauto.com; Chi phí bảo "
    "dưỡng CHUA CO NGUON CHINH THUC"
)


def upgrade() -> None:
    """Tách một dòng `VN` dùng chung thành hai dòng theo khu vực.

    Lệ phí đăng ký biển số ô tô chênh nhau 100 lần giữa hai khu vực (14.000.000
    và 140.000 đồng). Dùng chung một dòng cho cả nước nghĩa là mọi khách ngoài
    Hà Nội/TP.HCM đọc được con số cao hơn thực tế gần 14 triệu — sai đúng ở khoản
    khách mang đi so với báo giá đại lý.

    Chỉ đụng `tco_assumptions`. Cột `region_code` và ba cột chu kỳ đăng kiểm ĐÃ
    tồn tại (kiểm tra schema trước khi viết), unique constraint cũng đã gồm
    `region_code`, nên đây là migration THUẦN DỮ LIỆU — không `add_column`,
    không đổi constraint.
    """

    # Ô tô: dòng hiện có trở thành Khu vực II (baseline — đa số khách ở ngoài
    # Hà Nội/TP.HCM), kèm chu kỳ đăng kiểm hợp pháp thay cho 0/0/0 đang lưu.
    op.execute(
        f"""
        UPDATE tco_assumptions
        SET region_code = 'KHU_VUC_II',
            plate_fee_vnd = 140000,
            inspection_first_month = 30,
            inspection_interval_months = 18,
            inspection_interval_months_after_7y = 12,
            inspection_fee_vnd = 290000,
            assumption_version = {_NEW_VERSION},
            source_note = '{_CAR_SOURCE_II}',
            updated_at = NOW()
        WHERE vehicle_type = 'CAR'
        """
    )
    # Khu vực I nhân bản từ dòng vừa chuẩn hoá, chỉ khác lệ phí biển số.
    # `assumption_id` và `valid_from` là NOT NULL không có default — phải cấp
    # tường minh, template bỏ sót hai cột này sẽ vỡ ngay khi chạy.
    op.execute(
        """
        INSERT INTO tco_assumptions (
            assumption_id, vehicle_type, region_code, electricity_vnd_per_kwh,
            horizon_months, registration_fee_percent, registration_fee_flat_vnd,
            plate_fee_vnd, inspection_fee_vnd, inspection_first_month,
            inspection_interval_months, inspection_interval_months_after_7y,
            mandatory_insurance_vnd_per_year, road_fee_vnd_per_year,
            maintenance_vnd_per_service, maintenance_interval_km,
            status, assumption_version, source_note, valid_from, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), vehicle_type, 'KHU_VUC_I', electricity_vnd_per_kwh,
            horizon_months, registration_fee_percent, registration_fee_flat_vnd,
            14000000, inspection_fee_vnd, inspection_first_month,
            inspection_interval_months, inspection_interval_months_after_7y,
            mandatory_insurance_vnd_per_year, road_fee_vnd_per_year,
            maintenance_vnd_per_service, maintenance_interval_km,
            status, assumption_version,
            replace(
                source_note,
                'Khu vực II (ngoài Hà Nội, TP.HCM)',
                'Khu vực I (Hà Nội, TP.HCM)'
            ),
            valid_from, NOW(), NOW()
        FROM tco_assumptions
        WHERE vehicle_type = 'CAR' AND region_code = 'KHU_VUC_II'
        """
    )
    # Xe máy điện: [GIẢ ĐỊNH] một mức phí giống nhau ở cả hai khu vực (Thông tư
    # 155/2025 không tách khu vực cho lệ phí biển số xe máy điện trong dữ liệu
    # đang có). Vẫn tạo ĐỦ HAI DÒNG giá trị bằng nhau chứ không để một dòng
    # dùng chung: bảng khoá theo `(vehicle_type, region_code)` và repository lọc
    # chặt theo vùng, nên một dòng chỉ khớp được nửa số truy vấn — khách Hà Nội
    # hỏi xe máy sẽ nhận `tco_unavailable` dù dữ liệu thực ra có sẵn.
    op.execute(
        f"""
        UPDATE tco_assumptions
        SET region_code = 'KHU_VUC_II',
            inspection_first_month = 0,
            inspection_interval_months = 0,
            inspection_interval_months_after_7y = 0,
            maintenance_interval_km = 5000,
            assumption_version = {_NEW_VERSION},
            source_note = '{_MOTORBIKE_SOURCE}',
            updated_at = NOW()
        WHERE vehicle_type = 'ELECTRIC_MOTORBIKE'
        """
    )
    op.execute(
        """
        INSERT INTO tco_assumptions (
            assumption_id, vehicle_type, region_code, electricity_vnd_per_kwh,
            horizon_months, registration_fee_percent, registration_fee_flat_vnd,
            plate_fee_vnd, inspection_fee_vnd, inspection_first_month,
            inspection_interval_months, inspection_interval_months_after_7y,
            mandatory_insurance_vnd_per_year, road_fee_vnd_per_year,
            maintenance_vnd_per_service, maintenance_interval_km,
            status, assumption_version, source_note, valid_from, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), vehicle_type, 'KHU_VUC_I', electricity_vnd_per_kwh,
            horizon_months, registration_fee_percent, registration_fee_flat_vnd,
            plate_fee_vnd, inspection_fee_vnd, inspection_first_month,
            inspection_interval_months, inspection_interval_months_after_7y,
            mandatory_insurance_vnd_per_year, road_fee_vnd_per_year,
            maintenance_vnd_per_service, maintenance_interval_km,
            status, assumption_version, source_note, valid_from, NOW(), NOW()
        FROM tco_assumptions
        WHERE vehicle_type = 'ELECTRIC_MOTORBIKE' AND region_code = 'KHU_VUC_II'
        """
    )


def downgrade() -> None:
    """Gộp lại một dòng `VN` dùng chung cho cả nước.

    Xoá dòng Khu vực I TRƯỚC khi đổi `region_code` các dòng còn lại: đổi trước
    sẽ tạo hai dòng cùng `(vehicle_type, region_code, assumption_version)` và
    vỡ `uq_tco_assumptions_version`.
    """

    op.execute(
        f"""
        DELETE FROM tco_assumptions
        WHERE region_code = 'KHU_VUC_I' AND assumption_version = {_NEW_VERSION}
        """
    )
    op.execute(
        f"""
        UPDATE tco_assumptions
        SET region_code = 'VN',
            plate_fee_vnd = CASE WHEN vehicle_type = 'CAR' THEN 14000000 ELSE plate_fee_vnd END,
            inspection_first_month = 0,
            inspection_interval_months = 0,
            inspection_interval_months_after_7y = 0,
            assumption_version = {_OLD_VERSION},
            updated_at = NOW()
        WHERE assumption_version = {_NEW_VERSION}
        """
    )
