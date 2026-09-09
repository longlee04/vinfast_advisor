"""Application service — use cases for the Vehicle Catalog.

VehicleCatalogService thay thế các service riêng lẻ (CarService / MotorbikeService
/ PolicyService) trong schema cũ. Service này thao tác trên DTO
``VehicleDetail`` của application layer.
"""

from __future__ import annotations

from decimal import Decimal

from src.products.application import (
    CatalogSnapshot,
    FeatureFlagSummary,
    PageParams,
    VehicleDetail,
    VehicleRepository,
)
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.values import VehicleStatus, VehicleType


class VehicleCatalogService:
    """Use-case orchestrator cho Customer và Admin catalog endpoints."""

    def __init__(self, repository: VehicleRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Customer / Read-only
    # ------------------------------------------------------------------

    async def list_active_vehicles(self, page: PageParams, vehicle_type: str | None = None) -> list[VehicleDetail]:
        return await self._repo.list_vehicles(page, status=VehicleStatus.ACTIVE, vehicle_type=vehicle_type)

    async def count_active_vehicles(self, vehicle_type: str | None = None) -> int:
        return await self._repo.count_vehicles(status=VehicleStatus.ACTIVE, vehicle_type=vehicle_type)

    async def get_vehicle_detail(self, identifier: str) -> VehicleDetail:
        # Try to get vehicle by ID first
        detail = await self._repo.get_vehicle(identifier)
        if detail is None:
            # If not found by ID, try to get by slug
            detail = await self._repo.get_vehicle_by_slug(identifier)
            if detail is None:
                # If still not found, try to get by SKU
                detail = await self._repo.get_vehicle_by_sku(identifier)

        # If vehicle is found and active, return it
        if detail is not None and detail.vehicle.status == VehicleStatus.ACTIVE:
            return detail

        # If vehicle is not active, try to get RAG snapshot
        snapshot = await self._repo.get_rag_snapshot(identifier)
        if snapshot:
            return VehicleDetail(
                vehicle=snapshot.vehicle,
                specs=snapshot.specs,
                prices=snapshot.prices,
                promotions=[],  # No promotion data in snapshot
                battery_policies=snapshot.battery_policies,
                feature_flags=snapshot.feature_flags,
            )

        # If vehicle is not found or inactive and no RAG snapshot exists
        raise ProductNotFoundError(f"Vehicle {identifier!r} not found or inactive")

    async def search_vehicles(self, query: str, page: PageParams) -> list[VehicleDetail]:
        return await self._repo.search_vehicles(query, page, status=VehicleStatus.ACTIVE)

    # ------------------------------------------------------------------
    # RAG helper
    # ------------------------------------------------------------------

    async def get_vehicle_rag_context(self, identifier: str) -> str:
        # First, check if the vehicle exists and is active
        vehicle_detail = await self._repo.get_vehicle(identifier)
        if vehicle_detail is None:
            vehicle_detail = await self._repo.get_vehicle_by_slug(identifier)
            if vehicle_detail is None:
                vehicle_detail = await self._repo.get_vehicle_by_sku(identifier)

        # If vehicle is not found or inactive, raise an error
        if vehicle_detail is None or vehicle_detail.vehicle.status != VehicleStatus.ACTIVE:
            raise ProductNotFoundError(f"Vehicle {identifier!r} not found or inactive")

        # Get the RAG snapshot
        snapshot = await self._repo.get_rag_snapshot(identifier)
        if snapshot is None:
            raise ProductNotFoundError(f"RAG context for vehicle {identifier!r} not found")

        return _render_snapshot_as_markdown(snapshot)

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def list_admin_vehicles(
        self,
        page: PageParams,
        status: str | None = None,
        *,
        is_admin: bool,
    ) -> list[VehicleDetail]:
        if not is_admin:
            raise ProductPermissionError("Admin role required")

        status_enum: VehicleStatus | None = None
        if status is not None:
            try:
                status_enum = VehicleStatus(status.strip().upper())
            except ValueError:
                # If status is invalid, raise a permission error
                raise ProductPermissionError(f"Invalid status: {status}")

        return await self._repo.list_vehicles(page, status=status_enum)

    async def count_admin_vehicles(
        self,
        status: str | None = None,
        *,
        is_admin: bool,
    ) -> int:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        status_enum: VehicleStatus | None = None
        if status is not None:
            try:
                status_enum = VehicleStatus(status.strip().upper())
            except ValueError:
                status_enum = None
        return await self._repo.count_vehicles(status=status_enum)

    async def create_vehicle(self, data: dict, *, is_admin: bool) -> VehicleDetail:
        if not is_admin:
            raise ProductPermissionError("Admin role required")

        # Validate required fields
        if not data.get("brand") or not data.get("model_name"):
            raise ValueError("Brand and model_name are required fields")

        return await self._repo.create_vehicle(data)

    async def update_vehicle_price(
        self, vehicle_id: str, price_id: str, data: dict, *, is_admin: bool
    ) -> VehicleDetail:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        detail = await self._repo.update_vehicle_price(vehicle_id, price_id, data)
        if detail is None:
            raise ProductNotFoundError(f"Price {price_id!r} for vehicle {vehicle_id!r} not found")
        return detail

    async def update_vehicle_specs(self, vehicle_id: str, data: dict, *, is_admin: bool) -> VehicleDetail:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        detail = await self._repo.update_vehicle_specs(vehicle_id, data)
        if detail is None:
            raise ProductNotFoundError(f"Specs for vehicle {vehicle_id!r} not found")
        return detail

    async def review_feature_flag(
        self, vehicle_id: str, feature_code: str, data: dict, *, is_admin: bool
    ) -> FeatureFlagSummary:
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        flag = await self._repo.update_feature_flag(vehicle_id, feature_code, data)
        if flag is None:
            raise ProductNotFoundError(f"Feature flag {feature_code!r} for vehicle {vehicle_id!r} not found")
        return flag

    async def delete_vehicle(self, vehicle_id: str, *, is_admin: bool) -> None:
        if not is_admin:
            raise ProductPermissionError("Admin role required")

        deleted = await self._repo.delete_vehicle(vehicle_id)
        if not deleted:
            raise ProductNotFoundError(f"Vehicle {vehicle_id!r} not found")

    async def archive_vehicle(self, vehicle_id: str, *, is_admin: bool) -> VehicleDetail:
        """Chuyển xe sang ARCHIVED. Không xóa hàng — §6.5 schema doc.

        Idempotent: archive một xe đã ARCHIVED trả về chính nó, không lỗi.
        """
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        detail = await self._repo.archive_vehicle(vehicle_id)
        if detail is None:
            raise ProductNotFoundError(f"Vehicle {vehicle_id!r} not found")
        return detail

    async def restore_vehicle(self, vehicle_id: str, *, is_admin: bool) -> VehicleDetail:
        """Gỡ ARCHIVED, đưa xe về ACTIVE."""
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        detail = await self._repo.restore_vehicle(vehicle_id)
        if detail is None:
            raise ProductNotFoundError(f"Vehicle {vehicle_id!r} not found")
        return detail

    async def update_vehicle(self, vehicle_id: str, data: dict, *, is_admin: bool) -> VehicleDetail:
        """Partial update — chi doi field co mat va khac None (§6.4 schema doc)."""
        if not is_admin:
            raise ProductPermissionError("Admin role required")

        changes = {k: v for k, v in data.items() if v is not None}
        if "status" in changes:
            # Nem ValueError de route tra 400 thay vi im lang giu status cu.
            VehicleStatus(str(changes["status"]).strip().upper())
        if "vehicle_type" in changes:
            VehicleType(str(changes["vehicle_type"]).strip().upper())

        detail = await self._repo.update_vehicle(vehicle_id, changes)
        if detail is None:
            raise ProductNotFoundError(f"Vehicle {vehicle_id!r} not found")
        return detail

    async def replace_vehicle_prices(self, vehicle_id: str, prices: list[dict], *, is_admin: bool) -> VehicleDetail:
        """Dong version gia cu (EXPIRED), mo version moi (ACTIVE) — §6.3.

        Khong sua gia tai cho: lich su gia la du lieu can giu de audit va de
        snapshot A5-2 truy nguoc duoc "luc do gia bao nhieu".
        """
        if not is_admin:
            raise ProductPermissionError("Admin role required")
        seen_keys: set[tuple[str, str]] = set()
        for entry in prices:
            amount = entry.get("amount_vnd")
            if amount is None or int(amount) < 0:
                raise ValueError(f"amount_vnd khong hop le: {amount!r}")
            # DB co partial UNIQUE index (vehicle_id, price_type, region_code)
            # WHERE status='ACTIVE'; repo cung uppercase ca hai gia tri truoc khi
            # ghi, nen phai chan trung lap o day de tra ValueError (400) thay vi
            # de IntegrityError roi xuong tang DB (500).
            price_type = str(entry.get("price_type") or "").strip().upper()
            region_code = str(entry.get("region_code") or "VN").strip().upper()
            key = (price_type, region_code)
            if key in seen_keys:
                raise ValueError(f"price_type trung lap trong cung region_code: {price_type}/{region_code}")
            seen_keys.add(key)
        detail = await self._repo.replace_vehicle_prices(vehicle_id, prices)
        if detail is None:
            raise ProductNotFoundError(f"Vehicle {vehicle_id!r} not found")
        return detail


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_snapshot_as_markdown(snapshot: CatalogSnapshot) -> str:
    parts: list[str] = [
        f"# {snapshot.vehicle.brand} {snapshot.vehicle.model_name}"
        + (f" {snapshot.vehicle.variant_name}" if snapshot.vehicle.variant_name else ""),
        f"- vehicle_id: {snapshot.vehicle.vehicle_id}",
        f"- vehicle_type: {snapshot.vehicle.vehicle_type.value}",
        f"- status: {snapshot.vehicle.status.value}",
        f"- model_year: {snapshot.vehicle.model_year or 'N/A'}",
    ]

    # Handle specs section
    if snapshot.specs is not None:
        parts.append("\n## Thông số kỹ thuật")
        for field in snapshot.specs.__dataclass_fields__:
            value = getattr(snapshot.specs, field)
            if value in (None, "", 0):
                continue
            # Convert Decimal to float for display
            if isinstance(value, (Decimal, float)):
                value = float(value)
            parts.append(f"- {field}: {value}")

    # Handle prices section
    if snapshot.prices:
        parts.append("\n## Bảng giá")
        for p in snapshot.prices:
            parts.append(
                f"- {p.price_type}: {p.amount_vnd:,} {p.currency}"
                + (f" (region={p.region_code})" if p.region_code else "")
            )

    # Handle promotions section
    if snapshot.promotions:
        parts.append("\n## Khuyến mãi")
        for promo in snapshot.promotions:
            # Note: PromotionVehicle doesn't have discount info, so we'll skip this section
            # for now as it's not available in the snapshot
            pass

    # Handle battery policies section
    if snapshot.battery_policies:
        parts.append("\n## Chính sách pin")
        for bp in snapshot.battery_policies:
            parts.append(f"- {bp.ownership_model.value}: phí hàng tháng {bp.monthly_fee_vnd or 0:,} VND")

    # Handle feature flags section
    if snapshot.feature_flags:
        parts.append("\n## Tính năng")
        for flag in snapshot.feature_flags:
            parts.append(f"- {flag.name} ({flag.feature_code}): {flag.status}")

    return "\n".join(parts)


__all__ = ["VehicleCatalogService"]
