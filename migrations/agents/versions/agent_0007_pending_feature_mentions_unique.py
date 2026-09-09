"""Deduplicate pending feature mentions and enforce per-session uniqueness."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0007"
down_revision: str | None = "agent_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "uq_pending_feature_mentions_session_mention"


def upgrade() -> None:
    """Keep smallest UUID per duplicate and enforce future uniqueness."""

    op.execute(
        """
        DELETE FROM pending_feature_mentions duplicate
        USING pending_feature_mentions keeper
        WHERE duplicate.session_id = keeper.session_id
          AND duplicate.raw_mention = keeper.raw_mention
          AND duplicate.applied_at IS NULL
          AND keeper.applied_at IS NULL
          AND duplicate.id > keeper.id
        """
    )
    op.create_index(
        _INDEX_NAME,
        "pending_feature_mentions",
        ["session_id", "raw_mention"],
        unique=True,
        postgresql_where=sa.text("applied_at IS NULL"),
    )


def downgrade() -> None:
    """Remove only uniqueness introduced by this migration."""

    op.drop_index(_INDEX_NAME, table_name="pending_feature_mentions")
