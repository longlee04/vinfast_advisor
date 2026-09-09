"""create document schema

Revision ID: 4d0cument0001
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4d0cument0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("document_type", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=True),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("approval_status", sa.String(length=100), nullable=False),
        sa.Column("processing_status", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_by", sa.String(length=64), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(title) > 0", name="ck_documents_title_present"),
        sa.CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_documents_byte_size_non_negative"),
        sa.CheckConstraint("approval_status IN ('draft')", name="ck_documents_approval_status"),
        sa.CheckConstraint("processing_status IN ('not_started', 'queued', 'processing', 'completed', 'failed')", name="ck_documents_processing_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_active", "documents", ["archived_at"], unique=False, postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_documents_created_desc", "documents", ["created_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_created_desc", table_name="documents")
    op.drop_index("ix_documents_active", table_name="documents", postgresql_where=sa.text("archived_at IS NULL"))
    op.drop_table("documents")
