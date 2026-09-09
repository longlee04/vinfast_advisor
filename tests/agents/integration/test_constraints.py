"""Database constraint and funnel-metric integration tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agents.models import (
    AgentRunRow,
    ConversationSessionRow,
    ConversationSlotRow,
    InternalNoticeRow,
    NoticeReadRow,
    ReviewQueueRow,
    RunCandidateRow,
    ScoringResultRow,
    TcoEstimateRow,
)
from src.agents.models import (
    TestDriveBookingRow as BookingRow,
)

NOW = datetime(2026, 8, 4, tzinfo=UTC)


def _normalize_sql(statement: str | None) -> str | None:
    """Normalize PostgreSQL's rendered predicate for stable assertions."""
    if statement is None:
        return None
    return " ".join(statement.lower().replace("::text", "").replace("(", "").replace(")", "").split())


async def _create_session(engine: AsyncEngine) -> UUID:
    session_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return session_id


async def _create_run(engine: AsyncEngine, session_id: UUID) -> UUID:
    run_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return run_id


class TestAgentConstraints:
    @pytest.mark.asyncio
    async def test_slot_primary_key_rejects_duplicate(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)
        values = {
            "session_id": session_id,
            "slot_name": "vehicle_type",
            "slot_value_text": "CAR",
            "confirmed_at": NOW,
            "updated_at": NOW,
        }
        async with migrated_engine.begin() as connection:
            await connection.execute(insert(ConversationSlotRow).values(**values))

        # When / Then
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(insert(ConversationSlotRow).values(**values))

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("statement", "constraint_name"),
        [
            (
                "INSERT INTO conversation_sessions (session_id, customer_id, status, started_at, last_activity_at, created_at, updated_at) "
                "VALUES (:id, 'customer-1', 'BROKEN', now(), now(), now(), now())",
                "ck_conversation_sessions_status",
            ),
            (
                "INSERT INTO conversation_sessions (session_id, customer_id, vehicle_type_hint, started_at, last_activity_at, created_at, updated_at) "
                "VALUES (:id, 'customer-1', 'BIKE', now(), now(), now(), now())",
                "ck_conversation_sessions_vehicle_type",
            ),
            (
                "INSERT INTO out_of_scope_log (id, session_id, utterance, classification, created_at) "
                "VALUES (:id, :session_id, 'hello', 'UNKNOWN', now())",
                "ck_out_of_scope_log_classification",
            ),
        ],
    )
    async def test_conversation_checks_reject_invalid_values(
        self,
        migrated_engine: AsyncEngine,
        clean_agent_database: None,
        statement: str,
        constraint_name: str,
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)

        # When / Then
        with pytest.raises(IntegrityError, match=constraint_name):
            async with migrated_engine.begin() as connection:
                await connection.execute(text(statement), {"id": uuid4(), "session_id": session_id})

    @pytest.mark.asyncio
    async def test_agent_run_state_check_rejects_value_outside_enum(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)

        # When / Then
        with pytest.raises(IntegrityError, match="ck_agent_runs_state"):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    insert(AgentRunRow).values(
                        run_id=uuid4(),
                        session_id=session_id,
                        state="UNKNOWN",
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )

    @pytest.mark.asyncio
    async def test_run_scoring_and_tco_checks_reject_invalid_values(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)
        run_id = await _create_run(migrated_engine, session_id)

        # When / Then
        invalid_rows = (
            (
                insert(RunCandidateRow).values(
                    id=uuid4(), run_id=run_id, vehicle_id=uuid4(), layer_reached="L4", created_at=NOW
                ),
                "ck_run_candidates_layer",
            ),
            (
                insert(RunCandidateRow).values(
                    id=uuid4(), run_id=run_id, vehicle_id=uuid4(), layer_reached="L1", rank=21, created_at=NOW
                ),
                "ck_run_candidates_rank",
            ),
            (
                insert(ScoringResultRow).values(
                    id=uuid4(),
                    run_id=run_id,
                    vehicle_id=uuid4(),
                    score=Decimal("1"),
                    reasons=[{"reason_text": "only one"}],
                    created_at=NOW,
                ),
                "ck_scoring_result_reasons_min",
            ),
            (
                insert(TcoEstimateRow).values(
                    id=uuid4(),
                    run_id=run_id,
                    vehicle_id=uuid4(),
                    assumption_id=uuid4(),
                    monthly_distance_km=Decimal("10"),
                    promoted_purchase_price_vnd=1,
                    rolling_fees_vnd=2,
                    energy_vnd=3,
                    battery_vnd=4,
                    scheduled_maintenance_vnd=5,
                    total_vnd=0,
                    created_at=NOW,
                ),
                "ck_tco_estimates_total",
            ),
        )
        for statement, constraint_name in invalid_rows:
            with pytest.raises(IntegrityError, match=constraint_name):
                async with migrated_engine.begin() as connection:
                    await connection.execute(statement)

    @pytest.mark.asyncio
    async def test_review_booking_and_notice_constraints(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)
        run_id = await _create_run(migrated_engine, session_id)
        notice_id = uuid4()
        async with migrated_engine.begin() as connection:
            result = await connection.execute(
                insert(ReviewQueueRow)
                .values(
                    review_id=uuid4(),
                    session_id=session_id,
                    run_id=run_id,
                    content="review",
                    created_at=NOW,
                    updated_at=NOW,
                )
                .returning(ReviewQueueRow.version)
            )
            version = result.scalar_one()
            await connection.execute(
                insert(InternalNoticeRow).values(
                    notice_id=notice_id, title="notice", content="content", created_by="admin", created_at=NOW
                )
            )
            await connection.execute(
                insert(NoticeReadRow).values(notice_id=notice_id, advisor_id="advisor-1", read_at=NOW)
            )
            await connection.execute(
                insert(NoticeReadRow).values(notice_id=notice_id, advisor_id="advisor-2", read_at=NOW)
            )

        # When / Then
        assert version == 1
        with pytest.raises(IntegrityError, match="ck_review_queue_claim_pair"):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    insert(ReviewQueueRow).values(
                        review_id=uuid4(),
                        session_id=session_id,
                        run_id=run_id,
                        content="invalid",
                        claimed_by="advisor",
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    insert(NoticeReadRow).values(notice_id=notice_id, advisor_id="advisor-1", read_at=NOW)
                )
        with pytest.raises(IntegrityError, match="ck_test_drive_bookings_status"):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    insert(BookingRow).values(
                        booking_id=uuid4(),
                        customer_id="customer-1",
                        vehicle_id=uuid4(),
                        showroom="showroom",
                        scheduled_at=NOW,
                        status="UNKNOWN",
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
        with pytest.raises(IntegrityError, match="ck_internal_notices_priority"):
            async with migrated_engine.begin() as connection:
                await connection.execute(
                    insert(InternalNoticeRow).values(
                        notice_id=uuid4(),
                        title="notice",
                        content="content",
                        priority="LOW",
                        created_by="admin",
                        created_at=NOW,
                    )
                )

    @pytest.mark.asyncio
    async def test_session_delete_cascades_children_and_nulls_booking_run(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)
        run_id = await _create_run(migrated_engine, session_id)
        booking_id = uuid4()
        async with migrated_engine.begin() as connection:
            await connection.execute(
                insert(ConversationSlotRow).values(
                    session_id=session_id,
                    slot_name="vehicle_type",
                    slot_value_text="CAR",
                    confirmed_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(BookingRow).values(
                    booking_id=booking_id,
                    customer_id="customer-1",
                    vehicle_id=uuid4(),
                    run_id=run_id,
                    showroom="showroom",
                    scheduled_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        # When
        async with migrated_engine.begin() as connection:
            await connection.execute(
                delete(ConversationSessionRow).where(ConversationSessionRow.session_id == session_id)
            )

        # Then
        async with migrated_engine.connect() as connection:
            slot_count = await connection.scalar(select(text("count(*)")).select_from(ConversationSlotRow))
            booking_run_id = await connection.scalar(
                select(BookingRow.run_id).where(BookingRow.booking_id == booking_id)
            )
        assert slot_count == 0
        assert booking_run_id is None

    @pytest.mark.asyncio
    async def test_booking_partial_index_excludes_cancelled_rows(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        async with migrated_engine.begin() as connection:
            await connection.execute(
                insert(BookingRow).values(
                    booking_id=uuid4(),
                    customer_id="customer-1",
                    vehicle_id=uuid4(),
                    showroom="showroom",
                    scheduled_at=NOW,
                    status="CANCELLED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        # When
        async with migrated_engine.connect() as connection:
            predicate = await connection.scalar(
                text(
                    "SELECT pg_get_expr(indpred, indrelid) FROM pg_index "
                    "WHERE indexrelid = 'ix_test_drive_bookings_showroom_time'::regclass"
                )
            )

        # Then
        assert _normalize_sql(predicate) == "status <> 'cancelled'"

    @pytest.mark.asyncio
    async def test_funnel_metrics_counts_source_rows(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        session_id = await _create_session(migrated_engine)
        run_id = await _create_run(migrated_engine, session_id)
        async with migrated_engine.begin() as connection:
            await connection.execute(
                insert(ConversationSlotRow).values(
                    session_id=session_id,
                    slot_name="vehicle_type",
                    slot_value_text="CAR",
                    confirmed_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(AgentRunRow).values(
                    run_id=uuid4(), session_id=session_id, state="APPROVED", created_at=NOW, updated_at=NOW
                )
            )
            await connection.execute(
                insert(ReviewQueueRow).values(
                    review_id=uuid4(),
                    session_id=session_id,
                    run_id=run_id,
                    content="review",
                    status="APPROVED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(BookingRow).values(
                    booking_id=uuid4(),
                    customer_id="customer-1",
                    vehicle_id=uuid4(),
                    showroom="showroom",
                    scheduled_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        # When
        async with migrated_engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        text("sessions_started"),
                        text("sessions_with_profile"),
                        text("sessions_with_recommendation"),
                        text("sessions_approved"),
                        text("sessions_booked"),
                    ).select_from(text("funnel_metrics"))
                )
            ).one()

        # Then
        assert tuple(row) == (1, 1, 1, 1, 1)

    @pytest.mark.asyncio
    async def test_funnel_metrics_deduplicates_rows_and_excludes_cancelled_bookings(
        self, migrated_engine: AsyncEngine, clean_agent_database: None
    ) -> None:
        # Given
        first_session_id = await _create_session(migrated_engine)
        second_session_id = uuid4()
        first_run_id = await _create_run(migrated_engine, first_session_id)
        async with migrated_engine.begin() as connection:
            await connection.execute(
                insert(ConversationSessionRow).values(
                    session_id=second_session_id,
                    customer_id="customer-2",
                    started_at=NOW,
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(ConversationSlotRow).values(
                    session_id=first_session_id,
                    slot_name="vehicle_type",
                    slot_value_text="CAR",
                    confirmed_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(AgentRunRow).values(
                    run_id=uuid4(),
                    session_id=first_session_id,
                    state="DELIVERED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(ReviewQueueRow).values(
                    review_id=uuid4(),
                    session_id=first_session_id,
                    run_id=first_run_id,
                    content="first approval",
                    status="APPROVED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await connection.execute(
                insert(ReviewQueueRow).values(
                    review_id=uuid4(),
                    session_id=first_session_id,
                    run_id=first_run_id,
                    content="duplicate approval",
                    status="APPROVED",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            for customer_id, status in (
                ("customer-1", "REQUESTED"),
                ("customer-1", "CANCELLED"),
                ("customer-2", "CANCELLED"),
            ):
                await connection.execute(
                    insert(BookingRow).values(
                        booking_id=uuid4(),
                        customer_id=customer_id,
                        vehicle_id=uuid4(),
                        showroom="showroom",
                        scheduled_at=NOW,
                        status=status,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )

        # When
        async with migrated_engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        text("sessions_started"),
                        text("sessions_with_profile"),
                        text("sessions_with_recommendation"),
                        text("sessions_approved"),
                        text("sessions_booked"),
                    ).select_from(text("funnel_metrics"))
                )
            ).one()

        # Then
        assert tuple(row) == (2, 1, 1, 1, 1)
