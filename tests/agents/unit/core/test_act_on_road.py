"""Lượt GIÁ LĂN BÁNH: câu kết không được mời khách xem thứ đang hiện trên thẻ.

Thẻ chi phí của lượt lăn bánh đã chứa chi phí 5 năm (Sếp 2026-08-31: "giá lăn
bánh với TCO là MỘT"). `_closing` suy `has_tco` từ chặng `COSTING`, nhưng
`policy._run_vehicle_intent` giữ `stage=CHOSEN` cho lượt đầu → câu kết cũ mời
"xem chi phí 5 năm trước?" ngay dưới thẻ đang hiện con số đó.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from src.agents.contracts import CatalogBrowseResult, TcoResult, VehiclePitch
from src.agents.core.act import act
from src.agents.core.actions import OnRoadPrice
from src.agents.core.state import CoreState, Stage
from src.agents.domain.values import SlotName as N
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        pitch = VehiclePitch(
            vehicle_id=V1, rank=1, display_name="VinFast VF 5", pitch="", citations=(), starting_price_vnd=None
        )
        return CatalogBrowseResult(answer="VF 5", pitches=(pitch,))


class _Tco:
    async def estimate(self, *, vehicle_id: Any, daily_distance_km: float, run_id: Any = None, region_code: Any = None):
        return TcoResult(
            vehicle_id=vehicle_id,
            total_vnd=Decimal("560000000"),
            components_vnd={"promoted_purchase_price_vnd": Decimal("480000000")},
            assumptions_id=None,
            computed_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [Stage.CHOSEN, Stage.RECOMMENDED])
async def test_closing_khong_moi_xem_thu_dang_hien(stage: Stage) -> None:
    services = AgentServices(tco_estimation=_Tco(), catalog_browse=_Catalog())
    state = CoreState(
        session_id="s1", stage=stage, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"}
    )
    result = await act(
        OnRoadPrice(vehicle_id=V1), state, services, run_id=None, customer_id="c1", user_message="vf5 lăn bánh bao nhiêu"
    )
    assert "tco_card" in result.cards
    assert "chi phí 5 năm" not in result.text
    assert "lăn bánh" in result.text
    assert "lái thử" in result.text
