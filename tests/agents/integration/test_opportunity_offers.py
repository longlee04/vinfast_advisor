"""Ưu đãi theo cơ hội trên Postgres thật (plan Customer 360 Phase 5): luật DSL, vòng đời, hàng rào."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.agents.adapters.opportunity_offer_repository import SqlAlchemyOpportunityOfferRepository
from src.agents.adapters.promotion_catalog_source import SqlAlchemyPromotionCatalog
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.offer_lifecycle import OfferStatus
from src.agents.models import (
    ConversationSessionRow,
    CustomerInsightRow,
    CustomerOpportunityRow,
    OpportunityOfferEventRow,
    SessionOfferRow,
)
from src.agents.services.operations.opportunity_offers import (
    ActivePromotionGuard,
    OfferBlockedError,
    OffersDisabledError,
    OpportunityOfferOperations,
)
from src.products.infrastructure.models import PromotionRow
from tests.agents.integration.conftest import run_alembic

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
CODES = ("T-HN", "T-POLICE", "T-UNVERIFIED", "T-CRAWLER", "T-SOLDOUT")


class Flags:
    def __init__(self, *on: str) -> None:
        self.on = set(on)

    async def load(self, name: str) -> AgentFlagState | None:
        return AgentFlagState(name=name, enabled=name in self.on, rollout_percent=100)


def _promotion(code: str, *, rules: dict, status: str = "ACTIVE", **extra: object) -> PromotionRow:
    return PromotionRow(
        promotion_id=str(uuid4()),
        promotion_code=code,
        title=f"Ưu đãi {code}",
        promotion_type="FIXED_DISCOUNT",
        discount_amount_vnd=10_000_000,
        region_code="VN",
        eligibility_rules=rules,
        status=status,
        valid_from=NOW - timedelta(days=1),
        valid_to=NOW + timedelta(days=30),
        created_at=NOW,
        updated_at=NOW,
        **extra,
    )


@pytest.mark.asyncio
async def test_luat_vong_doi_va_hang_rao(migrated_engine: AsyncEngine, clean_agent_database: None) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    opportunity_id = uuid4()
    async with factory() as session:
        await session.execute(delete(PromotionRow).where(PromotionRow.promotion_code.in_(CODES)))
        session.add_all(
            [
                _promotion(
                    "T-HN",
                    rules={"all": [{"field": "registration_province", "in": ["HN"]}]},
                    advisor_max_discount_vnd=20_000_000,
                    priority=1,
                ),
                _promotion("T-POLICE", rules={"field": "customer_group", "in": ["POLICE_MILITARY"]}, priority=2),
                _promotion("T-UNVERIFIED", rules={}, status="UNVERIFIED"),
                _promotion("T-CRAWLER", rules={"source_url": "https://…", "eligible_group": "VNPOST"}),
                _promotion("T-SOLDOUT", rules={}, max_uses=1, used_count=1),
            ]
        )
        session.add(
            ConversationSessionRow(
                session_id=uuid4(),
                customer_id="cust-o",
                status="ACTIVE",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            CustomerOpportunityRow(
                opportunity_id=opportunity_id,
                customer_id="cust-o",
                vehicle_type="CAR",
                buyer_for="SELF",
                status="OPEN",
                slots_snapshot={"vehicle_type": "CAR", "budget_max_vnd": 800_000_000},
                slot_history=[],
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        await session.flush()
        session.add(
            CustomerInsightRow(
                insight_id=uuid4(),
                customer_id="cust-o",
                field="registration_province",
                value="HN",
                value_code="HN",
                source="SLOT",
                extracted_at=NOW,
            )
        )
        await session.commit()

    catalog = SqlAlchemyPromotionCatalog(factory)
    operations = OpportunityOfferOperations(
        SqlAlchemyOpportunityOfferRepository(factory),
        catalog,
        clock=lambda: NOW,
        flags=Flags("offer_rules_engine", "offer_lifecycle"),
    )
    try:
        result = await operations.eligible(str(opportunity_id))
        assert [item["promotion_code"] for item in result["eligible"]] == ["T-HN"]
        assert [item["promotion_code"] for item in result["need_info"]] == ["T-POLICE"]
        assert result["need_info"][0]["missing_fields"] == ["customer_group"]
        # UNVERIFIED, metadata crawler, hết suất: KHÔNG xuất hiện ở đâu cả.
        offered = {item["promotion_code"] for group in result.values() for item in group}
        assert offered.isdisjoint({"T-UNVERIFIED", "T-CRAWLER", "T-SOLDOUT"})

        # Vượt ngưỡng TVV (30tr > 20tr) → chờ quản lý; gửi bị chặn.
        offer = await operations.create(str(opportunity_id), "T-HN", {"amount_vnd": 30_000_000}, "adv-1")
        assert (offer.status, offer.needs_manager_approval) == (OfferStatus.SUGGESTED, True)
        with pytest.raises(OfferBlockedError) as blocked:
            await operations.send(offer.offer_id, "adv-1")
        assert blocked.value.reason == "NEEDS_MANAGER"

        await operations.approve(offer.offer_id, "admin-1")
        sent = await operations.send(offer.offer_id, "adv-1")
        assert sent.status is OfferStatus.SENT

        async with factory() as session:
            delivered = await session.scalar(select(SessionOfferRow).where(SessionOfferRow.promotion_code == "T-HN"))
            used = await session.scalar(select(PromotionRow.used_count).where(PromotionRow.promotion_code == "T-HN"))
            events = await session.scalar(select(func.count()).select_from(OpportunityOfferEventRow))
        assert delivered is not None and str(delivered.opportunity_offer_id) == offer.offer_id
        assert delivered.source_kind == "OPPORTUNITY_OFFER" and delivered.approved_by == "adv-1"
        assert used == 1 and events == 3

        stats = await operations.stats("T-HN")
        assert stats[0]["sent"] == 1 and stats[0]["conversion_rate"] == 0.0

        # Ưu đãi gốc bị huỷ → agent không còn được nhắc (cờ bật); cờ tắt → như cũ.
        async with factory() as session:
            await session.execute(
                PromotionRow.__table__.update().where(PromotionRow.promotion_code == "T-HN").values(status="CANCELLED")
            )
            await session.commit()
        assert await ActivePromotionGuard(catalog, Flags("offer_lifecycle"), lambda: NOW).allowed(["T-HN"]) == set()
        assert await ActivePromotionGuard(catalog, Flags(), lambda: NOW).allowed(["T-HN"]) == {"T-HN"}

        off = OpportunityOfferOperations(
            SqlAlchemyOpportunityOfferRepository(factory), catalog, clock=lambda: NOW, flags=Flags()
        )
        with pytest.raises(OffersDisabledError):
            await off.eligible(str(opportunity_id))
    finally:
        async with factory() as session:
            await session.execute(delete(PromotionRow).where(PromotionRow.promotion_code.in_(CODES)))
            await session.commit()


@pytest.mark.asyncio
async def test_migration_promotion_guardrails_len_xuong(
    agent_database_url: str, _agent_migrations_applied: None
) -> None:
    async def columns() -> set[str]:
        engine = create_async_engine(agent_database_url)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'promotions'")
                )
                return {row[0] for row in rows}
        finally:
            await engine.dispose()

    guardrails = {"stackable", "priority", "max_uses", "used_count", "advisor_max_discount_vnd", "source_meta"}
    assert guardrails <= await columns()
    # 0039 thêm FK logic sang customer_opportunities — hạ agent trước, rồi products.
    down_agent = run_alembic(agent_database_url, "alembic-agent.ini", "AGENT_DATABASE_URL", "downgrade", "agent_0038")
    assert down_agent.returncode == 0, down_agent.stderr
    down = run_alembic(agent_database_url, "alembic-products.ini", "PRODUCT_DATABASE_URL", "downgrade", "b2c3d4e5f6a7")
    assert down.returncode == 0, down.stderr
    assert not guardrails & await columns()
    for configuration, variable in (
        ("alembic-products.ini", "PRODUCT_DATABASE_URL"),
        ("alembic-agent.ini", "AGENT_DATABASE_URL"),
    ):
        up = run_alembic(agent_database_url, configuration, variable, "upgrade", "head")
        assert up.returncode == 0, up.stderr
    assert guardrails <= await columns()
