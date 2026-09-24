"""Customer 360 Phase 4 trên Postgres thật: gắn phiên → cơ hội, insight, độ nóng, hồ sơ ≤ 3 câu SQL.

LLM là bản giả: trích xuất trả cả một mục hợp lệ lẫn một mục suy diễn (phải bị loại).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.agents.adapters.customer_360_query import SqlAlchemyCustomer360Query
from src.agents.adapters.customer_opportunity_repository import SqlAlchemyCustomer360Repository
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.models import (
    ConversationCoreStateRow,
    ConversationMessageRow,
    ConversationSessionRow,
    Customer360FeedbackRow,
    CustomerAdvisorAssignmentRow,
    CustomerInsightRow,
    CustomerOpportunityRow,
    CustomerProfileRow,
    SessionOpportunityRow,
)
from src.agents.services.operations.customer_360 import Customer360Operations, ExtractionResult
from src.agents.services.operations.customer_360_read import (
    Customer360DisabledError,
    Customer360ReadOperations,
    CustomerAccessDeniedError,
)
from tests.agents.integration.conftest import run_alembic

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


class FakeFlags:
    def __init__(self, *on: str) -> None:
        self.on = set(on)

    async def load(self, name: str) -> AgentFlagState | None:
        return AgentFlagState(name=name, enabled=name in self.on, rollout_percent=100 if name in self.on else 0)


class FakeExtractor:
    def __init__(self) -> None:
        self.calls: list[dict[int, str]] = []

    async def extract(self, user_turns):  # noqa: ANN001, ANN201
        self.calls.append(dict(user_turns))
        return ExtractionResult(
            items=[
                {
                    "field": "purchase_timeframe",
                    "value": "trong tháng này",
                    "value_code": "WITHIN_1_MONTH",
                    "evidence_quote": "tháng này em chốt",
                    "turn_index": 5,
                    "confidence": 0.9,
                },
                {
                    "field": "payment_method",
                    "value": "trả góp",
                    "value_code": "INSTALLMENT",
                    "evidence_quote": "trả góp",
                    "turn_index": 5,
                    "confidence": 0.9,
                },
                # Suy diễn: không có câu nào nói "đã có gia đình" → phải bị loại.
                {
                    "field": "decision_maker",
                    "value": "vợ quyết",
                    "value_code": "SPOUSE",
                    "evidence_quote": "vợ em quyết",
                    "turn_index": 1,
                    "confidence": 0.9,
                },
            ],
            model_name="fake",
            prompt_version="insight-v1",
        )


async def _seed_session(
    session: AsyncSession,
    customer_id: str,
    slots: dict[str, object],
    messages: list[str],
    *,
    stage: str = "COLLECTING",
    ask_counts: dict[str, int] | None = None,
    at: datetime = NOW,
) -> UUID:
    session_id = uuid4()
    session.add(
        ConversationSessionRow(
            session_id=session_id,
            customer_id=customer_id,
            status="ACTIVE",
            started_at=at,
            last_activity_at=at,
            created_at=at,
            updated_at=at,
        )
    )
    await session.flush()
    for index, content in enumerate(messages, start=1):
        session.add(
            ConversationMessageRow(
                message_id=uuid4(),
                session_id=session_id,
                role="USER",
                content=content,
                turn_index=index * 2 - 1,
                created_at=at,
            )
        )
    session.add(
        ConversationCoreStateRow(
            session_id=session_id,
            stage=stage,
            intent="ADVISORY",
            slots=slots,
            recommended_ids=[],
            ask_counts=ask_counts or {},
            turn_count=len(messages),
        )
    )
    await session.commit()
    return session_id


def _operations(
    factory: async_sessionmaker[AsyncSession], extractor: FakeExtractor | None = None
) -> Customer360Operations:
    return Customer360Operations(
        SqlAlchemyCustomer360Repository(factory),
        clock=lambda: NOW,
        flags=FakeFlags("customer360_attach", "customer360_extractor"),
        extractor=extractor,
    )


@pytest.mark.asyncio
async def test_gan_phien_insight_va_do_nong_tren_db_that(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    extractor = FakeExtractor()
    operations = _operations(factory, extractor)
    async with factory() as session:
        first = await _seed_session(
            session,
            "cust-1",
            {
                "vehicle_type": "CAR",
                "purpose_bucket": "FAMILY",
                "budget_max_vnd": 700_000_000,
                "registration_province": "HN",
            },
            [
                "tư vấn ô tô điện cho gia đình",
                "ngân sách 700 triệu, số em 0912345678",
                "Chắc tháng này em chốt, trả góp",
            ],
            stage="COSTING",
            ask_counts={"passenger_count": 2},
        )

    result = await operations.refresh_session(str(first))
    assert result is not None and result.rule_code == "R1"
    assert result.rejected == {"NO_EVIDENCE": 1}

    async with factory() as session:
        opportunity = await session.get(CustomerOpportunityRow, UUID(result.opportunity_id))
        insights = (await session.scalars(select(CustomerInsightRow).order_by(CustomerInsightRow.field))).all()
    assert opportunity is not None and opportunity.vehicle_type == "CAR"
    # COSTING→QUOTE 25 + tháng này 20 + SĐT trong chat 10 + ngân sách 5 + hỏi trả góp 5 − né 1 câu 5 = 60 → Nóng.
    assert (opportunity.stage, opportunity.heat_score, opportunity.heat_band) == ("QUOTE", 60, "HOT")
    assert {(row.field, row.value_code, row.source) for row in insights} == {
        ("payment_method", "INSTALLMENT", "LLM"),
        ("purchase_timeframe", "WITHIN_1_MONTH", "LLM"),
        ("registration_province", "HN", "SLOT"),
    }
    # Chạy lại không trích lại lượt đã trích.
    await operations.refresh_session(str(first))
    assert len(extractor.calls) == 1

    # Phiên sau: cùng xe, chỉ đổi ngân sách → R5 cùng cơ hội, lưu vết.
    async with factory() as session:
        second = await _seed_session(
            session,
            "cust-1",
            {"vehicle_type": "CAR", "purpose_bucket": "FAMILY", "budget_max_vnd": 850_000_000},
            ["quay lại hỏi xe", "tăng ngân sách lên 850 triệu"],
            at=NOW + timedelta(hours=1),
        )
    again = await operations.refresh_session(str(second))
    assert again is not None and (again.rule_code, again.opportunity_id) == ("R5", result.opportunity_id)
    async with factory() as session:
        updated = await session.get(CustomerOpportunityRow, UUID(result.opportunity_id))
    assert updated.slots_snapshot["budget_max_vnd"] == 850_000_000
    assert updated.slot_history[-1]["previous"] == 700_000_000

    # Xe máy → cơ hội mới (R2).
    async with factory() as session:
        third = await _seed_session(session, "cust-1", {"vehicle_type": "ELECTRIC_MOTORBIKE"}, ["xem xe máy điện"])
    moto = await operations.refresh_session(str(third))
    assert moto is not None and moto.rule_code == "R2" and moto.opportunity_id != result.opportunity_id

    # TVV tách phiên 2 ra → cơ hội mới, ADVISOR; máy chạy lại không được lật quyết định.
    split = await operations.move_session(str(second), None, "adv-1")
    assert split not in {None, result.opportunity_id}
    await operations.refresh_session(str(second))
    async with factory() as session:
        attached = await session.get(SessionOpportunityRow, second)
        feedback = (await session.scalars(select(Customer360FeedbackRow))).all()
    assert (attached.decided_by, str(attached.opportunity_id)) == ("ADVISOR", split)
    assert [row.kind for row in feedback] == ["SESSION_SPLIT"]


@pytest.mark.asyncio
async def test_ho_so_dung_3_cau_sql_va_quyen(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    operations = _operations(factory)
    async with factory() as session:
        session_id = await _seed_session(
            session, "cust-2", {"vehicle_type": "CAR", "budget_max_vnd": 600_000_000}, ["tư vấn ô tô"]
        )
        session.add(
            CustomerProfileRow(
                customer_id="cust-2", display_name="Trần B", phone="0987654321", created_at=NOW, updated_at=NOW
            )
        )
        session.add(
            CustomerAdvisorAssignmentRow(
                assignment_id=uuid4(),
                customer_id="cust-2",
                advisor_id="adv-1",
                assigned_by="admin",
                status="ACTIVE",
                assigned_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await session.commit()
    await operations.refresh_session(str(session_id))

    reader = Customer360ReadOperations(SqlAlchemyCustomer360Query(factory), FakeFlags("customer360_ui"), lambda: NOW)
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        statements.append(statement)

    event.listen(migrated_engine.sync_engine, "before_cursor_execute", count)
    try:
        payload = await reader.overview("cust-2", requester_ids=("adv-1",), is_admin=False)
    finally:
        event.remove(migrated_engine.sync_engine, "before_cursor_execute", count)

    assert len(statements) == 3
    assert payload["customer"]["phone"] == "0987654321"
    assert payload["customer"]["phone_masked"] == "0987***321"
    [opportunity] = payload["opportunities"]
    assert opportunity["stage"] == "DISCOVER" and opportunity["needs"]["missing"]
    assert payload["sessions"][0]["kind"] == "SALES"

    admin = await reader.overview("cust-2", requester_ids=("admin-1",), is_admin=True)
    assert "phone" not in admin["customer"]
    with pytest.raises(CustomerAccessDeniedError):
        await reader.overview("cust-2", requester_ids=("adv-9",), is_admin=False)
    mine = await reader.list_opportunities(requester_ids=("adv-1",), is_admin=False, band=None, limit=10)
    assert [row["customer_id"] for row in mine] == ["cust-2"]
    assert await reader.list_opportunities(requester_ids=("adv-9",), is_admin=False, band=None, limit=10) == []
    picker = await reader.picker("Trần", 10)
    assert picker[0]["phone"] == "0987***321"
    metrics = await reader.metrics(30)
    assert metrics["stages"] == {"DISCOVER": 1} and metrics["totals"]["open_opportunities"] == 1

    off = Customer360ReadOperations(SqlAlchemyCustomer360Query(factory), FakeFlags(), lambda: NOW)
    with pytest.raises(Customer360DisabledError):
        await off.overview("cust-2", requester_ids=("adv-1",), is_admin=False)


@pytest.mark.asyncio
async def test_migration_0037_0038_len_xuong_sach(agent_database_url: str, _agent_migrations_applied: None) -> None:
    async def present() -> tuple[bool, bool, int]:
        engine = create_async_engine(agent_database_url)
        try:
            async with engine.connect() as connection:
                opportunities = bool(
                    await connection.scalar(text("SELECT to_regclass('public.customer_opportunities') IS NOT NULL"))
                )
                view = bool(
                    await connection.scalar(text("SELECT to_regclass('public.customer_360_facts') IS NOT NULL"))
                )
                flags = int(
                    await connection.scalar(
                        text("SELECT COUNT(*) FROM agent_feature_flags WHERE name LIKE 'customer360_%' AND NOT enabled")
                    )
                )
                return opportunities, view, flags
        finally:
            await engine.dispose()

    assert await present() == (True, True, 3)
    completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0036")
    assert completed.returncode == 0, completed.stderr
    assert await present() == (False, False, 0)
    completed = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "upgrade", "head")
    assert completed.returncode == 0, completed.stderr
    assert await present() == (True, True, 3)


@pytest.mark.asyncio
async def test_chat_luong_trich_xuat(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    operations = _operations(factory, FakeExtractor())
    async with factory() as session:
        first = await _seed_session(
            session,
            "cust-q",
            {"vehicle_type": "CAR", "budget_max_vnd": 700_000_000},
            ["tư vấn ô tô", "số em 0912345678", "Chắc tháng này em chốt, trả góp"],
        )
    await operations.refresh_session(str(first))
    async with factory() as session:
        timeframe = await session.scalar(
            select(CustomerInsightRow.insight_id).where(CustomerInsightRow.field == "purchase_timeframe")
        )
    assert await operations.insight_feedback(str(timeframe), "WRONG", "adv-1", "khách nói tháng sau")
    await operations.move_session(str(first), None, "adv-1")

    reader = Customer360ReadOperations(SqlAlchemyCustomer360Query(factory), FakeFlags(), lambda: NOW)
    quality = await reader.extraction_quality(30)

    assert quality["insights_total"] == 2 and quality["insights_reported_wrong"] == 1
    assert {"field": "purchase_timeframe", "total": 1, "wrong": 1} in quality["by_field"]
    assert quality["corrected_by_decider"] == {"RULE": 1}
    assert quality["samples"][0]["note"] == "khách nói tháng sau"
