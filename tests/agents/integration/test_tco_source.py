"""A5-5: agent và API dùng chung nguồn TCO, không có công thức thứ hai."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.agents.adapters.tco_source import ProductTcoDataSource
from src.products.infrastructure.models import VehiclePriceRow, VehicleRow


@pytest.mark.asyncio
async def test_load_returns_input_for_a_real_car(agent_session, agent_session_factory):
    # `clean_agent_database` xoá sạch bảng `vehicles` trước mỗi test (không seed
    # dữ liệu mẫu). `ProductTcoDataSource` tự mở session riêng qua
    # `agent_session_factory`, nên phải chèn và COMMIT qua chính factory đó —
    # chèn qua transaction đang mở của `agent_session` sẽ không thấy được từ
    # một connection khác (READ COMMITTED).
    now = datetime.now(UTC)
    car_id = str(uuid4())
    async with agent_session_factory() as seed_session, seed_session.begin():
        seed_session.add_all(
            [
                VehicleRow(
                    vehicle_id=car_id,
                    vehicle_type="CAR",
                    brand="VinFast",
                    model_name="VF 7",
                    variant_name="TCO source test",
                    status="ACTIVE",
                    slug=f"vf-7-tco-source-{car_id}",
                    created_at=now,
                    updated_at=now,
                ),
                VehiclePriceRow(
                    price_id=str(uuid4()),
                    vehicle_id=car_id,
                    price_type="STARTING_PRICE",
                    amount_vnd=Decimal("700000000"),
                    currency="VND",
                    region_code="VN",
                    status="ACTIVE",
                    valid_from=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )

    vehicle_id = await agent_session.scalar(text("select vehicle_id from vehicles where vehicle_type = 'CAR' limit 1"))
    source = ProductTcoDataSource(agent_session_factory)

    result = await source.load(vehicle_id=vehicle_id, region_code="VN", at=datetime.now(UTC))

    assert result is not None
    assert result.prices_vnd


@pytest.mark.asyncio
async def test_load_returns_none_for_unknown_vehicle(agent_session_factory):
    source = ProductTcoDataSource(agent_session_factory)

    result = await source.load(vehicle_id=uuid4(), region_code="VN", at=datetime.now(UTC))

    assert result is None
