"""Dựng cơ hội cho các phiên ĐÃ CÓ trước khi bật Customer 360 (plan Phase 4 mục 4 — backfill).

    python -m scripts.customer360_backfill                 # chỉ luật, không gọi LLM, không trích insight
    python -m scripts.customer360_backfill --since 2026-08-01 --with-insights --max-sessions 500

Mặc định CHỈ LUẬT: ca mơ hồ (R7) được gắn tạm + `needs_review` để TVV quyết, không tốn tiền
LLM. `--with-insights` bật trích insight (có trần `--max-sessions`). Idempotent: phiên đã gắn
không bị đổi quyết định của TVV; chạy lại chỉ cập nhật những gì mới.
Phiên được xử lý theo thứ tự thời gian để cơ hội sinh ra đúng trình tự khách đã đi.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.customer_360_llm import OpenAIInsightExtractor
from src.agents.adapters.customer_identity_source import AuthProfileIdentitySource
from src.agents.adapters.customer_opportunity_repository import SqlAlchemyCustomer360Repository
from src.agents.composition import agent_database_url
from src.agents.models import ConversationSessionRow
from src.agents.services.operations.customer_360 import Customer360Operations


async def _run(since: datetime | None, with_insights: bool, max_sessions: int) -> dict[str, object]:
    database_url = agent_database_url()
    if not database_url:
        raise SystemExit("Thiếu AGENT_DATABASE_URL")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    rules: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    insights = 0
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        operations = Customer360Operations(
            SqlAlchemyCustomer360Repository(factory),
            clock=SystemClock().now,
            classifier=None,  # chỉ luật — R7 gắn tạm, TVV quyết
            extractor=OpenAIInsightExtractor() if with_insights else None,
            identity=AuthProfileIdentitySource(factory),
        )
        statement = select(ConversationSessionRow.session_id).order_by(
            ConversationSessionRow.customer_id, ConversationSessionRow.started_at
        )
        if since is not None:
            statement = statement.where(ConversationSessionRow.last_activity_at >= since)
        async with factory() as session:
            session_ids = [str(item) for item in (await session.scalars(statement.limit(max_sessions)))]
        for session_id in session_ids:
            result = await operations.refresh_session(session_id, force_extract=with_insights)
            if result is None:
                continue
            rules[result.rule_code or "ADVISOR"] += 1
            insights += result.insights_saved
            rejected.update(result.rejected)
    finally:
        await engine.dispose()
    return {
        "sessions": sum(rules.values()),
        "rules": dict(rules),
        "insights_saved": insights,
        "rejected": dict(rejected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=lambda value: datetime.fromisoformat(value).replace(tzinfo=UTC))
    parser.add_argument("--with-insights", action="store_true")
    parser.add_argument("--max-sessions", type=int, default=5000)
    args = parser.parse_args()
    print(
        json.dumps(asyncio.run(_run(args.since, args.with_insights, args.max_sessions)), ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
