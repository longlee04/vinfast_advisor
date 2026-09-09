"""Create funnel metrics view."""

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0006"
down_revision: str | None = "agent_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """CREATE VIEW funnel_metrics AS SELECT date_trunc('day', cs.started_at) AS day, count(DISTINCT cs.session_id) AS sessions_started, count(DISTINCT cs.session_id) FILTER (WHERE EXISTS (SELECT 1 FROM conversation_slots slot WHERE slot.session_id = cs.session_id)) AS sessions_with_profile, count(DISTINCT ar.session_id) FILTER (WHERE ar.state IN ('PENDING_REVIEW', 'APPROVED', 'DELIVERED')) AS sessions_with_recommendation, count(DISTINCT rq.session_id) FILTER (WHERE rq.status = 'APPROVED') AS sessions_approved, count(DISTINCT tdb.customer_id) FILTER (WHERE tdb.status <> 'CANCELLED') AS sessions_booked FROM conversation_sessions cs LEFT JOIN agent_runs ar ON ar.session_id = cs.session_id LEFT JOIN review_queue rq ON rq.session_id = cs.session_id LEFT JOIN test_drive_bookings tdb ON tdb.customer_id = cs.customer_id GROUP BY date_trunc('day', cs.started_at)"""
    )


def downgrade() -> None:
    op.execute("DROP VIEW funnel_metrics")
