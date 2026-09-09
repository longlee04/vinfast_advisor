"""Use case ước tính tổng chi phí sở hữu."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from src.products.domain.errors import ProductDomainError, ProductNotFoundError
from src.products.domain.tco import TcoBreakdown, TcoInput, calculate_tco, derive_consumption

# Thứ tự ưu tiên. `PROMOTION_PRICE` có thời hạn còn TCO là ước tính nhiều năm;
# `BATTERY_SUBSCRIPTION` thuộc mô hình thuê pin đã ngừng bán từ 1/3/2025.
PRICE_PREFERENCE: Final[tuple[str, ...]] = ("BATTERY_INCLUDED", "STARTING_PRICE")


class TcoUnavailableError(ProductDomainError):
    """Thiếu dữ liệu để tính. Không bao giờ thay bằng số ước đoán."""


class TcoRepository(Protocol):
    """Port đọc mọi thứ cần cho một lần tính TCO."""

    async def get_tco_snapshot(self, identifier: str, *, region_code: str) -> dict | None: ...


@dataclass(frozen=True, slots=True)
class TcoEstimate:
    """Kết quả một lần tính, đủ để hiển thị kèm căn cứ."""

    breakdown: TcoBreakdown
    price_type: str
    kwh_per_100km: Decimal
    consumption_source: str
    derivation: str | None
    assumptions: dict


class TcoService:
    """Đọc dữ liệu, chọn giá, rồi giao cho hàm tính thuần."""

    def __init__(self, repository: TcoRepository) -> None:
        self._repository = repository

    async def estimate(self, identifier: str, *, monthly_km: Decimal, years: int, region_code: str) -> TcoEstimate:
        snapshot = await self._repository.get_tco_snapshot(identifier, region_code=region_code)
        if snapshot is None:
            raise ProductNotFoundError(f"vehicle {identifier} not found")

        assumptions = snapshot.get("assumptions")
        if not assumptions:
            raise TcoUnavailableError(f"no active tco assumptions for this vehicle type in region {region_code}")

        prices = snapshot.get("prices") or {}
        price_type = next((name for name in PRICE_PREFERENCE if prices.get(name)), None)
        if price_type is None:
            raise TcoUnavailableError("vehicle has no usable active price")

        consumption = derive_consumption(
            published_kwh_per_100km=snapshot.get("energy_consumption_kwh_per_100km"),
            battery_capacity_kwh=snapshot.get("battery_capacity_kwh"),
            range_km=snapshot.get("range_km"),
        )
        if consumption is None:
            raise TcoUnavailableError("vehicle has neither published nor derivable consumption")

        published = snapshot.get("energy_consumption_kwh_per_100km")
        is_published = published is not None and published > 0
        derivation = (
            None if is_published else (f"{snapshot['battery_capacity_kwh']} kWh / {snapshot['range_km']} km × 100")
        )

        breakdown = calculate_tco(
            TcoInput(
                vehicle_price_vnd=prices[price_type],
                monthly_km=monthly_km,
                years=years,
                kwh_per_100km=consumption,
                electricity_vnd_per_kwh=assumptions["electricity_vnd_per_kwh"],
                registration_fee_percent=assumptions["registration_fee_percent"],
                registration_fee_flat_vnd=assumptions["registration_fee_flat_vnd"],
                plate_fee_vnd=assumptions["plate_fee_vnd"],
                inspection_fee_vnd=assumptions["inspection_fee_vnd"],
                inspection_first_month=assumptions["inspection_first_month"],
                inspection_interval_months=assumptions["inspection_interval_months"],
                inspection_interval_months_after_7y=assumptions["inspection_interval_months_after_7y"],
                insurance_vnd_per_year=assumptions["mandatory_insurance_vnd_per_year"],
                road_fee_vnd_per_year=assumptions["road_fee_vnd_per_year"],
                maintenance_vnd_per_service=assumptions["maintenance_vnd_per_service"],
                maintenance_interval_km=assumptions["maintenance_interval_km"],
            )
        )

        return TcoEstimate(
            breakdown=breakdown,
            price_type=price_type,
            kwh_per_100km=consumption,
            consumption_source="published" if is_published else "derived",
            derivation=derivation,
            assumptions=assumptions,
        )
