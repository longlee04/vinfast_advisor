"""them chu ky dang kiem va sua so lieu tco

Revision ID: 097257a0543e
Revises: d4e5f6a7b8c9
Create Date: 2026-08-08 13:51:05.474496

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '097257a0543e'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('tco_assumptions', sa.Column('inspection_first_month', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('tco_assumptions', sa.Column('inspection_interval_months', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('tco_assumptions', sa.Column('inspection_interval_months_after_7y', sa.SmallInteger(), server_default='0', nullable=False))

    # Ba con số chu kỳ đăng kiểm nằm trong dữ liệu chứ không viết cứng trong
    # mã, để lần sau quy định đổi thì sửa dữ liệu chứ không phải sửa code.
    op.execute(
        """
        UPDATE tco_assumptions
        SET inspection_first_month = 30,
            inspection_interval_months = 18,
            inspection_interval_months_after_7y = 12,
            plate_fee_vnd = 14000000,
            inspection_fee_vnd = 290000,
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
        SET inspection_first_month = 0,
            inspection_interval_months = 0,
            inspection_interval_months_after_7y = 0,
            maintenance_interval_km = 5000,
            assumption_version = 2,
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


def downgrade() -> None:
    op.execute(
        "UPDATE tco_assumptions SET plate_fee_vnd = 20000000, inspection_fee_vnd = 340000, "
        "assumption_version = 1 WHERE vehicle_type = 'CAR'"
    )
    op.execute(
        "UPDATE tco_assumptions SET maintenance_interval_km = 4000, assumption_version = 1 "
        "WHERE vehicle_type = 'ELECTRIC_MOTORBIKE'"
    )

    op.drop_column('tco_assumptions', 'inspection_interval_months_after_7y')
    op.drop_column('tco_assumptions', 'inspection_interval_months')
    op.drop_column('tco_assumptions', 'inspection_first_month')
