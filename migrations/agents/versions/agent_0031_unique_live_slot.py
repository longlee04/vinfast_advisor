"""Một khung giờ showroom chỉ được có MỘT lịch còn sống.

`SLOT_CAPACITY = 1` trước nay chỉ do mã ứng dụng giữ: `book` đếm rồi ghi trong
cùng một transaction. Ở mức cô lập mặc định của Postgres (READ COMMITTED) hai
transaction song song vẫn cùng đếm ra 0 rồi cùng ghi — đúng khoảng thời gian hai
khách bấm cùng một nút trên thẻ chọn giờ.

Hậu quả nếu để hở: hai khách cùng nhận câu "đã đặt lịch", cùng tới showroom một
giờ, và không ai biết cho tới lúc họ có mặt.

Chỉ đổi index cũ thành UNIQUE, giữ nguyên điều kiện `status <> 'CANCELLED'`: một
lịch đã huỷ KHÔNG được giữ chỗ, nếu không thì huỷ xong khung đó chết vĩnh viễn.

Đã đếm trên prod trước khi viết (2026-08-28): 12 bản ghi, 0 khung trùng — nên
migration này không vấp dữ liệu cũ.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0031"
down_revision: str | None = "agent_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_test_drive_bookings_showroom_time"
_LIVE_ONLY = sa.text("status <> 'CANCELLED'")


def upgrade() -> None:
    op.drop_index(_INDEX, table_name="test_drive_bookings")
    op.create_index(
        _INDEX,
        "test_drive_bookings",
        ["showroom", "scheduled_at"],
        unique=True,
        postgresql_where=_LIVE_ONLY,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="test_drive_bookings")
    op.create_index(
        _INDEX,
        "test_drive_bookings",
        ["showroom", "scheduled_at"],
        unique=False,
        postgresql_where=_LIVE_ONLY,
    )
