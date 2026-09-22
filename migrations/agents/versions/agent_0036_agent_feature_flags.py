"""Bảng `agent_feature_flags` — cờ động cho đường agent (plan agent-migration Bước 3).

Một hàng/cờ: `enabled` (công tắc chính), `rollout_percent` (0..100, chia phần
trăm tất định theo `customer_id`), `customer_allowlist` (danh sách `customer_id`
ngăn bằng dấu phẩy, thắng phần trăm). Gieo sẵn hàng `agent_fallback` ở trạng
thái TẮT: bảng có mà hàng chưa có cũng được coi là TẮT, nhưng có hàng thì bật
bằng một câu `UPDATE`, không cần `INSERT` tay lúc sự cố.

`downgrade` = DROP TABLE — không đụng bảng nghiệp vụ nào.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0036"
down_revision: str | None = "agent_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_feature_flags",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rollout_percent", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("customer_allowlist", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rollout_percent BETWEEN 0 AND 100", name="ck_agent_feature_flags_rollout_percent"),
    )
    op.execute("INSERT INTO agent_feature_flags (name, enabled) VALUES ('agent_fallback', FALSE)")


def downgrade() -> None:
    op.drop_table("agent_feature_flags")
