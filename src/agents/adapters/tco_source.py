"""A5-5: adapter TCO của agent uỷ quyền cho `SqlAlchemyTcoRepository` của products.

Không tự tính bất kỳ con số nào ở đây — `src/products/domain/tco.py` là
calculator chuẩn duy nhất (mục PRD 8.4). Adapter chỉ đọc snapshot đã đóng băng
của products (giá `ACTIVE`, giả định TCO đang `ACTIVE`) và ánh xạ sang
`VehicleTcoInput` cho `vinfast_tco_v1` dùng.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.agents.domain.values import VehicleType
from src.agents.tools.tco import BatteryPolicyInput, TcoAssumptionInput, VehicleTcoInput
from src.products.infrastructure.repositories import SqlAlchemyTcoRepository


class ProductTcoDataSource:
    """Chuyển snapshot TCO của products sang `VehicleTcoInput` cho agent."""

    def __init__(self, session_factory) -> None:
        self._repository = SqlAlchemyTcoRepository(session_factory)

    async def load(self, *, vehicle_id: UUID, region_code: str, at: datetime) -> VehicleTcoInput | None:
        """Đọc snapshot xe/giá/giả định đang ACTIVE; `None` nếu không thấy xe."""

        # `region_code` TRƯỚC ĐÂY bị nhận rồi bỏ, nên mọi lượt đọc cùng một
        # dòng giả định bất kể khách ở đâu — lệ phí biển số ô tô chênh 100 lần
        # giữa hai khu vực nên đó là một con số sai, không phải xấp xỉ.
        snapshot = await self._repository.get_tco_snapshot(str(vehicle_id), region_code=region_code)
        if snapshot is None:
            return None

        vehicle_type = VehicleType(snapshot["vehicle_type"])
        assumption_snapshot = snapshot["assumptions"]
        assumptions: tuple[TcoAssumptionInput, ...] = ()
        if assumption_snapshot is not None:
            assumptions = (
                TcoAssumptionInput(
                    assumption_id=UUID(str(assumption_snapshot["assumption_id"])),
                    vehicle_type=vehicle_type,
                    region_code=assumption_snapshot["region_code"],
                    electricity_vnd_per_kwh=assumption_snapshot["electricity_vnd_per_kwh"],
                    horizon_months=assumption_snapshot["horizon_months"],
                    registration_fee_percent=assumption_snapshot["registration_fee_percent"],
                    registration_fee_flat_vnd=assumption_snapshot["registration_fee_flat_vnd"],
                    plate_fee_vnd=assumption_snapshot["plate_fee_vnd"],
                    inspection_fee_vnd=assumption_snapshot["inspection_fee_vnd"],
                    inspection_first_month=assumption_snapshot["inspection_first_month"],
                    inspection_interval_months=assumption_snapshot["inspection_interval_months"],
                    inspection_interval_months_after_7y=assumption_snapshot["inspection_interval_months_after_7y"],
                    mandatory_insurance_vnd_per_year=assumption_snapshot["mandatory_insurance_vnd_per_year"],
                    road_fee_vnd_per_year=assumption_snapshot["road_fee_vnd_per_year"],
                    maintenance_vnd_per_service=assumption_snapshot["maintenance_vnd_per_service"],
                    maintenance_interval_km=assumption_snapshot["maintenance_interval_km"],
                    source_note=assumption_snapshot["source_note"],
                ),
            )

        energy_consumption = snapshot["energy_consumption_kwh_per_100km"]
        battery_capacity = snapshot["battery_capacity_kwh"]
        range_km = snapshot["range_km"]

        return VehicleTcoInput(
            vehicle_type=vehicle_type,
            prices_vnd=snapshot["prices"],
            assumptions=assumptions,
            # VinFast dừng bán xe thuê pin từ 1/3/2025; `battery_policies` trong
            # DB chỉ còn là dữ liệu lịch sử nên không tính chi phí thuê pin.
            battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
            promotions=(),
            energy_consumption_kwh_per_100km=(None if energy_consumption is None else Decimal(str(energy_consumption))),
            battery_capacity_kwh=(None if battery_capacity is None else Decimal(str(battery_capacity))),
            range_max_km=None if range_km is None else Decimal(str(range_km)),
        )


__all__ = ["ProductTcoDataSource"]
