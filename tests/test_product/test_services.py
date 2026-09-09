"""Unit tests cho VehicleCatalogService — sử dụng FakeRepository (in-memory)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.products.application import (
    CatalogSnapshot,
    FeatureFlagSummary,
    PageParams,
    PricePoint,
    VehicleDetail,
    VehicleRepository,
)
from src.products.application.vehicle_service import VehicleCatalogService
from src.products.domain.entities import (
    BatteryPolicy,
    Car,
    FeatureDefinition,
    Motorbike,
    Vehicle,
)
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.values import (
    BatteryOwnershipModel,
    FeatureDefinitionStatus,
    FeatureFlagStatus,
    FeatureValueType,
    FilterBehavior,
    RecordLifecycleStatus,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeVehicleRepository(VehicleRepository):
    def __init__(self) -> None:
        self._details: dict[str, VehicleDetail] = {}
        self._by_slug: dict[str, str] = {}
        self._snapshots: dict[str, CatalogSnapshot] = {}

    # ----- write helpers -----

    def add_vehicle(self, detail: VehicleDetail, snapshot: CatalogSnapshot | None = None) -> None:
        self._details[detail.vehicle.vehicle_id] = detail
        self._by_slug[detail.vehicle.slug] = detail.vehicle.vehicle_id
        if snapshot is not None:
            self._snapshots[detail.vehicle.vehicle_id] = snapshot

    # ----- read -----

    async def get_vehicle(self, identifier: str) -> VehicleDetail | None:
        return self._details.get(identifier)

    async def get_vehicle_by_slug(self, slug: str) -> VehicleDetail | None:
        vid = self._by_slug.get(slug)
        return self._details.get(vid) if vid else None

    async def get_vehicle_by_sku(self, sku: str) -> VehicleDetail | None:
        # Assuming SKU is stored in the vehicle's slug or another field
        # For this test, we'll assume SKU is part of the slug or vehicle_id
        # This is a mock implementation for testing purposes
        for detail in self._details.values():
            if sku in detail.vehicle.slug or sku == detail.vehicle.vehicle_id:
                return detail
        return None

    async def list_vehicles(self, page, status=None, vehicle_type=None) -> list[VehicleDetail]:
        items = list(self._details.values())
        if status is not None:
            items = [d for d in items if d.vehicle.status == status]
        if vehicle_type:
            items = [d for d in items if d.vehicle.vehicle_type.value == vehicle_type.upper()]
        return items[page.skip : page.skip + page.limit]

    async def search_vehicles(self, query, page, status=None) -> list[VehicleDetail]:
        q = query.lower()
        items = [d for d in self._details.values() if q in d.vehicle.model_name.lower() or q in d.vehicle.brand.lower()]
        if status is not None:
            items = [d for d in items if d.vehicle.status == status]
        return items[page.skip : page.skip + page.limit]

    async def count_vehicles(self, status=None, vehicle_type=None) -> int:
        items = list(self._details.values())
        if status is not None:
            items = [d for d in items if d.vehicle.status == status]
        if vehicle_type:
            items = [d for d in items if d.vehicle.vehicle_type.value == vehicle_type.upper()]
        return len(items)

    async def create_vehicle(self, data: dict) -> VehicleDetail:
        now = datetime.now(UTC)
        vid = "v-new"
        v = Vehicle(
            vehicle_id=vid,
            vehicle_type=VehicleType(data.get("vehicle_type", "CAR")),
            brand=data.get("brand", ""),
            model_name=data.get("model_name", ""),
            status=VehicleStatus(data.get("status", "ACTIVE")),
            slug=data.get("slug") or f"{data.get('brand', '')}-{data.get('model_name', '')}".lower(),
            created_at=now,
            updated_at=now,
            variant_name=data.get("variant_name"),
        )
        detail = VehicleDetail(vehicle=v, specs=None, prices=[])
        self.add_vehicle(detail)
        return detail

    async def archive_vehicle(self, vehicle_id: str) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        archived = replace(detail.vehicle, status=VehicleStatus.ARCHIVED)
        updated = replace(detail, vehicle=archived)
        self._details[vehicle_id] = updated
        return updated

    async def restore_vehicle(self, vehicle_id: str) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        restored = replace(detail.vehicle, status=VehicleStatus.ACTIVE)
        updated = replace(detail, vehicle=restored)
        self._details[vehicle_id] = updated
        return updated

    async def update_vehicle(self, vehicle_id: str, data: dict) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        changes = {k: v for k, v in data.items() if v is not None}
        if "status" in changes:
            changes["status"] = VehicleStatus(changes["status"])
        if "vehicle_type" in changes:
            changes["vehicle_type"] = VehicleType(changes["vehicle_type"])
        updated_vehicle = replace(detail.vehicle, **changes)
        updated = replace(detail, vehicle=updated_vehicle)
        self._details[vehicle_id] = updated
        self._by_slug[updated_vehicle.slug] = vehicle_id
        return updated

    async def replace_vehicle_prices(self, vehicle_id: str, prices: list[dict]) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        now = datetime.now(UTC)
        expired = [
            replace(p, status=RecordLifecycleStatus.EXPIRED, valid_to=now)
            for p in detail.prices
            if p.status is RecordLifecycleStatus.ACTIVE
        ]
        kept = [p for p in detail.prices if p.status is not RecordLifecycleStatus.ACTIVE]
        added = [
            PricePoint(
                price_id=f"p-new-{index}",
                price_type=p["price_type"],
                amount_vnd=p["amount_vnd"],
                currency=p.get("currency", "VND"),
                region_code=p.get("region_code", "VN"),
                status=RecordLifecycleStatus.ACTIVE,
                valid_from=now,
            )
            for index, p in enumerate(prices)
        ]
        updated = replace(detail, prices=[*kept, *expired, *added])
        self._details[vehicle_id] = updated
        return updated

    async def update_vehicle_price(self, vehicle_id: str, price_id: str, data: dict) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        from dataclasses import replace

        new_prices = []
        found = False
        for p in detail.prices:
            if p.price_id == price_id:
                found = True
                new_p = replace(
                    p,
                    amount_vnd=data.get("amount_vnd", p.amount_vnd),
                    price_type=data.get("price_type", p.price_type),
                )
                new_prices.append(new_p)
            else:
                new_prices.append(p)
        if not found:
            return None
        updated_detail = VehicleDetail(
            vehicle=detail.vehicle,
            specs=detail.specs,
            prices=new_prices,
            promotions=detail.promotions,
            battery_policies=detail.battery_policies,
            feature_flags=detail.feature_flags,
        )
        self._details[vehicle_id] = updated_detail
        return updated_detail

    async def update_vehicle_specs(self, vehicle_id: str, data: dict) -> VehicleDetail | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        from dataclasses import replace

        specs_dict = data.get("specs", data) if isinstance(data, dict) else data
        if detail.specs is not None:
            updated_specs = replace(detail.specs, **{k: v for k, v in specs_dict.items() if hasattr(detail.specs, k)})
            updated_detail = VehicleDetail(
                vehicle=detail.vehicle,
                specs=updated_specs,
                prices=detail.prices,
                promotions=detail.promotions,
                battery_policies=detail.battery_policies,
                feature_flags=detail.feature_flags,
            )
            self._details[vehicle_id] = updated_detail
            return updated_detail
        return None

    async def update_feature_flag(self, vehicle_id: str, feature_code: str, data: dict) -> FeatureFlagSummary | None:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return None
        from dataclasses import replace

        new_flags = []
        updated_summary = None
        for f in detail.feature_flags:
            if f.feature_code == feature_code:
                updated_summary = replace(
                    f,
                    status=data.get("status", f.status),
                    verification_status=data.get("verification_status", f.verification_status),
                    value_text=data.get("value_text", f.value_text),
                    value_number=data.get("value_number", f.value_number),
                    value_boolean=data.get("value_boolean", f.value_boolean),
                )
                new_flags.append(updated_summary)
            else:
                new_flags.append(f)
        if updated_summary is None:
            return None
        self._details[vehicle_id] = VehicleDetail(
            vehicle=detail.vehicle,
            specs=detail.specs,
            prices=detail.prices,
            promotions=detail.promotions,
            battery_policies=detail.battery_policies,
            feature_flags=new_flags,
        )
        return updated_summary

    async def delete_vehicle(self, vehicle_id: str) -> bool:
        detail = self._details.get(vehicle_id)
        if detail is None:
            return False
        from dataclasses import replace

        updated_v = replace(detail.vehicle, status=VehicleStatus.ARCHIVED)
        self._details[vehicle_id] = VehicleDetail(
            vehicle=updated_v,
            specs=detail.specs,
            prices=detail.prices,
            promotions=detail.promotions,
            battery_policies=detail.battery_policies,
            feature_flags=detail.feature_flags,
        )
        return True

    async def get_rag_snapshot(self, identifier: str) -> CatalogSnapshot | None:
        detail = self._details.get(identifier) or self._details.get(self._by_slug.get(identifier, ""))
        if detail is None:
            return None
        return self._snapshots.get(detail.vehicle.vehicle_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _car_detail(vehicle_id: str = "v-car-1") -> VehicleDetail:
    v = Vehicle(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.CAR,
        brand="VinFast",
        model_name="VF 8",
        status=VehicleStatus.ACTIVE,
        slug="vinfast-vf-8",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    c = Car(
        vehicle_id=vehicle_id,
        specs_version=1,
        created_at=v.created_at,
        updated_at=v.updated_at,
        body_type="SUV",
        range_km=Decimal("500.0"),
        battery_capacity_kwh=Decimal("87.7"),
    )
    return VehicleDetail(
        vehicle=v,
        specs=c,
        prices=[
            PricePoint(
                price_id="p1",
                price_type="STARTING_PRICE",
                amount_vnd=854050000,
                currency="VND",
                region_code="VN",
                status=RecordLifecycleStatus.ACTIVE,
                valid_from=v.created_at,
            )
        ],
        battery_policies=[
            BatteryPolicy(
                battery_policy_id="bp1",
                vehicle_id=vehicle_id,
                ownership_model=BatteryOwnershipModel.INCLUDED,
                status=RecordLifecycleStatus.ACTIVE,
                valid_from=v.created_at,
                version=1,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
        ],
        feature_flags=[
            FeatureFlagSummary(
                feature_code="GPS",
                name="GPS",
                status=FeatureFlagStatus.YES.value,
                verification_status=VerificationStatus.APPROVED.value,
                value_boolean=True,
            )
        ],
    )


def _motorbike_detail(vehicle_id: str = "v-mb-1") -> VehicleDetail:
    v = Vehicle(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        brand="VinFast",
        model_name="Klara S",
        status=VehicleStatus.ACTIVE,
        slug="vinfast-klara-s",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    m = Motorbike(
        vehicle_id=vehicle_id,
        specs_version=1,
        created_at=v.created_at,
        updated_at=v.updated_at,
        motor_power_w=1800,
        max_speed_kmh=Decimal("78"),
        range_min_km=Decimal("194"),
        range_max_km=Decimal("194"),
    )
    return VehicleDetail(vehicle=v, specs=m, prices=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_active_vehicles_filters_by_status() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail("v-active"))
    draft = VehicleDetail(
        vehicle=Vehicle(
            vehicle_id="v-draft",
            vehicle_type=VehicleType.CAR,
            brand="VinFast",
            model_name="VF 9 Draft",
            status=VehicleStatus.DRAFT,
            slug="vf-9-draft",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        specs=None,
        prices=[],
    )
    repo.add_vehicle(draft)

    svc = VehicleCatalogService(repo)
    items = await svc.list_active_vehicles(PageParams(skip=0, limit=10))
    assert [d.vehicle.vehicle_id for d in items] == ["v-active"]
    assert await svc.count_active_vehicles() == 1


@pytest.mark.asyncio
async def test_list_active_vehicles_filters_by_vehicle_type() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    repo.add_vehicle(_motorbike_detail())
    svc = VehicleCatalogService(repo)

    cars = await svc.list_active_vehicles(PageParams(0, 10), vehicle_type="CAR")
    assert len(cars) == 1
    assert cars[0].vehicle.vehicle_type == VehicleType.CAR

    bikes = await svc.list_active_vehicles(PageParams(0, 10), vehicle_type="ELECTRIC_MOTORBIKE")
    assert len(bikes) == 1


@pytest.mark.asyncio
async def test_get_vehicle_detail_by_id() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    detail = await svc.get_vehicle_detail("v-car-1")
    assert detail.vehicle.vehicle_id == "v-car-1"
    assert isinstance(detail.specs, Car)
    assert detail.specs.body_type == "SUV"


@pytest.mark.asyncio
async def test_get_vehicle_detail_by_slug() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    detail = await svc.get_vehicle_detail("vinfast-vf-8")
    assert detail.vehicle.vehicle_id == "v-car-1"


@pytest.mark.asyncio
async def test_get_vehicle_detail_inactive_raises() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(
        VehicleDetail(
            vehicle=Vehicle(
                vehicle_id="v-inactive",
                vehicle_type=VehicleType.CAR,
                brand="X",
                model_name="Y",
                status=VehicleStatus.INACTIVE,
                slug="x-y",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            specs=None,
            prices=[],
        )
    )
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductNotFoundError):
        await svc.get_vehicle_detail("v-inactive")


@pytest.mark.asyncio
async def test_get_vehicle_detail_missing_raises() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductNotFoundError):
        await svc.get_vehicle_detail("does-not-exist")


@pytest.mark.asyncio
async def test_search_vehicles_by_query() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    repo.add_vehicle(_motorbike_detail())
    svc = VehicleCatalogService(repo)
    res = await svc.search_vehicles("Klara", PageParams(0, 10))
    assert len(res) == 1
    assert res[0].vehicle.model_name == "Klara S"


@pytest.mark.asyncio
async def test_admin_create_vehicle_succeeds() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    detail = await svc.create_vehicle({"brand": "VinFast", "model_name": "VF 7", "vehicle_type": "CAR"}, is_admin=True)
    assert detail.vehicle.brand == "VinFast"


@pytest.mark.asyncio
async def test_admin_create_vehicle_requires_admin() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductPermissionError):
        await svc.create_vehicle({"brand": "X", "model_name": "Y"}, is_admin=False)


@pytest.mark.asyncio
async def test_admin_list_requires_admin() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductPermissionError):
        await svc.list_admin_vehicles(PageParams(0, 10), is_admin=False)


@pytest.mark.asyncio
async def test_admin_list_with_invalid_status_raises() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductPermissionError):
        await svc.list_admin_vehicles(PageParams(0, 10), status="INVALID", is_admin=True)


@pytest.mark.asyncio
async def test_admin_delete_succeeds() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    await svc.archive_vehicle("v-car-1", is_admin=True)
    assert repo._details["v-car-1"].vehicle.status == VehicleStatus.ARCHIVED
    with pytest.raises(ProductNotFoundError):
        await svc.get_vehicle_detail("v-car-1")


@pytest.mark.asyncio
async def test_admin_delete_vehicle_soft_archives() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    await svc.delete_vehicle("v-car-1", is_admin=True)
    assert repo._details["v-car-1"].vehicle.status == VehicleStatus.ARCHIVED
    with pytest.raises(ProductNotFoundError):
        await svc.get_vehicle_detail("v-car-1")


@pytest.mark.asyncio
async def test_admin_delete_missing_raises() -> None:
    repo = FakeVehicleRepository()
    svc = VehicleCatalogService(repo)
    with pytest.raises(ProductNotFoundError):
        await svc.archive_vehicle("missing", is_admin=True)


@pytest.mark.asyncio
async def test_rag_context_render() -> None:
    repo = FakeVehicleRepository()
    detail = _car_detail()
    definitions = [
        FeatureDefinition(
            feature_code="GPS",
            name="GPS",
            category="SMART_FEATURE",
            value_type=FeatureValueType.BOOLEAN,
            filter_behavior=FilterBehavior.PREFERENCE,
            status=FeatureDefinitionStatus.ACTIVE,
            display_order=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    ]
    snapshot = CatalogSnapshot(
        vehicle=detail.vehicle,
        specs=detail.specs,
        prices=detail.prices,
        promotions=[],
        battery_policies=detail.battery_policies,
        feature_flags=detail.feature_flags,
        feature_definitions=definitions,
    )
    repo.add_vehicle(detail, snapshot)
    svc = VehicleCatalogService(repo)
    ctx = await svc.get_vehicle_rag_context("v-car-1")
    assert "VinFast VF 8" in ctx
    assert "500" in ctx  # range_km
    assert "GPS" in ctx


@pytest.mark.asyncio
async def test_admin_update_vehicle_succeeds() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    detail = await svc.update_vehicle("v-car-1", {"model_name": "VF 8 Plus"}, is_admin=True)
    assert detail.vehicle.model_name == "VF 8 Plus"


@pytest.mark.asyncio
async def test_admin_update_vehicle_price_succeeds() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    detail = await svc.update_vehicle_price("v-car-1", "p1", {"amount_vnd": 900000000}, is_admin=True)
    assert detail.prices[0].amount_vnd == 900000000


@pytest.mark.asyncio
async def test_admin_update_vehicle_specs_succeeds() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    detail = await svc.update_vehicle_specs("v-car-1", {"body_type": "Crossover"}, is_admin=True)
    assert detail.specs.body_type == "Crossover"


@pytest.mark.asyncio
async def test_admin_review_feature_flag_succeeds() -> None:
    repo = FakeVehicleRepository()
    repo.add_vehicle(_car_detail())
    svc = VehicleCatalogService(repo)
    flag = await svc.review_feature_flag("v-car-1", "GPS", {"verification_status": "APPROVED"}, is_admin=True)
    assert flag.verification_status == "APPROVED"
