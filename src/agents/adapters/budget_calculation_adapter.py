"""BudgetCalculationAdapter — wraps CatalogReadAdapter for budget-count queries.

Adapter nhẹ dùng bởi BudgetCalculatorNode: không cần toàn bộ giao diện
của RetrievalService, chỉ cần đọc danh sách xe + giá khởi điểm.
"""

from __future__ import annotations

from decimal import Decimal

from src.agents.adapters.catalog_reader import CatalogReadAdapter


class BudgetCalculationAdapter:
    """Delegate get_prices_under_budget tới CatalogReadAdapter."""

    def __init__(self, catalog: CatalogReadAdapter) -> None:
        self._catalog = catalog

    async def get_prices_under_budget(self, budget: Decimal) -> list[dict]:
        """Trả danh sách ``{"name": str, "price": Decimal}`` với giá <= budget."""
        return await self._catalog.get_prices_under_budget(budget)
