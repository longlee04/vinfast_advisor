"""Create agent run and scoring tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "agent_0003"
down_revision: str | None = "agent_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("run_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="CAPTURING"),
        sa.Column("terminal_reason", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.session_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "state IN ('CAPTURING', 'SNAPSHOT_READY', 'PACKAGE_READY', 'PENDING_REVIEW', 'APPROVED', 'DELIVERED', 'FAILED', 'REJECTED')",
            name="ck_agent_runs_state",
        ),
    )
    op.create_index("ix_agent_runs_session", "agent_runs", ["session_id", sa.text("created_at DESC")])
    op.create_index("ix_agent_runs_state", "agent_runs", ["state"])
    op.create_table(
        "run_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_snapshots_run", "run_snapshots", ["run_id"])
    op.create_table(
        "run_candidates",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("layer_reached", sa.String(16), nullable=False),
        sa.Column("rank", sa.SmallInteger()),
        sa.Column("over_budget_percent", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.CheckConstraint("layer_reached IN ('L1', 'L2', 'L3')", name="ck_run_candidates_layer"),
        sa.CheckConstraint("rank IS NULL OR rank BETWEEN 1 AND 3", name="ck_run_candidates_rank"),
    )
    op.create_index("ix_run_candidates_run", "run_candidates", ["run_id", "rank"])
    op.create_table(
        "run_evidence",
        sa.Column("evidence_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("fact_code", sa.String(60), nullable=False),
        sa.Column("source_table", sa.String(60), nullable=False),
        sa.Column("source_id", UUID(as_uuid=False)),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_run_evidence_run", "run_evidence", ["run_id", "fact_code"])
    op.create_table(
        "scoring_result",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("score", sa.Numeric(6, 3), nullable=False),
        sa.Column("reasons", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.CheckConstraint("jsonb_array_length(reasons) >= 2", name="ck_scoring_result_reasons_min"),
    )
    op.create_index("ix_scoring_result_run", "scoring_result", ["run_id", sa.text("score DESC")])
    op.create_table(
        "tco_estimates",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=False), nullable=False),
        sa.Column("assumption_id", UUID(as_uuid=False), nullable=False),
        sa.Column("monthly_distance_km", sa.Numeric(10, 2), nullable=False),
        *[
            sa.Column(name, sa.BigInteger(), nullable=False)
            for name in (
                "promoted_purchase_price_vnd",
                "rolling_fees_vnd",
                "energy_vnd",
                "battery_vnd",
                "scheduled_maintenance_vnd",
                "total_vnd",
            )
        ],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "total_vnd = promoted_purchase_price_vnd + rolling_fees_vnd + energy_vnd + battery_vnd + scheduled_maintenance_vnd",
            name="ck_tco_estimates_total",
        ),
    )
    op.create_index("ix_tco_estimates_run", "tco_estimates", ["run_id"])


def downgrade() -> None:
    for index, table in [
        ("ix_tco_estimates_run", "tco_estimates"),
        ("ix_scoring_result_run", "scoring_result"),
        ("ix_run_evidence_run", "run_evidence"),
        ("ix_run_candidates_run", "run_candidates"),
        ("ix_run_snapshots_run", "run_snapshots"),
        ("ix_agent_runs_state", "agent_runs"),
        ("ix_agent_runs_session", "agent_runs"),
    ]:
        op.drop_index(index, table_name=table)
    for table in ("tco_estimates", "scoring_result", "run_evidence", "run_candidates", "run_snapshots", "agent_runs"):
        op.drop_table(table)
