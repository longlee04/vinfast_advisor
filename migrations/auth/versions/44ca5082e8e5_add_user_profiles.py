"""Add auth_user_profiles table.

Revision ID: 44ca5082e8e5
Revises: 33ba3071d7c4
Create Date: 2026-08-21 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "44ca5082e8e5"
down_revision: str | None = "33ba3071d7c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create auth_user_profiles table."""
    op.create_table(
        "auth_user_profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("showroom_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_user_profiles_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """Drop auth_user_profiles table."""
    op.drop_table("auth_user_profiles")
