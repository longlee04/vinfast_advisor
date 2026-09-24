"""SQLAlchemy mappings for the Agent persistence schema."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AgentBase(DeclarativeBase):
    """Own Agent tables without coupling migration metadata to other modules."""


class ConversationSessionRow(AgentBase):
    """Mutable row persisted for one customer conversation session."""

    __tablename__ = "conversation_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'COMPLETED', 'ABANDONED')", name="ck_conversation_sessions_status"),
        CheckConstraint(
            "ownership IN ('AI', 'PENDING_HANDOFF', 'HUMAN')",
            name="ck_conversation_sessions_ownership",
        ),
        CheckConstraint(
            "vehicle_type_hint IS NULL OR vehicle_type_hint IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_conversation_sessions_vehicle_type",
        ),
        Index("ix_conversation_sessions_customer", "customer_id", text("started_at DESC")),
        Index(
            "ix_conversation_sessions_customer_activity",
            "customer_id",
            "archived_at",
            "last_activity_at",
        ),
        Index("ix_conversation_sessions_advisor", "assigned_advisor_id", "status"),
        Index(
            "ix_conversation_sessions_state_last_activity",
            "status",
            "last_activity_at",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64))
    assigned_advisor_id: Mapped[str | None] = mapped_column(String(64))
    vehicle_type_hint: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), server_default=text("'ACTIVE'"))
    ownership: Mapped[str] = mapped_column(String(24), server_default=text("'AI'"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A7-5: đánh giá của báo giá GẦN NHẤT đã gửi trong phiên, để lượt xác nhận
    # tiếp theo tái dùng thay vì dựng lại từ một lượt không mang thông tin nào.
    last_quote_evaluation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_quote_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A7-10: slot đang chờ khách trả lời (intent + slot + form dở dang + thời
    # điểm hỏi). Một cột JSONB vì đây là một bản ghi nguyên khối, luôn đọc/ghi
    # cùng lúc và không có truy vấn nào lọc theo trường bên trong.
    pending_slot_request: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    # Focused operational task. Unlike transcript/summary, this is validated
    # machine-readable state used to continue or revise a completed tool call.
    active_task_state: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    # Lớp 4 nhận diện ý định: câu xác nhận đang chờ khách gật/lắc. Cột RIÊNG chứ
    # không dùng chung `pending_slot_request`: hai bản ghi trả lời hai câu hỏi
    # khác nhau ("thiếu giá trị nào" vs "hiểu đúng ý chưa") và có hai vòng đời
    # khác nhau — xem `domain/pending_intent_confirmation.py`.
    pending_intent_confirmation: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    # Vị trí người dùng (toạ độ + địa danh) được ghi nhớ theo phiên
    user_location: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationSlotRow(AgentBase):
    """Mutable confirmed value for one named conversation slot."""

    __tablename__ = "conversation_slots"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    slot_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot_value_text: Mapped[str | None] = mapped_column(Text)
    slot_value_number: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SlotAskAttemptRow(AgentBase):
    """Số lần agent đã hỏi một slot trong một phiên.

    Đếm phải bền vững qua các lượt: mỗi `POST /agent/turn` là một process state
    mới, giữ `retry_count` trong bộ nhớ thì lượt sau luôn thấy 0 và agent lặp câu
    hỏi vô hạn — đúng thứ cơ chế MAX_RETRY sinh ra để chặn.
    """

    __tablename__ = "slot_ask_attempts"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    slot_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ask_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationMessageRow(AgentBase):
    """Append-only customer-visible transcript item."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('USER', 'ASSISTANT', 'ADVISOR', 'SYSTEM')",
            name="ck_conversation_messages_role",
        ),
        UniqueConstraint("session_id", "turn_index", name="uq_conversation_messages_session_turn"),
        Index("ix_conversation_messages_session_turn", "session_id", "turn_index"),
        Index(
            "uq_conversation_messages_client_turn_role",
            "session_id",
            "client_turn_id",
            "role",
            unique=True,
            postgresql_where=text("client_turn_id IS NOT NULL"),
        ),
    )

    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    client_turn_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    review_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    turn_index: Mapped[int] = mapped_column(BIGINT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationSummaryRow(AgentBase):
    """Latest incremental summary for one conversation session."""

    __tablename__ = "conversation_summaries"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text)
    summarized_through_turn: Mapped[int] = mapped_column(BIGINT)
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationTurnOutcomeRow(AgentBase):
    """Immutable replay payload and claim state for one client turn."""

    __tablename__ = "conversation_turn_outcomes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'WAITING_REVIEW', 'REJECTED', 'EXPIRED')",
            name="ck_conversation_turn_outcomes_status",
        ),
        UniqueConstraint(
            "session_id",
            "client_turn_id",
            name="uq_conversation_turn_outcomes_client_turn",
        ),
        UniqueConstraint(
            "session_id",
            "turn_number",
            name="uq_conversation_turn_outcomes_turn_number",
        ),
        Index(
            "ix_conversation_turn_outcomes_session_status",
            "session_id",
            "status",
        ),
    )

    outcome_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    client_turn_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    turn_number: Mapped[int] = mapped_column(BIGINT)
    status: Mapped[str] = mapped_column(String(24))
    answer: Mapped[str | None] = mapped_column(Text)
    pending_question: Mapped[str | None] = mapped_column(Text)
    terminal_reason: Mapped[str | None] = mapped_column(String(64))
    lookup_facts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    recommendations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    error_category: Mapped[str | None] = mapped_column(String(64))
    review_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    message_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # PR1: lease fields — token xác thực + mốc hết hạn của worker đang chạy lượt.
    # NULL trên hàng cũ = terminal-safe, không tạo token giả.
    claim_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # PR1: canonical replay payload (versioned JSONB, cap 256 KiB).
    result_payload: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationTurnBottleneckRow(AgentBase):
    """Mutable advisor task for one detected customer-turn bottleneck."""

    __tablename__ = "conversation_turn_bottlenecks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "client_turn_id"],
            [
                "conversation_turn_outcomes.session_id",
                "conversation_turn_outcomes.client_turn_id",
            ],
            name="fk_turn_bottlenecks_current_outcome",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "anchor_client_turn_id"],
            [
                "conversation_turn_outcomes.session_id",
                "conversation_turn_outcomes.client_turn_id",
            ],
            name="fk_turn_bottlenecks_anchor_outcome",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "label IN ('PRICE', 'CHARGING', 'BATTERY', 'RANGE')",
            name="ck_conversation_turn_bottlenecks_label",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CORRECT', 'INCORRECT')",
            name="ck_conversation_turn_bottlenecks_status",
        ),
        CheckConstraint(
            "(claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL) OR "
            "(claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_conversation_turn_bottlenecks_claim_triple",
        ),
        UniqueConstraint(
            "session_id",
            "client_turn_id",
            name="uq_conversation_turn_bottlenecks_current_turn",
        ),
        Index(
            "ix_conversation_turn_bottlenecks_status_lease_created",
            "status",
            "lease_expires_at",
            "created_at",
        ),
        Index(
            "ix_conversation_turn_bottlenecks_session_status_created",
            "session_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_conversation_turn_bottlenecks_anchor",
            "anchor_client_turn_id",
        ),
    )

    signal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    client_turn_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    anchor_client_turn_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    label: Mapped[str] = mapped_column(String(16))
    evidence_quote: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PENDING'"))
    claimed_by: Mapped[str | None] = mapped_column(String(64))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advisor_id: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PendingFeatureMentionRow(AgentBase):
    """Mutable unresolved feature mention from a conversation."""

    __tablename__ = "pending_feature_mentions"
    __table_args__ = (Index("ix_pending_feature_mentions_session", "session_id", "applied_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    raw_mention: Mapped[str] = mapped_column(Text)
    feature_code: Mapped[str | None] = mapped_column(String(100))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerProfileRow(AgentBase):
    """Mutable display contact profile for an Agent customer."""

    __tablename__ = "customer_profiles"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutOfScopeLogRow(AgentBase):
    """Mutable classification audit row for a customer utterance."""

    __tablename__ = "out_of_scope_log"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('IN_SCOPE', 'SOCIAL', 'MISSING_DATA', 'OUT_OF_SCOPE')",
            name="ck_out_of_scope_log_classification",
        ),
        Index("ix_out_of_scope_log_classification", "classification", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    utterance: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteAuditLogRow(AgentBase):
    """Append-only audit row for one quote-risk gate decision (A7-4).

    Không FK tới `agent_runs`: dòng audit được ghi bất đồng bộ và phải tồn tại
    kể cả cho lượt chưa từng mở run (tra giá niêm yết thuần).
    """

    __tablename__ = "quote_audit_log"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('NON_QUOTE', 'DETERMINISTIC_AUTO', 'EVIDENCE_BACKED_AUTO', 'SYNC_HITL', 'ADVISOR_HANDOFF')",
            name="ck_quote_audit_log_tier",
        ),
        Index("ix_quote_audit_log_tier", "tier", text("created_at DESC")),
        Index("ix_quote_audit_log_sampled", "sampled_for_review", text("created_at DESC")),
        Index("ix_quote_audit_log_near_threshold", "near_threshold", text("created_at DESC")),
    )

    audit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    tier: Mapped[str] = mapped_column(String(24))
    requires_hitl: Mapped[bool] = mapped_column(Boolean)
    legacy_requires_hitl: Mapped[bool] = mapped_column(Boolean)
    shadow_mode: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    sampled_for_review: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    near_threshold: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    user_message: Mapped[str] = mapped_column(Text)
    output_content: Mapped[str] = mapped_column(Text)
    evaluation: Mapped[dict] = mapped_column(JSONB)
    reasons: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentRunRow(AgentBase):
    """Mutable persisted execution run for one conversation."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('CAPTURING', 'SNAPSHOT_READY', 'PACKAGE_READY', 'PENDING_REVIEW', 'APPROVED', 'DELIVERED', 'FAILED', 'REJECTED')",
            name="ck_agent_runs_state",
        ),
        Index("ix_agent_runs_session", "session_id", text("created_at DESC")),
        Index("ix_agent_runs_state", "state"),
    )

    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(24), server_default=text("'CAPTURING'"))
    terminal_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunSnapshotRow(AgentBase):
    """Mutable frozen catalog payload used by one run."""

    __tablename__ = "run_snapshots"
    __table_args__ = (Index("ix_run_snapshots_run", "run_id"),)

    snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunCandidateRow(AgentBase):
    """Mutable vehicle candidate evaluated by one run."""

    __tablename__ = "run_candidates"
    __table_args__ = (
        CheckConstraint("layer_reached IN ('L1', 'L2', 'L3')", name="ck_run_candidates_layer"),
        CheckConstraint("rank IS NULL OR rank BETWEEN 1 AND 20", name="ck_run_candidates_rank"),
        Index("ix_run_candidates_run", "run_id", "rank"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    vehicle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    layer_reached: Mapped[str] = mapped_column(String(16))
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    over_budget_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunEvidenceRow(AgentBase):
    """Mutable allowlisted fact persisted as run evidence."""

    __tablename__ = "run_evidence"
    __table_args__ = (Index("ix_run_evidence_run", "run_id", "fact_code"),)

    evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    fact_code: Mapped[str] = mapped_column(String(60))
    source_table: Mapped[str] = mapped_column(String(60))
    source_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    value_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScoringResultRow(AgentBase):
    """Mutable score and typed reason payload for one vehicle candidate."""

    __tablename__ = "scoring_result"
    __table_args__ = (
        CheckConstraint("jsonb_array_length(reasons) >= 2", name="ck_scoring_result_reasons_min"),
        Index("ix_scoring_result_run", "run_id", text("score DESC")),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    vehicle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    reasons: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TcoEstimateRow(AgentBase):
    """Mutable deterministic total-cost estimate for a run candidate."""

    __tablename__ = "tco_estimates"
    __table_args__ = (
        CheckConstraint(
            "total_vnd = promoted_purchase_price_vnd + rolling_fees_vnd + energy_vnd + battery_vnd + scheduled_maintenance_vnd",
            name="ck_tco_estimates_total",
        ),
        Index("ix_tco_estimates_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    vehicle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    assumption_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    monthly_distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    promoted_purchase_price_vnd: Mapped[int] = mapped_column(BIGINT)
    rolling_fees_vnd: Mapped[int] = mapped_column(BIGINT)
    energy_vnd: Mapped[int] = mapped_column(BIGINT)
    battery_vnd: Mapped[int] = mapped_column(BIGINT)
    scheduled_maintenance_vnd: Mapped[int] = mapped_column(BIGINT)
    total_vnd: Mapped[int] = mapped_column(BIGINT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewQueueRow(AgentBase):
    """Mutable human-review task with lease and optimistic-version state."""

    __tablename__ = "review_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'EDITED', 'REJECTED', 'EXPIRED')",
            name="ck_review_queue_status",
        ),
        CheckConstraint(
            "(claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL) OR (claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_review_queue_claim_pair",
        ),
        Index("ix_review_queue_status_lease", "status", "lease_expires_at"),
        Index("ix_review_queue_session", "session_id", text("created_at DESC")),
        Index(
            "ix_review_queue_offer_state",
            text("(profile_snapshot->>'offer_state')"),
            postgresql_using="btree",
        ),
    )

    review_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    #: [T7b] Số lần đẩy vượt trần đã gộp vào mục này. Tư vấn viên đọc "spam ×N"
    #: thay vì thấy N mục rời — quyết định vẫn ra trên `content` của mục này.
    merged_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: Run của những lượt bị gộp, để còn lần được về nguồn khi tune ngưỡng.
    merged_run_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PENDING'"))
    claimed_by: Mapped[str | None] = mapped_column(String(64))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advisor_id: Mapped[str | None] = mapped_column(String(64))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_content: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    profile_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    handoff_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offer_suggestion_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class TestDriveBookingRow(AgentBase):
    """Mutable requested, confirmed, or cancelled test-drive booking."""

    __tablename__ = "test_drive_bookings"
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED', 'CONFIRMED', 'CANCELLED')", name="ck_test_drive_bookings_status"),
        # UNIQUE, không phải index thường: `SLOT_CAPACITY = 1` phải được CHÍNH
        # CSDL giữ. `book` đếm rồi ghi trong một transaction, nhưng READ
        # COMMITTED để hai transaction song song cùng đếm ra 0 rồi cùng ghi —
        # đúng khoảng hai khách bấm cùng một nút. Xem `agent_0031`.
        #
        # Điều kiện `status <> 'CANCELLED'` giữ nguyên: lịch đã huỷ không được
        # giữ chỗ, nếu không thì huỷ xong khung đó chết vĩnh viễn.
        # KHÔNG unique từ agent_0034 (Sếp 2026-08-31: bao nhiêu khách đặt một
        # khung cũng nhận — showroom nhiều xe, nhiều tư vấn viên).
        Index(
            "ix_test_drive_bookings_showroom_time",
            "showroom",
            "scheduled_at",
            postgresql_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_test_drive_bookings_customer", "customer_id", text("scheduled_at DESC")),
    )

    booking_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64))
    vehicle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    advisor_id: Mapped[str | None] = mapped_column(String(64))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="SET NULL"))
    showroom: Mapped[str] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'REQUESTED'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InternalNoticeRow(AgentBase):
    """Mutable internal notice published by an Agent staff member."""

    __tablename__ = "internal_notices"
    __table_args__ = (
        CheckConstraint("priority IN ('NORMAL', 'URGENT')", name="ck_internal_notices_priority"),
        Index("ix_internal_notices_created", text("created_at DESC")),
    )

    notice_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), server_default=text("'NORMAL'"))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NoticeReadRow(AgentBase):
    """Mutable acknowledgement keyed by notice and advisor."""

    __tablename__ = "notice_reads"

    notice_id: Mapped[UUID] = mapped_column(
        ForeignKey("internal_notices.notice_id", ondelete="CASCADE"), primary_key=True
    )
    advisor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerAdvisorAssignmentRow(AgentBase):
    """Customer-level assignment assigning an advisor to manage a customer with audit history."""

    __tablename__ = "customer_advisor_assignments"
    __table_args__ = (
        Index("ix_customer_advisor_assignments_customer", "customer_id", "status"),
        Index("ix_customer_advisor_assignments_advisor", "advisor_id", "status"),
    )

    assignment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    advisor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), server_default=text("'ACTIVE'"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationReassignmentRow(AgentBase):
    """Audit record when Admin reassigns a live chat session to another advisor."""

    __tablename__ = "conversation_reassignments"
    __table_args__ = (Index("ix_conversation_reassignments_session", "session_id"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    previous_advisor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_advisor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reassigned_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionOfferRow(AgentBase):
    """Advisor-approved session-scoped offer surviving across turns (T4)."""

    __tablename__ = "session_offers"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'EXPIRED')", name="ck_session_offers_status"),
        CheckConstraint(
            "source_kind IN ('CONTENT_REVIEW', 'BOTTLENECK_SIGNAL', 'OPPORTUNITY_OFFER')",
            name="ck_session_offers_source_kind",
        ),
        Index("ix_session_offers_session_status", "session_id", "status"),
        Index("ix_session_offers_expires", "expires_at"),
    )

    offer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_signal_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_review_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    promotion_code: Mapped[str] = mapped_column(String(64), nullable=False)
    value_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    approved_by: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: agent_0039: ưu đãi gửi từ vòng đời cơ hội (Customer 360) — truy ngược `opportunity_offers`.
    opportunity_offer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class AgentRateLimitCounterRow(AgentBase):
    """[T7a] Bộ đếm lượt theo cửa sổ cố định, riêng cho module agents.

    Cùng hình dạng với `auth_rate_limit_counters` nhưng là BẢNG RIÊNG: hai module
    có chuỗi migration riêng, và dùng chung một bảng sẽ buộc chúng phải đổi cùng
    nhịp. Khoá chính ghép `(key, window_start)` cho phép đếm bằng đúng một câu
    `INSERT ... ON CONFLICT DO UPDATE`.
    """

    __tablename__ = "agent_rate_limit_counters"
    __table_args__ = (Index("ix_agent_rate_limit_expires", "expires_at"),)

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: Mốc dọn rác — hàng quá hạn không còn ý nghĩa và được xoá theo lô.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TurnTraceRow(AgentBase):
    """Vệt quyết định của MỘT lượt — vì sao máy đáp như vậy (Sếp 2026-08-26).

    Vài cột VÔ HƯỚNG cho những gì phải đếm/lọc bằng SQL, cộng `payload` JSONB giữ
    trọn phần còn lại: thêm trường quan sát mới về sau không cần migration.

    KHÔNG phải bản sao thứ hai của hội thoại — nội dung đầy đủ vẫn ở
    `conversation_messages`; bảng này chỉ giữ LÝ DO.
    """

    __tablename__ = "turn_traces"
    __table_args__ = (
        Index("ix_turn_traces_created", "created_at"),
        Index("ix_turn_traces_session", "session_id"),
        Index("ix_turn_traces_tier", "tier"),
    )

    trace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    client_turn_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    intent_hint: Mapped[str | None] = mapped_column(String(48), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    routing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ConversationCoreStateRow(AgentBase):
    """Trạng thái lõi hội thoại v2 — một hàng/phiên (spec 2026-08-29 mục 4).

    Chỉ `core/run_turn.py` ghi, một lần cuối lượt, cùng transaction với outcome.
    Không khoá ngoại tới `conversation_sessions`: phiên xoá thì hàng này xoá theo
    bằng logic `delete_conversation`, không để FK kéo theo lúc điều tra.
    """

    __tablename__ = "conversation_core_state"

    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    intent: Mapped[str] = mapped_column(String(24), nullable=False)
    slots: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    pending: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    chosen_vehicle_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    recommended_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ask_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Lịch lái thử đã đặt trong phiên (agent_0033). Không FK tới
    #: `test_drive_bookings`: chỉ là dấu "đã có lịch" cho câu kết/panel.
    booking_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentFeatureFlagRow(AgentBase):
    """Cờ động cho đường agent (agent_0036, plan agent-migration Bước 3).

    Đọc qua `adapters/agent_flag_repository.SqlAlchemyAgentFlagAdapter` với TTL
    cache 60s; bật/tắt bằng `UPDATE` thẳng, không cần restart. Không FK tới
    bảng nào — đây là cấu hình vận hành, không phải dữ liệu phiên.
    """

    __tablename__ = "agent_feature_flags"
    __table_args__ = (
        CheckConstraint("rollout_percent BETWEEN 0 AND 100", name="ck_agent_feature_flags_rollout_percent"),
    )

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    rollout_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    #: `customer_id` ngăn bằng dấu phẩy — `domain/agent_flag.parse_allowlist` là chỗ DUY NHẤT tách.
    customer_allowlist: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CustomerOpportunityRow(AgentBase):
    """Một nhu cầu mua của một khách — tầng Cơ hội (agent_0037, plan Customer 360 §2.1).

    Giai đoạn và độ nóng tính SẴN ở job nền (`services/operations/customer_360.py`);
    đường đọc không tính lại.
    """

    __tablename__ = "customer_opportunities"
    __table_args__ = (
        CheckConstraint(
            "vehicle_type IS NULL OR vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')",
            name="ck_customer_opportunities_vehicle_type",
        ),
        CheckConstraint(
            "buyer_for IN ('SELF', 'FAMILY', 'COMPANY', 'OTHER')", name="ck_customer_opportunities_buyer_for"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'DORMANT', 'WON', 'LOST', 'REPLACED')", name="ck_customer_opportunities_status"
        ),
        CheckConstraint(
            "stage IN ('DISCOVER', 'COMPARE', 'QUOTE', 'TEST_DRIVE', 'CLOSE')", name="ck_customer_opportunities_stage"
        ),
        CheckConstraint("heat_score BETWEEN 0 AND 100", name="ck_customer_opportunities_heat_score"),
        CheckConstraint("heat_band IN ('HOT', 'WARM', 'COLD')", name="ck_customer_opportunities_heat_band"),
        CheckConstraint(
            "(status = 'REPLACED') = (replaced_by IS NOT NULL)", name="ck_customer_opportunities_replaced_pair"
        ),
        Index("ix_customer_opportunities_customer_status", "customer_id", "status"),
        Index("ix_customer_opportunities_heat", "status", text("heat_score DESC")),
        Index("ix_customer_opportunities_last_seen", "last_seen_at"),
    )

    opportunity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    buyer_for: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'SELF'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'OPEN'"))
    replaced_by: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "customer_opportunities.opportunity_id",
            ondelete="SET NULL",
            name="fk_customer_opportunities_replaced_by",
        ),
        nullable=True,
    )
    slots_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    slot_history: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    stage: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'DISCOVER'"))
    heat_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    heat_band: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'COLD'"))
    heat_breakdown: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    heat_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SessionOpportunityRow(AgentBase):
    """Phiên gắn vào cơ hội nào, ai quyết (agent_0037). `kind=SUPPORT` = phiên chỉ hỗ trợ."""

    __tablename__ = "session_opportunity"
    __table_args__ = (
        CheckConstraint("kind IN ('SALES', 'SUPPORT')", name="ck_session_opportunity_kind"),
        CheckConstraint("decided_by IN ('RULE', 'LLM', 'ADVISOR')", name="ck_session_opportunity_decided_by"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_session_opportunity_confidence"),
        CheckConstraint("kind = 'SALES' OR opportunity_id IS NULL", name="ck_session_opportunity_support_unattached"),
        Index("ix_session_opportunity_opportunity", "opportunity_id"),
        Index("ix_session_opportunity_review", "needs_review", postgresql_where=text("needs_review")),
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE", name="fk_session_opportunity_session"),
        primary_key=True,
    )
    opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "customer_opportunities.opportunity_id",
            ondelete="SET NULL",
            name="fk_session_opportunity_opportunity",
        ),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(8), nullable=False)
    decided_by_actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    evaluated_through_turn: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    extracted_through_turn: Mapped[int] = mapped_column(BIGINT, nullable=False, server_default=text("0"))
    extraction_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Customer360FeedbackRow(AgentBase):
    """TVV sửa máy: Tách/Gộp phiên, báo insight sai/đúng (agent_0037)."""

    __tablename__ = "customer360_feedback"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('INSIGHT_WRONG', 'INSIGHT_OK', 'SESSION_MOVED', 'SESSION_SPLIT')",
            name="ck_customer360_feedback_kind",
        ),
        Index("ix_customer360_feedback_kind_created", "kind", text("created_at DESC")),
    )

    feedback_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    insight_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    from_opportunity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    to_opportunity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    previous_decided_by: Mapped[str | None] = mapped_column(String(8), nullable=True)
    field: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomerInsightRow(AgentBase):
    """Một điều khách NÓI RA, kèm bằng chứng nguyên văn (agent_0038, plan §5.4)."""

    __tablename__ = "customer_insights"
    __table_args__ = (
        CheckConstraint(
            "field IN ('purchase_timeframe', 'payment_method', 'current_vehicle', 'trade_in', 'decision_maker', "
            "'competitor_brand', 'other_concern', 'buyer_for', 'customer_group', 'registration_province', "
            "'home_charging')",
            name="ck_customer_insights_field",
        ),
        CheckConstraint("source IN ('SLOT', 'LLM', 'ADVISOR')", name="ck_customer_insights_source"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_customer_insights_confidence"),
        CheckConstraint(
            "source <> 'LLM' OR (length(evidence_quote) > 0 AND turn_index IS NOT NULL)",
            name="ck_customer_insights_llm_evidence",
        ),
        UniqueConstraint("session_id", "turn_index", "field", "value", name="uq_customer_insights_turn_field_value"),
        Index(
            "ix_customer_insights_customer_current",
            "customer_id",
            "field",
            postgresql_where=text("superseded_by IS NULL"),
        ),
        Index("ix_customer_insights_opportunity", "opportunity_id"),
    )

    insight_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "customer_opportunities.opportunity_id",
            ondelete="SET NULL",
            name="fk_customer_insights_opportunity",
        ),
        nullable=True,
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE", name="fk_customer_insights_session"),
        nullable=True,
    )
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    value_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    turn_index: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1"))
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("customer_insights.insight_id", ondelete="SET NULL", name="fk_customer_insights_superseded_by"),
        nullable=True,
    )
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityOfferRow(AgentBase):
    """Ưu đãi gắn MỘT cơ hội, có vòng đời (agent_0039, plan Customer 360 Phase 5B)."""

    __tablename__ = "opportunity_offers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUGGESTED', 'APPROVED', 'SENT', 'ENGAGED', 'CONVERTED', 'EXPIRED', 'DISMISSED')",
            name="ck_opportunity_offers_status",
        ),
        CheckConstraint("eligibility IN ('ELIGIBLE', 'NEED_INFO')", name="ck_opportunity_offers_eligibility"),
        CheckConstraint("discount_vnd IS NULL OR discount_vnd >= 0", name="ck_opportunity_offers_discount"),
        CheckConstraint(
            "(status IN ('SUGGESTED', 'DISMISSED')) OR approved_by IS NOT NULL",
            name="ck_opportunity_offers_approved_before_send",
        ),
        Index(
            "uq_opportunity_offers_live",
            "opportunity_id",
            "promotion_code",
            unique=True,
            postgresql_where=text("status NOT IN ('EXPIRED', 'DISMISSED')"),
        ),
        Index("ix_opportunity_offers_customer", "customer_id", "status"),
    )

    offer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "customer_opportunities.opportunity_id", ondelete="CASCADE", name="fk_opportunity_offers_opportunity"
        ),
        nullable=False,
    )
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    promotion_code: Mapped[str] = mapped_column(String(100), nullable=False)
    eligibility: Mapped[str] = mapped_column(String(12), nullable=False)
    eligibility_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    proposed_value: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    discount_vnd: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    needs_manager_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    suggested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_offer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityOfferEventRow(AgentBase):
    """Một lần đổi trạng thái ưu đãi — nguồn đo hiệu quả (agent_0039)."""

    __tablename__ = "opportunity_offer_events"
    __table_args__ = (
        Index("ix_opportunity_offer_events_status", "to_status", "created_at"),
        Index("ix_opportunity_offer_events_promotion", "promotion_code", "to_status"),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    offer_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunity_offers.offer_id", ondelete="CASCADE", name="fk_opportunity_offer_events_offer"),
        nullable=False,
    )
    promotion_code: Mapped[str] = mapped_column(String(100), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_status: Mapped[str] = mapped_column(String(12), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
