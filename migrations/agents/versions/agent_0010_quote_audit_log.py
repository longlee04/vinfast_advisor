"""Audit every quote-risk gate decision, including the auto-approved ones."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "agent_0010"
down_revision: str | None = "agent_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "quote_audit_log"


def upgrade() -> None:
    """Bảng audit cho A7-4 — nới HITL thì phải có bằng chứng đã nới đúng.

    Ghi CẢ case auto-approve, không chỉ case bị chặn: bỏ giám sát nhánh tự động
    là bỏ đúng nhánh cần bằng chứng nhất. `run_id` để rời, không FK, vì lượt tra
    giá niêm yết thuần không mở `agent_runs` nào.
    """

    op.create_table(
        _TABLE,
        sa.Column("audit_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tier", sa.String(24), nullable=False),
        sa.Column("requires_hitl", sa.Boolean(), nullable=False),
        # Kết quả luồng CŨ trên cùng lượt — cột so sánh của shadow-mode (A9 KPI).
        sa.Column("legacy_requires_hitl", sa.Boolean(), nullable=False),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "sampled_for_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("near_threshold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("output_content", sa.Text(), nullable=False),
        sa.Column("evaluation", JSONB(), nullable=False),
        sa.Column("reasons", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tier IN ('NON_QUOTE', 'DETERMINISTIC_AUTO', 'SYNC_HITL')",
            name="ck_quote_audit_log_tier",
        ),
    )
    op.create_index(f"ix_{_TABLE}_tier", _TABLE, ["tier", sa.text("created_at DESC")])
    op.create_index(
        f"ix_{_TABLE}_sampled", _TABLE, ["sampled_for_review", sa.text("created_at DESC")]
    )
    op.create_index(
        f"ix_{_TABLE}_near_threshold", _TABLE, ["near_threshold", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    """Bỏ audit; cổng rủi ro vẫn quyết định như cũ, chỉ mất dấu vết."""

    op.drop_index(f"ix_{_TABLE}_near_threshold", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_sampled", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_tier", table_name=_TABLE)
    op.drop_table(_TABLE)
