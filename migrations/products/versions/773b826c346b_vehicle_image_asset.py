"""vehicle image asset

Revision ID: 773b826c346b
Revises: b8c9d0e1f2a3
Create Date: 2026-08-11 23:44:35.120771

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '773b826c346b'
down_revision: str | None = 'b8c9d0e1f2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Thêm chỗ trỏ tới ảnh đã tải về MinIO.

    Hai cột `NULL` được: xe chưa đồng bộ ảnh là trạng thái bình thường, không
    phải lỗi dữ liệu (PRD mục 9 — thiếu là thiếu).
    """
    op.add_column("vehicles", sa.Column("image_object_key", sa.Text(), nullable=True))
    op.add_column("vehicles", sa.Column("image_sha256", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "image_sha256")
    op.drop_column("vehicles", "image_object_key")
