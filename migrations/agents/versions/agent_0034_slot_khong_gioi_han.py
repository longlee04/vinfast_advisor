"""Bỏ giới hạn MỘT lịch mỗi khung giờ — bao nhiêu khách đặt cũng nhận.

Sếp 2026-08-31: "bỏ đi giới hạn về đặt lịch, bao nhiêu người đặt cũng được".
Showroom thực tế có nhiều xe và nhiều tư vấn viên; một khung giờ chỉ một khách
là giả định của bản demo, và nó làm ô giờ "kín" mờ đi ngay khi CHỈ MỘT người
đặt. Index quay về dạng thường (đúng bản trước agent_0031) — vẫn giữ để tra
cứu nhanh theo showroom + giờ.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0034"
down_revision: str | None = "agent_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_test_drive_bookings_showroom_time"
_LIVE_ONLY = sa.text("status <> 'CANCELLED'")


def upgrade() -> None:
    op.drop_index(_INDEX, table_name="test_drive_bookings")
    op.create_index(_INDEX, "test_drive_bookings", ["showroom", "scheduled_at"], unique=False, postgresql_where=_LIVE_ONLY)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="test_drive_bookings")
    op.create_index(_INDEX, "test_drive_bookings", ["showroom", "scheduled_at"], unique=True, postgresql_where=_LIVE_ONLY)
