"""Add official source revisions and reviewed policy applicability scopes.

Revision ID: d0cument0005
Revises: d0cument0004
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "d0cument0005"
down_revision: str | None = "d0cument0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store immutable source revisions and policy applicability independently of Products."""
    op.add_column(
        "documents",
        sa.Column("source_authority", sa.String(24), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column("documents", sa.Column("source_revision", sa.String(80), nullable=True))
    op.add_column("documents", sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("source_etag", sa.String(512), nullable=True))
    op.add_column("documents", sa.Column("source_last_modified", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("supersedes_document_id", UUID(as_uuid=False), nullable=True))
    op.create_check_constraint(
        "ck_documents_source_authority",
        "documents",
        "source_authority IN ('OFFICIAL', 'INTERNAL_APPROVED', 'UNKNOWN')",
    )
    op.create_foreign_key(
        "fk_documents_supersedes_document",
        "documents",
        "documents",
        ["supersedes_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_source_revision", "documents", ["source_url", "source_revision"])
    op.create_index(
        "uq_documents_source_hash",
        "documents",
        ["source_url", "content_hash"],
        unique=True,
        postgresql_where=sa.text(
            "source_url IS NOT NULL AND source_authority IN ('OFFICIAL', 'INTERNAL_APPROVED')"
        ),
    )

    op.create_table(
        "policy_scopes",
        sa.Column("scope_id", UUID(as_uuid=False), nullable=False),
        sa.Column("notification_id", UUID(as_uuid=False), nullable=False),
        sa.Column("source_document_id", UUID(as_uuid=False), nullable=False),
        sa.Column("policy_type", sa.String(40), nullable=False),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("vehicle_type", sa.String(20), nullable=False),
        sa.Column("component", sa.String(40), nullable=False),
        sa.Column("battery_chemistry", sa.String(24), nullable=True),
        sa.Column("ownership_model", sa.String(24), nullable=True),
        sa.Column("usage_type", sa.String(20), nullable=False),
        sa.Column("policy_active_from", sa.Date(), nullable=True),
        sa.Column("policy_active_to", sa.Date(), nullable=True),
        sa.Column("eligibility_basis", sa.String(40), nullable=False),
        sa.Column("eligibility_from", sa.Date(), nullable=True),
        sa.Column("eligibility_to", sa.Date(), nullable=True),
        sa.Column("is_current_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("supersedes_scope_id", UUID(as_uuid=False), nullable=True),
        sa.Column("affected_models", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("resolved_vehicle_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_quotes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_policy_scopes_status"),
        sa.CheckConstraint(
            "eligibility_to IS NULL OR eligibility_from IS NULL OR eligibility_to >= eligibility_from",
            name="ck_policy_scopes_eligibility_period",
        ),
        sa.CheckConstraint(
            "policy_active_to IS NULL OR policy_active_from IS NULL OR policy_active_to >= policy_active_from",
            name="ck_policy_scopes_active_period",
        ),
        sa.CheckConstraint(
            "eligibility_basis <> 'NONE' OR (eligibility_from IS NULL AND eligibility_to IS NULL)",
            name="ck_policy_scopes_eligibility_basis",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["policy_notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_scope_id"], ["policy_scopes.scope_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("scope_id"),
    )
    op.create_index("ix_policy_scopes_source", "policy_scopes", ["source_document_id", "status"])
    op.create_index(
        "ix_policy_scopes_applicability",
        "policy_scopes",
        ["vehicle_type", "topic", "component", "status", "is_current_default"],
    )
    op.add_column("vehicle_documents", sa.Column("policy_scope_id", UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        "fk_vehicle_documents_policy_scope",
        "vehicle_documents",
        "policy_scopes",
        ["policy_scope_id"],
        ["scope_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_vehicle_documents_policy_scope",
        "vehicle_documents",
        ["policy_scope_id", "status", "document_type"],
    )


def downgrade() -> None:
    """Remove policy scopes while preserving older Document tables and corpus rows."""
    op.drop_index("ix_vehicle_documents_policy_scope", table_name="vehicle_documents")
    op.drop_constraint(
        "fk_vehicle_documents_policy_scope", "vehicle_documents", type_="foreignkey"
    )
    op.drop_column("vehicle_documents", "policy_scope_id")
    op.drop_index("ix_policy_scopes_applicability", table_name="policy_scopes")
    op.drop_index("ix_policy_scopes_source", table_name="policy_scopes")
    op.drop_table("policy_scopes")
    op.drop_index("uq_documents_source_hash", table_name="documents")
    op.drop_index("ix_documents_source_revision", table_name="documents")
    op.drop_constraint("fk_documents_supersedes_document", "documents", type_="foreignkey")
    op.drop_constraint("ck_documents_source_authority", "documents", type_="check")
    op.drop_column("documents", "supersedes_document_id")
    op.drop_column("documents", "source_last_modified")
    op.drop_column("documents", "source_etag")
    op.drop_column("documents", "source_retrieved_at")
    op.drop_column("documents", "source_published_at")
    op.drop_column("documents", "source_revision")
    op.drop_column("documents", "source_authority")
