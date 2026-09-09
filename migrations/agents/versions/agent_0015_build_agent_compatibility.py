"""Repair build-agent objects skipped by the legacy memory revision collision."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "agent_0015"
down_revision: str | None = "agent_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS slot_ask_attempts (
        session_id UUID NOT NULL
            REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
        slot_name VARCHAR(64) NOT NULL,
        ask_count INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (session_id, slot_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_audit_log (
        audit_id UUID PRIMARY KEY,
        session_id UUID NOT NULL
            REFERENCES conversation_sessions(session_id) ON DELETE CASCADE,
        run_id UUID,
        tier VARCHAR(24) NOT NULL,
        requires_hitl BOOLEAN NOT NULL,
        legacy_requires_hitl BOOLEAN NOT NULL,
        shadow_mode BOOLEAN NOT NULL DEFAULT false,
        sampled_for_review BOOLEAN NOT NULL DEFAULT false,
        near_threshold BOOLEAN NOT NULL DEFAULT false,
        user_message TEXT NOT NULL,
        output_content TEXT NOT NULL,
        evaluation JSONB NOT NULL,
        reasons JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT ck_quote_audit_log_tier
            CHECK (tier IN ('NON_QUOTE', 'DETERMINISTIC_AUTO', 'SYNC_HITL'))
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_quote_audit_log_tier
    ON quote_audit_log (tier, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_quote_audit_log_sampled
    ON quote_audit_log (sampled_for_review, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_quote_audit_log_near_threshold
    ON quote_audit_log (near_threshold, created_at DESC)
    """,
    """
    ALTER TABLE conversation_sessions
    ADD COLUMN IF NOT EXISTS last_quote_evaluation JSONB
    """,
    """
    ALTER TABLE conversation_sessions
    ADD COLUMN IF NOT EXISTS last_quote_sent_at TIMESTAMP WITH TIME ZONE
    """,
    """
    ALTER TABLE conversation_sessions
    ADD COLUMN IF NOT EXISTS pending_slot_request JSONB
    """,
)


def upgrade() -> None:
    """Restore objects absent from databases that used the old revision IDs."""

    for statement in _UPGRADE_STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    """Preserve objects whose original creating revision cannot be determined safely."""

    # This bridge may run after 0009-0012 created the same objects or may create
    # them for a legacy memory database. Dropping them cannot be made provenance-safe.
    return None
