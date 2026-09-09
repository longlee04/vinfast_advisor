"""Allow ADVISOR and SYSTEM roles in conversation_messages check constraint."""

from collections.abc import Sequence

from alembic import op

revision: str = "agent_0021"
down_revision: str | None = "agent_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_conversation_messages_role", "conversation_messages", type_="check")
    op.create_check_constraint(
        "ck_conversation_messages_role",
        "conversation_messages",
        "role IN ('USER', 'ASSISTANT', 'ADVISOR', 'SYSTEM')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_conversation_messages_role", "conversation_messages", type_="check")
    op.create_check_constraint(
        "ck_conversation_messages_role",
        "conversation_messages",
        "role IN ('USER', 'ASSISTANT')",
    )
