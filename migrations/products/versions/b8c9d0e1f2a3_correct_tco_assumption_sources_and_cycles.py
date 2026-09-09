"""Correct TCO assumption sources and private-car inspection cycles.

Revision ID: b8c9d0e1f2a3
Revises: 097257a0543e
Create Date: 2026-08-09 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "097257a0543e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply version 3 assumptions without rewriting migration history."""

    op.execute(
        """
        UPDATE tco_assumptions
        SET inspection_first_month = 36,
            inspection_interval_months = 24,
            inspection_interval_months_after_7y = 12,
            assumption_version = 3,
            source_note = 'Giá điện 3.150 VND/kWh là GIẢ ĐỊNH bình quân, không phải một biểu giá phẳng chính thức; '
                || 'Lệ phí trước bạ ô tô điện 0% theo Nghị định 51/2025/NĐ-CP (đến 28/2/2027) và '
                || 'Nghị định 202/2026/NĐ-CP (có hiệu lực từ 1/3/2027); '
                || 'Lệ phí biển số 14.000.000 chỉ áp dụng giả định khu vực I theo Thông tư 155/2025/TT-BTC; '
                || 'Phí đăng kiểm 250.000 dịch vụ + 40.000 lệ phí cấp giấy chứng nhận, chu kỳ xe con mới '
                || 'không kinh doanh vận tải 36 tháng lần đầu, 24 tháng đến 7 năm và 12 tháng khi trên 7 năm '
                || 'theo Thông tư 47/2024/TT-BGTVT; '
                || 'Bảo hiểm 480.000 VND/năm là GIẢ ĐỊNH mô hình, mức thực tế phụ thuộc số chỗ và phân loại xe '
                || 'theo Nghị định 67/2023/NĐ-CP; Phí đường bộ theo Nghị định 364/2025/NĐ-CP; '
                || 'Chi phí bảo dưỡng 1.500.000 VND/lần là GIẢ ĐỊNH vì chưa có bảng giá cố định chính thức của VinFast',
            updated_at = NOW()
        WHERE vehicle_type = 'CAR'
        """
    )
    op.execute(
        """
        UPDATE tco_assumptions
        SET assumption_version = 3,
            source_note = 'Giá điện 3.150 VND/kWh là GIẢ ĐỊNH bình quân, không phải một biểu giá phẳng chính thức; '
                || 'Lệ phí trước bạ xe máy 2% theo Nghị định 10/2022/NĐ-CP sửa đổi bởi Nghị định 175/2025/NĐ-CP; '
                || 'Chi phí kiểm định khí thải chưa được cộng vì mô hình chưa có mức phí và lộ trình áp dụng theo '
                || 'phương tiện, không được diễn giải là xe máy luôn miễn kiểm định; '
                || 'Bảo hiểm 66.000 VND/năm là GIẢ ĐỊNH mô hình, mức thực tế phụ thuộc phân loại xe theo '
                || 'Nghị định 67/2023/NĐ-CP; Xe máy điện không chịu phí sử dụng đường bộ thu qua đầu phương tiện; '
                || 'Chu kỳ bảo dưỡng 5.000 km theo lịch VinFast; Chi phí bảo dưỡng 200.000 VND/lần là GIẢ ĐỊNH '
                || 'vì chưa có bảng giá cố định chính thức',
            updated_at = NOW()
        WHERE vehicle_type = 'ELECTRIC_MOTORBIKE'
        """
    )


def downgrade() -> None:
    """Restore the version 2 assumptions from the preceding migration."""

    op.execute(
        """
        UPDATE tco_assumptions
        SET inspection_first_month = 30,
            inspection_interval_months = 18,
            inspection_interval_months_after_7y = 12,
            assumption_version = 2,
            source_note = 'Giá điện EVN bậc 5 (giả định bình quân 3.150 VND/kWh, '
                || 'biểu giá thực tế lũy tiến 2.143-4.285 VND/kWh gồm VAT); '
                || 'Lệ phí trước bạ ô tô điện 0% theo Nghị định 51/2025/NĐ-CP '
                || '(đến 28/2/2027) và Nghị định 202/2026/NĐ-CP (đến 31/12/2030); '
                || 'Lệ phí biển số khu vực I theo Thông tư 155/2025/TT-BTC; '
                || 'Phí đăng kiểm 250.000 dịch vụ + 40.000 lệ phí cấp giấy chứng nhận, '
                || 'chu kỳ 30 tháng lần đầu, 18 tháng các lần sau, 12 tháng khi xe quá 7 năm; '
                || 'Bảo hiểm TNDS theo Nghị định 67/2023/NĐ-CP; '
                || 'Phí đường bộ theo Nghị định 364/2025/NĐ-CP; '
                || 'Chi phí bảo dưỡng CHUA CO NGUON CHINH THUC - VinFast khong cong bo bang gia',
            updated_at = NOW()
        WHERE vehicle_type = 'CAR'
        """
    )
    op.execute(
        """
        UPDATE tco_assumptions
        SET assumption_version = 2,
            source_note = 'Giá điện EVN bậc 5 (giả định bình quân 3.150 VND/kWh, '
                || 'biểu giá thực tế lũy tiến 2.143-4.285 VND/kWh gồm VAT); '
                || 'Lệ phí trước bạ xe máy 2% theo Nghị định 10/2022/NĐ-CP sửa đổi bởi '
                || 'Nghị định 175/2025/NĐ-CP; Xe máy điện KHONG phải đăng kiểm định kỳ; '
                || 'Bảo hiểm TNDS theo Nghị định 67/2023/NĐ-CP; '
                || 'Xe máy điện được miễn phí sử dụng đường bộ; '
                || 'Chu kỳ bảo dưỡng 5.000 km theo lịch công bố trên vinfastauto.com; '
                || 'Chi phí bảo dưỡng CHUA CO NGUON CHINH THUC',
            updated_at = NOW()
        WHERE vehicle_type = 'ELECTRIC_MOTORBIKE'
        """
    )
