"""Việc định kỳ của Customer 360 (plan Phase 4, G3/G4) — chạy bằng cron mỗi 15 phút.

    python -m scripts.customer360_sweep            # đúng như cron
    python -m scripts.customer360_sweep --limit 50

Làm bốn việc: cơ hội im > 30 ngày → DORMANT; phiên idle > 30 phút chưa được gắn/đánh giá
tới lượt cuối → gắn cơ hội (chỉ khách có cờ `customer360_attach`); tính lại độ nóng (điểm
giảm theo thời gian); nhả khách không có hoạt động tư vấn viên trong 7 ngày về hàng chờ. Task nền trong process API mất khi restart thì chính script này nhặt lại.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.agents.adapters.agent_flag_repository import SqlAlchemyAgentFlagAdapter
from src.agents.adapters.clock import SystemClock
from src.agents.adapters.customer_360_llm import OpenAIInsightExtractor, OpenAIOpportunityClassifier
from src.agents.adapters.customer_identity_source import AuthProfileIdentitySource
from src.agents.adapters.customer_opportunity_repository import SqlAlchemyCustomer360Repository
from src.agents.adapters.customer_ownership_repository import SqlAlchemyCustomerOwnershipRepository
from src.agents.adapters.opportunity_offer_repository import SqlAlchemyOpportunityOfferRepository
from src.agents.adapters.promotion_catalog_source import SqlAlchemyPromotionCatalog
from src.agents.composition import agent_database_url
from src.agents.services.operations.customer_360 import Customer360Operations
from src.agents.services.operations.customer_ownership import CustomerOwnershipOperations
from src.agents.services.operations.opportunity_offers import OpportunityOfferOperations


async def _run(limit: int) -> dict[str, int]:
    database_url = agent_database_url()
    if not database_url:
        raise SystemExit("Thiếu AGENT_DATABASE_URL")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        operations = Customer360Operations(
            SqlAlchemyCustomer360Repository(factory),
            clock=SystemClock().now,
            flags=SqlAlchemyAgentFlagAdapter(factory),
            classifier=OpenAIOpportunityClassifier(),
            extractor=OpenAIInsightExtractor(),
            identity=AuthProfileIdentitySource(factory),
        )
        result = await operations.sweep(limit=limit)
        # Ưu đãi quá `expires_at` → EXPIRED (kèm `session_offers`, agent thôi nhắc).
        offers = OpportunityOfferOperations(
            SqlAlchemyOpportunityOfferRepository(factory), SqlAlchemyPromotionCatalog(factory), clock=SystemClock().now
        )
        result["offers_expired"] = await offers.expire_due()
        # Tư vấn viên tự nhận khách: khách bị bỏ quên quay lại hàng chờ cho người khác nhận.
        ownership = CustomerOwnershipOperations(SqlAlchemyCustomerOwnershipRepository(factory), SystemClock().now)
        result["customers_released"] = len(await ownership.release_stale())
        return result
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=200, help="Số phiên/cơ hội tối đa mỗi lượt")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.limit)), ensure_ascii=False))


if __name__ == "__main__":
    main()
