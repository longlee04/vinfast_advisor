"""Expand quote audit tiers for evidence-backed delivery and advisor handoff."""

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0017"
down_revision: str | None = "agent_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TIER_CHECK = "tier IN ('NON_QUOTE', 'DETERMINISTIC_AUTO', 'SYNC_HITL')"
_NEW_TIER_CHECK = (
    "tier IN ('NON_QUOTE', 'DETERMINISTIC_AUTO', 'EVIDENCE_BACKED_AUTO', "
    "'SYNC_HITL', 'ADVISOR_HANDOFF')"
)


def upgrade() -> None:
    """Allow the two semantic outcomes introduced by output-risk policy."""

    op.drop_constraint(
        "ck_quote_audit_log_tier", "quote_audit_log", type_="check"
    )
    op.create_check_constraint(
        "ck_quote_audit_log_tier", "quote_audit_log", _NEW_TIER_CHECK
    )


def downgrade() -> None:
    """Map new outcomes to legacy equivalents before restoring the old check."""

    op.execute(
        "UPDATE quote_audit_log SET tier = CASE "
        "WHEN tier = 'EVIDENCE_BACKED_AUTO' THEN 'DETERMINISTIC_AUTO' "
        "WHEN tier = 'ADVISOR_HANDOFF' THEN 'SYNC_HITL' ELSE tier END "
        "WHERE tier IN ('EVIDENCE_BACKED_AUTO', 'ADVISOR_HANDOFF')"
    )
    op.drop_constraint(
        "ck_quote_audit_log_tier", "quote_audit_log", type_="check"
    )
    op.create_check_constraint(
        "ck_quote_audit_log_tier", "quote_audit_log", _OLD_TIER_CHECK
    )
