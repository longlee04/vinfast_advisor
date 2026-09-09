"""Application-layer ports (interfaces) and DTOs for the Vehicle Catalog module.

DTOs ở đây là projection phục vụ use-case (vd: ``VehicleDetail`` gộp
``Vehicle`` + specs + prices + flags + policies). Domain entities thuần nằm ở
``domain/entities.py`` và là 1-1 với schema. Không đặt DTO vào domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.products.domain.entities import (
    BatteryPolicy,
    Car,
    FeatureDefinition,
    Motorbike,
    Promotion,
    PromotionVehicle,
    Vehicle,
    VehicleFeatureFlag,
    VehiclePrice,
    VehicleShowcaseItem,
)
from src.products.domain.values import RecordLifecycleStatus, VehicleStatus

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PageParams:
    """Simple offset pagination helper."""

    def __init__(self, skip: int = 0, limit: int = 50) -> None:
        self.skip = max(0, skip)
        self.limit = min(max(1, limit), 200)


# ---------------------------------------------------------------------------
# Application DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Lightweight price record for catalog responses."""

    price_id: str
    price_type: str
    amount_vnd: int
    currency: str
    region_code: str
    status: RecordLifecycleStatus
    valid_from: datetime
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class FeatureFlagSummary:
    feature_code: str
    name: str
    status: str
    verification_status: str
    value_text: str | None = None
    value_number: Decimal | None = None
    value_boolean: bool | None = None


@dataclass(frozen=True, slots=True)
class FeatureFlagDetail:
    """Mot dong vehicle_feature_flags kem ten xe/feature de hien o man Admin."""

    vehicle_id: str
    feature_code: str
    status: str
    verification_status: str
    vehicle_name: str
    feature_name: str
    confidence: Decimal | None
    updated_by: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VehicleDetail:
    """Aggregate projection cho Customer/Admin catalog endpoint.

    Bao gồm vehicle, specs (Car hoặc Motorbike), prices, promotion links và
    feature flags. Repository build DTO này từ ORM, service trả về nguyên trạng.
    """

    vehicle: Vehicle
    specs: Car | Motorbike | None
    prices: list[PricePoint] = field(default_factory=list)
    promotions: list[PromotionVehicle] = field(default_factory=list)
    battery_policies: list[BatteryPolicy] = field(default_factory=list)
    feature_flags: list[FeatureFlagSummary] = field(default_factory=list)
    showcase_items: list[VehicleShowcaseItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """DTO tổng quan cho RAG: chứa luôn danh sách FeatureDefinition đã active."""

    vehicle: Vehicle
    specs: Car | Motorbike | None
    prices: list[PricePoint] = field(default_factory=list)
    promotions: list[Promotion] = field(default_factory=list)
    battery_policies: list[BatteryPolicy] = field(default_factory=list)
    feature_flags: list[FeatureFlagSummary] = field(default_factory=list)
    feature_definitions: list[FeatureDefinition] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class VehicleRepository(ABC):
    """Port cho Vehicle Catalog persistence."""

    @abstractmethod
    async def get_vehicle(self, identifier: str) -> VehicleDetail | None: ...

    @abstractmethod
    async def get_vehicle_by_slug(self, slug: str) -> VehicleDetail | None: ...

    @abstractmethod
    async def list_vehicles(
        self,
        page: PageParams,
        status: VehicleStatus | None = None,
        vehicle_type: str | None = None,
    ) -> list[VehicleDetail]: ...

    @abstractmethod
    async def search_vehicles(
        self,
        query: str,
        page: PageParams,
        status: VehicleStatus | None = None,
    ) -> list[VehicleDetail]: ...

    @abstractmethod
    async def count_vehicles(
        self,
        status: VehicleStatus | None = None,
        vehicle_type: str | None = None,
    ) -> int: ...

    @abstractmethod
    async def create_vehicle(self, data: dict) -> VehicleDetail: ...

    @abstractmethod
    async def archive_vehicle(self, vehicle_id: str) -> VehicleDetail | None: ...

    @abstractmethod
    async def restore_vehicle(self, vehicle_id: str) -> VehicleDetail | None: ...

    @abstractmethod
    async def update_vehicle(self, vehicle_id: str, data: dict) -> VehicleDetail | None: ...

    @abstractmethod
    async def replace_vehicle_prices(self, vehicle_id: str, prices: list[dict]) -> VehicleDetail | None: ...

    @abstractmethod
    async def update_vehicle_price(self, vehicle_id: str, price_id: str, data: dict) -> VehicleDetail | None: ...

    @abstractmethod
    async def update_vehicle_specs(self, vehicle_id: str, data: dict) -> VehicleDetail | None: ...

    @abstractmethod
    async def update_feature_flag(
        self, vehicle_id: str, feature_code: str, data: dict
    ) -> FeatureFlagSummary | None: ...

    @abstractmethod
    async def delete_vehicle(self, vehicle_id: str) -> bool: ...

    @abstractmethod
    async def get_rag_snapshot(self, identifier: str) -> CatalogSnapshot | None: ...


class FeatureFlagRepository(ABC):
    """Doc/duyet vehicle_feature_flags cho man quan tri."""

    @abstractmethod
    async def list_flags(
        self,
        page: PageParams,
        *,
        verification_status: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[FeatureFlagDetail]: ...

    @abstractmethod
    async def count_flags(self, *, verification_status: str | None = None, vehicle_id: str | None = None) -> int: ...

    @abstractmethod
    async def review_flag(
        self, vehicle_id: str, feature_code: str, decision: str, actor_id: str
    ) -> FeatureFlagDetail | None: ...


__all__ = [
    "CatalogSnapshot",
    "FeatureFlagDetail",
    "FeatureFlagRepository",
    "FeatureFlagSummary",
    "PageParams",
    "PricePoint",
    "VehicleDetail",
    "VehicleFeatureFlag",
    "VehiclePrice",
    "VehicleRepository",
]
