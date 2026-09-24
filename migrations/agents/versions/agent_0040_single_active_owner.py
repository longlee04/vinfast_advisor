"""Mỗi khách tối đa MỘT người phụ trách đang hiệu lực (tư vấn viên tự nhận khách).

Phân công không còn do Admin làm tay: tư vấn viên nhận khách khi tiếp quản hội thoại hoặc
bấm "Nhận khách" ở hàng chờ. Hai tư vấn viên có thể bấm cùng lúc, nên ràng buộc nằm ở
database: unique index một phần trên `customer_id` với `status = 'ACTIVE'`, để câu
`INSERT … ON CONFLICT DO NOTHING` quyết người thắng một cách nguyên tử.

Trước khi tạo index, các dòng ACTIVE trùng (dữ liệu cũ do Admin gán chồng) được đóng lại,
chỉ giữ dòng mới nhất — cùng quy ước `assign_customer` đang dùng (`TRANSFERRED`).

Revision ID: agent_0040
Revises: agent_0039
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0040"
down_revision: str | None = "agent_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE customer_advisor_assignments a
        SET status = 'TRANSFERRED', unassigned_at = now(), updated_at = now()
        WHERE a.status = 'ACTIVE'
          AND EXISTS (
              SELECT 1 FROM customer_advisor_assignments newer
              WHERE newer.customer_id = a.customer_id AND newer.status = 'ACTIVE'
                AND (newer.assigned_at, newer.assignment_id) > (a.assigned_at, a.assignment_id)
          )
        """
    )
    op.create_index(
        "uq_customer_advisor_assignments_active",
        "customer_advisor_assignments",
        ["customer_id"],
        unique=True,
        postgresql_where="status = 'ACTIVE'",
    )


def downgrade() -> None:
    op.drop_index("uq_customer_advisor_assignments_active", table_name="customer_advisor_assignments")
