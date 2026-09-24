"""Phase 3 Customer 360: danh sách phiên cho nhân sự nạp phần làm giàu theo LÔ.

Trước đây `_enrich_summary` chạy 2 câu SQL cho MỖI phiên (tin cuối + trạng thái lõi),
và `customer_display` không bao giờ được gán nên màn TVV chỉ thấy UUID.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.agents.adapters.assignment_repository import SqlAlchemyCustomerAssignmentRepository
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.models import (
    ConversationCoreStateRow,
    ConversationMessageRow,
    ConversationSessionRow,
    CustomerAdvisorAssignmentRow,
    CustomerProfileRow,
)

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _session_row(customer_id: str) -> ConversationSessionRow:
    return ConversationSessionRow(
        session_id=uuid4(),
        customer_id=customer_id,
        status="ACTIVE",
        started_at=NOW,
        last_activity_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


async def _seed(session: AsyncSession, count: int, prefix: str = "cust") -> list[ConversationSessionRow]:
    rows = [_session_row(f"{prefix}-{index}") for index in range(count)]
    session.add_all(rows)
    session.add(CustomerProfileRow(customer_id=f"{prefix}-0", display_name="Nguyễn An", created_at=NOW, updated_at=NOW))
    await session.flush()
    for index, row in enumerate(rows):
        session.add_all(
            [
                ConversationMessageRow(
                    message_id=uuid4(),
                    session_id=row.session_id,
                    role="USER",
                    content=f"câu đầu {index}",
                    turn_index=1,
                    created_at=NOW,
                ),
                ConversationMessageRow(
                    message_id=uuid4(),
                    session_id=row.session_id,
                    role="ASSISTANT",
                    content=f"câu cuối {index}",
                    turn_index=2,
                    created_at=NOW + timedelta(seconds=1),
                ),
            ]
        )
        session.add(
            ConversationCoreStateRow(
                session_id=row.session_id,
                stage="COLLECTING",
                intent="ADVISORY",
                slots={"vehicle_type": "CAR", "budget_max_vnd": 700_000_000, "khoa_la": "bo qua"},
                recommended_ids=[],
                ask_counts={},
                turn_count=1,
            )
        )
    await session.flush()
    return rows


@pytest.mark.asyncio
async def test_lam_giau_theo_lo_dung_gia_tri(agent_session: AsyncSession) -> None:
    rows = await _seed(agent_session, 3)
    repository = SqlAlchemySessionRepository(agent_session, FixedClock())

    extras = await repository.load_staff_extras(rows)

    first = extras[rows[0].session_id]
    assert first.last_message == "câu cuối 0"
    assert first.slots == {"vehicle_type": "CAR", "budget_max_vnd": 700_000_000}
    assert first.customer_display == "Nguyễn An"
    assert extras[rows[1].session_id].customer_display is None


@pytest.mark.asyncio
async def test_so_cau_sql_khong_tang_theo_so_phien(migrated_engine: AsyncEngine, agent_session: AsyncSession) -> None:
    few = await _seed(agent_session, 2)
    many = few + await _seed(agent_session, 10, prefix="more")
    repository = SqlAlchemySessionRepository(agent_session, FixedClock())
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        statements.append(statement)

    event.listen(migrated_engine.sync_engine, "before_cursor_execute", count)
    try:
        await repository.load_staff_extras(few)
        few_count = len(statements)
        statements.clear()
        await repository.load_staff_extras(many)
        many_count = len(statements)
    finally:
        event.remove(migrated_engine.sync_engine, "before_cursor_execute", count)

    # Phase 3: 3 câu; Phase 4 thêm câu độ nóng/rào cản — vẫn KHÔNG tăng theo số phiên.
    assert few_count == many_count == 4


@pytest.mark.asyncio
async def test_danh_sach_khach_duoc_giao_nap_theo_lo(migrated_engine: AsyncEngine, agent_session: AsyncSession) -> None:
    rows = await _seed(agent_session, 4)
    agent_session.add_all(
        [
            CustomerAdvisorAssignmentRow(
                assignment_id=uuid4(),
                customer_id=row.customer_id,
                advisor_id="adv-1",
                assigned_by="admin-1",
                status="ACTIVE",
                assigned_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
            for row in rows
        ]
    )
    await agent_session.flush()
    repository = SqlAlchemyCustomerAssignmentRepository(agent_session, FixedClock())
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        statements.append(statement)

    event.listen(migrated_engine.sync_engine, "before_cursor_execute", count)
    try:
        customers = await repository.list_assigned_customers_for_advisor("adv-1")
    finally:
        event.remove(migrated_engine.sync_engine, "before_cursor_execute", count)

    assert len(customers) == 4
    assert len(statements) == 3
    named = next(item for item in customers if item.customer_id == "cust-0")
    assert named.profile_payload["name"] == "Nguyễn An"
    assert named.active_conversations_count == 1
