"""tao bang geocode_cache

Revision ID: c1f7a2d40b3e
Revises: b44e204613af
Create Date: 2026-08-20 10:00:00.000000

Bộ nhớ đệm cho việc đổi một địa danh khách gõ thành toạ độ. Nominatim
(OpenStreetMap) giới hạn 1 request/giây và cấm dùng ồ ạt; không có bảng này thì
mỗi lần một khách gõ "Cầu Giấy" là một lần gọi ra ngoài cho cùng một câu trả
lời — trả tiền bằng độ trễ của khách và bằng nguy cơ bị chặn IP.

`latitude`/`longitude` cho phép NULL một cách CÓ CHỦ ĐÍCH: một hàng như vậy ghi
lại "địa danh này đã hỏi rồi và nhà cung cấp không biết". Thiếu nó, mỗi lần khách
gõ lại một địa danh sai chính tả là thêm một lần gọi ra ngoài nữa.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1f7a2d40b3e"
down_revision: str | None = "b44e204613af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "geocode_cache",
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("query"),
    )
    op.create_index("ix_geocode_cache_expires_at", "geocode_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_geocode_cache_expires_at", table_name="geocode_cache")
    op.drop_table("geocode_cache")
