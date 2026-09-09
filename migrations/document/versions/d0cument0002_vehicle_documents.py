"""create vehicle_documents (RAG chunk cho catalog phương tiện)

``vehicle_id`` intentionally has no database foreign key. Product and Document
use independent Alembic chains, so either chain must be able to migrate first.
Referential validation is handled at the application boundary.

Revision ID: d0cument0002
Revises: 4d0cument0001
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

revision: str = "d0cument0002"
down_revision: str | None = "4d0cument0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "vehicle_documents",
        sa.Column("document_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=True),
        sa.Column("source_document_id", UUID(as_uuid=False), nullable=True),
        sa.Column("source_content_hash", sa.String(128), nullable=True),
        sa.Column("source_revision", sa.String(40), nullable=True),
        sa.Column("document_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("embedding_version", sa.String(40), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column(
            "content_tsv",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('simple', coalesce(section_title, '') || ' ' || content)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("document_id"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'ARCHIVED')", name="ck_vehicle_documents_status"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_vehicle_documents_period",
        ),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_vehicle_documents_content"),
        sa.CheckConstraint(
            "status <> 'ACTIVE' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_vehicle_documents_approval",
        ),
    )
    op.create_index(
        "ix_vehicle_documents_scope",
        "vehicle_documents",
        ["vehicle_id", "status", "document_type", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_vehicle_documents_source_document", "vehicle_documents", ["source_document_id"]
    )
    op.create_index(
        "ix_vehicle_documents_content_tsv", "vehicle_documents", ["content_tsv"], postgresql_using="gin"
    )
    op.execute(
        "CREATE INDEX ix_vehicle_documents_embedding_hnsw "
        "ON vehicle_documents USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_documents_embedding_hnsw", table_name="vehicle_documents")
    op.drop_index("ix_vehicle_documents_content_tsv", table_name="vehicle_documents")
    op.drop_index("ix_vehicle_documents_scope", table_name="vehicle_documents")
    op.drop_table("vehicle_documents")
