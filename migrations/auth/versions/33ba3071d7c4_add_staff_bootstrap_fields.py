"""Add temporary-password expiry and first-Admin bootstrap claim.

Revision ID: 33ba3071d7c4
Revises: 2c458fbc011b
Create Date: 2026-07-31 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "33ba3071d7c4"
down_revision: str | None = "2c458fbc011b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add staff temporary-password expiry and the singleton bootstrap claim."""
    op.add_column(
        "auth_users",
        sa.Column("temporary_password_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "auth_bootstrap_admin_claims",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_bootstrap_claims_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    """Remove the Task 5 persistence additions in dependency order."""
    op.drop_table("auth_bootstrap_admin_claims")
    op.drop_column("auth_users", "temporary_password_expires_at")
