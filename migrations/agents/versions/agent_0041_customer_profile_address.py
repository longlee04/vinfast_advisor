"""Địa chỉ khách trong `customer_profiles` — khách tự khai sau khi đăng nhập (plan Customer 360 §19).

Tên/SĐT đã được đồng bộ từ `auth_user_profiles` (4F); địa chỉ thì chưa có chỗ chứa bên agents,
nên tư vấn viên không thấy dù khách đã khai. Cột mới, cho phép NULL — không backfill: lần đồng
bộ kế tiếp (khách lưu hồ sơ / job nền) tự lấp.

Revision ID: agent_0041
Revises: agent_0040
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0041"
down_revision: str | None = "agent_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customer_profiles", sa.Column("address", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("customer_profiles", "address")
