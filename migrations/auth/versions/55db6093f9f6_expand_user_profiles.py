"""Expand user profile fields for customer preferences and advisor title.

Revision ID: 55db6093f9f6
Revises: 44ca5082e8e5
Create Date: 2026-08-21 00:31:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "55db6093f9f6"
down_revision: str | None = "44ca5082e8e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add customer preferences and advisor bio/title fields."""
    op.add_column("auth_user_profiles", sa.Column("vehicle_preference", sa.String(length=50), nullable=True))
    op.add_column("auth_user_profiles", sa.Column("budget_preference", sa.String(length=100), nullable=True))
    op.add_column("auth_user_profiles", sa.Column("seats_preference", sa.String(length=20), nullable=True))
    op.add_column("auth_user_profiles", sa.Column("home_charging", sa.Boolean(), nullable=True))
    op.add_column("auth_user_profiles", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("auth_user_profiles", sa.Column("bio", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Drop extended profile columns."""
    op.drop_column("auth_user_profiles", "bio")
    op.drop_column("auth_user_profiles", "title")
    op.drop_column("auth_user_profiles", "home_charging")
    op.drop_column("auth_user_profiles", "seats_preference")
    op.drop_column("auth_user_profiles", "budget_preference")
    op.drop_column("auth_user_profiles", "vehicle_preference")
