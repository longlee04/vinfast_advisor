"""Create the policy notification MVP aggregate.

Revision ID: d0cument0004
Revises: d0cument0003
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "d0cument0004"
down_revision: str | None = "d0cument0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one table for analysis, draft review, and publication."""
    op.create_table(
        "policy_notifications",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("source_document_id", UUID(as_uuid=False), nullable=False),
        sa.Column("policy_type", sa.String(40), nullable=False),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("secondary_topics", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("affected_models", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("facts", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ai_confidence", sa.Float(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("published_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_policy_notifications_status"),
        sa.CheckConstraint(
            "ai_confidence >= 0 AND ai_confidence <= 1",
            name="ck_policy_notifications_confidence",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(content)) > 0",
            name="ck_policy_notifications_copy_present",
        ),
        sa.CheckConstraint(
            "status = 'draft' OR (published_by IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_policy_notifications_publication_actor",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_policy_notifications_source_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id", name="uq_policy_notifications_source_document"),
    )
    op.create_index(
        "ix_policy_notifications_status_published",
        "policy_notifications",
        ["status", "published_at", "id"],
    )
    op.create_index(
        "ix_policy_notifications_created",
        "policy_notifications",
        ["created_at", "id"],
    )


def downgrade() -> None:
    """Remove only the policy notification MVP aggregate."""
    op.drop_index("ix_policy_notifications_created", table_name="policy_notifications")
    op.drop_index("ix_policy_notifications_status_published", table_name="policy_notifications")
    op.drop_table("policy_notifications")
