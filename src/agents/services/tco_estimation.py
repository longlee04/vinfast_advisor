"""Application service for loading structured inputs and running A5-5 TCO."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.agents.contracts import EvidenceInput
from src.agents.ports import ClockPort, UnitOfWorkPort
from src.agents.tools.tco import (
    DetailedTcoResult,
    VehicleTcoInput,
    tco_unavailable,
    vinfast_tco_v1,
)
from src.products.domain.tco import KHU_VUC_II


class TcoDataSource(Protocol):
    """Load already-effective structured TCO rows without exposing SQLAlchemy."""

    async def load(self, *, vehicle_id: UUID, region_code: str, at: datetime) -> VehicleTcoInput | None: ...


class DefaultTcoEstimationService:
    """Load one vehicle's approved inputs and calculate deterministic TCO."""

    def __init__(
        self,
        *,
        data_source: TcoDataSource,
        clock: ClockPort,
        default_region_code: str = KHU_VUC_II,
        unit_of_work: UnitOfWorkPort | None = None,
    ) -> None:
        self._data_source = data_source
        self._clock = clock
        # Chỉ là giá trị dự phòng cho lời gọi chưa biết tỉnh của khách. Khu vực
        # THẬT đi theo từng request qua tham số `region_code` của `estimate()` —
        # cố định một vùng ở constructor nghĩa là cả hệ thống chỉ tính đúng cho
        # một nửa số khách.
        self._default_region_code = default_region_code
        self._unit_of_work = unit_of_work

    async def estimate(
        self,
        *,
        vehicle_id: UUID,
        daily_distance_km: float | None,
        run_id: UUID | None = None,
        region_code: str | None = None,
        discount_vnd: Decimal = Decimal("0"),
    ) -> DetailedTcoResult:
        """Return TCO or an explicit unavailable result without guessing missing data."""

        computed_at = self._clock.now()
        if daily_distance_km is None:
            return tco_unavailable(
                vehicle_id=vehicle_id,
                computed_at=computed_at,
                reason="daily_distance_km",
            )
        data = await self._data_source.load(
            vehicle_id=vehicle_id,
            region_code=region_code or self._default_region_code,
            at=computed_at,
        )
        if data is None:
            return tco_unavailable(
                vehicle_id=vehicle_id,
                computed_at=computed_at,
                reason="structured TCO data for vehicle",
            )
        result = vinfast_tco_v1(
            vehicle_id=vehicle_id,
            daily_distance_km=Decimal(str(daily_distance_km)),
            data=data,
            computed_at=computed_at,
            discount_vnd=discount_vnd,
        )
        await self._persist(run_id, result)
        return result

    async def _persist(self, run_id: UUID | None, result: DetailedTcoResult) -> None:
        """Đóng băng số của lượt này; không có run hoặc không có transaction thì bỏ qua."""

        if run_id is None or self._unit_of_work is None:
            return
        async with self._unit_of_work.transaction() as transaction:
            await transaction.runs.save_tco_estimate(run_id, result)
            if result.total_vnd is None:
                return
            # Tầng tổng hợp chỉ render số nào có evidence của chính lượt này;
            # thiếu dòng này thì `TCO_TOTAL_VND` không đối chiếu được và cả lượt vỡ.
            await transaction.runs.save_evidence(
                run_id,
                (
                    EvidenceInput(
                        fact_code="TCO_TOTAL_VND",
                        value_text=str(result.total_vnd),
                        source_table="tco_estimates",
                        source_id=result.vehicle_id,
                    ),
                ),
            )
