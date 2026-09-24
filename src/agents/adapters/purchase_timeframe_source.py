"""Cổng đọc "khách đã nói thời điểm mua chưa" cho câu hỏi lồng 4G (plan Customer 360).

Chỉ ĐỌC `customer_insights`: hàng `purchase_timeframe` còn hiện hành (chưa bị
thay) của khách. Chỉ chạy khi cờ `agent_ask_purchase_timeframe` bật cho khách —
cờ tắt thì `act` không gọi tới đây.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.domain.customer_insight import InsightField
from src.agents.logging import get_agent_logger
from src.agents.models import CustomerInsightRow

logger = get_agent_logger(__name__)


class SqlAlchemyPurchaseTimeframeSource:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def known(self, customer_id: str) -> bool:
        """Đọc hỏng → `True`: thà bớt một câu hỏi còn hơn hỏi lại điều khách đã nói."""

        try:
            async with self._session_factory() as session:
                found = await session.scalar(
                    select(CustomerInsightRow.insight_id)
                    .where(
                        CustomerInsightRow.customer_id == customer_id,
                        CustomerInsightRow.field == InsightField.PURCHASE_TIMEFRAME.value,
                        CustomerInsightRow.superseded_by.is_(None),
                    )
                    .limit(1)
                )
        except Exception:
            logger.warning("purchase_timeframe.known: doc insight loi, coi nhu da biet", exc_info=True)
            return True
        return found is not None
