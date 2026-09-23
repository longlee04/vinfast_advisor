"""SQLAlchemy repository implementations cho Vehicle Catalog module.

Bám sát schema định nghĩa tại
``migrations/products/versions/d4e5f6a7b8c9_product_schema.py``. Trả về DTO
``VehicleDetail`` / ``CatalogSnapshot`` (application layer) thay vì ORM row.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.products.application import (
    CatalogSnapshot,
    FeatureFlagDetail,
    FeatureFlagRepository,
    FeatureFlagSummary,
    PageParams,
    PricePoint,
    VehicleDetail,
    VehicleRepository,
)
from src.products.domain.entities import (
    BatteryPolicy,
    Car,
    FeatureDefinition,
    Motorbike,
    Promotion,
    PromotionVehicle,
    Vehicle,
    VehicleShowcaseItem,
)
from src.products.domain.errors import ProductNotFoundError
from src.products.domain.offer_policy import OfferAdjustmentPolicy
from src.products.domain.values import (
    BatteryOwnershipModel,
    FeatureDefinitionStatus,
    PromotionType,
    RecordLifecycleStatus,
    VehicleStatus,
    VehicleType,
)
from src.products.infrastructure.models import (
    BatteryPolicyRow,
    CarSpecRow,
    FeatureDefinitionRow,
    MotorbikeSpecRow,
    OfferAdjustmentPolicyRow,
    PromotionRow,
    PromotionVehicleRow,
    TcoAssumptionRow,
    VehicleFeatureFlagRow,
    VehiclePriceRow,
    VehicleRow,
    VehicleShowcaseItemRow,
)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _to_car(row: CarSpecRow) -> Car:
    return Car(
        vehicle_id=row.vehicle_id,
        specs_version=row.specs_version,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
        updated_at=_utc(row.updated_at) if hasattr(row, "updated_at") else datetime.now(UTC),
        body_type=row.body_type,
        seat_count=row.seat_count,
        range_km=row.range_km,
        range_cycle=row.range_cycle,
        energy_consumption_kwh_per_100km=row.energy_consumption_kwh_per_100km,
        battery_capacity_kwh=row.battery_capacity_kwh,
        motor_power_kw=row.motor_power_kw,
        torque_nm=row.torque_nm,
        max_speed_kmh=row.max_speed_kmh,
        acceleration_0_100_seconds=row.acceleration_0_100_seconds,
        curb_weight_kg=row.curb_weight_kg,
        gross_weight_kg=row.gross_weight_kg,
        fast_charge_power_kw=row.fast_charge_power_kw,
        fast_charge_time_minutes=row.fast_charge_time_minutes,
        fast_charge_from_percent=row.fast_charge_from_percent,
        fast_charge_to_percent=row.fast_charge_to_percent,
        home_charge_time_minutes=row.home_charge_time_minutes,
        charging_port=row.charging_port,
        cargo_volume_standard_l=row.cargo_volume_standard_l,
        cargo_volume_maximum_l=row.cargo_volume_maximum_l,
        towing_supported=row.towing_supported,
        towing_capacity_kg=row.towing_capacity_kg,
        effective_from=_utc(row.effective_from) if hasattr(row, "effective_from") else None,
        effective_to=_utc(row.effective_to) if hasattr(row, "effective_to") else None,
    )


def _to_motorbike(row: MotorbikeSpecRow) -> Motorbike:
    return Motorbike(
        vehicle_id=row.vehicle_id,
        specs_version=row.specs_version,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
        updated_at=_utc(row.updated_at) if hasattr(row, "updated_at") else datetime.now(UTC),
        motor_power_w=row.motor_power_w,
        max_power_w=row.max_power_w,
        torque_nm=row.torque_nm,
        max_speed_kmh=row.max_speed_kmh,
        battery_type=row.battery_type,
        battery_capacity_kwh=row.battery_capacity_kwh,
        battery_quantity=row.battery_quantity,
        battery_removable=row.battery_removable,
        battery_swappable=row.battery_swappable,
        energy_consumption_kwh_per_100km=row.energy_consumption_kwh_per_100km,
        range_min_km=row.range_min_km,
        range_max_km=row.range_max_km,
        range_cycle=row.range_cycle,
        charging_time_minutes=row.charging_time_minutes,
        charging_method=row.charging_method,
        curb_weight_kg=row.curb_weight_kg,
        max_load_kg=row.max_load_kg,
        seat_height_mm=row.seat_height_mm,
        wheel_size_front_inch=row.wheel_size_front_inch,
        wheel_size_rear_inch=row.wheel_size_rear_inch,
        license_requirement=None,
        effective_from=_utc(row.effective_from) if hasattr(row, "effective_from") else None,
        effective_to=_utc(row.effective_to) if hasattr(row, "effective_to") else None,
    )


def _to_price_point(row: VehiclePriceRow) -> PricePoint:
    return PricePoint(
        price_id=row.price_id,
        price_type=row.price_type,
        amount_vnd=row.amount_vnd,
        currency=row.currency,
        region_code=row.region_code,
        status=RecordLifecycleStatus(row.status),
        valid_from=_utc(row.valid_from) if hasattr(row, "valid_from") else datetime.now(UTC),
        valid_to=_utc(row.valid_to) if hasattr(row, "valid_to") else None,
    )


def _to_feature_flag_summary(row: VehicleFeatureFlagRow, definition: FeatureDefinitionRow | None) -> FeatureFlagSummary:
    return FeatureFlagSummary(
        feature_code=row.feature_code,
        name=definition.name if definition else row.feature_code,
        status=row.status,
        verification_status=row.verification_status,
        value_text=row.value_text,
        value_number=row.value_number,
        value_boolean=row.value_boolean,
    )


def _to_battery_policy(row: BatteryPolicyRow) -> BatteryPolicy:
    return BatteryPolicy(
        battery_policy_id=row.battery_policy_id,
        vehicle_id=row.vehicle_id,
        ownership_model=BatteryOwnershipModel(row.ownership_model),
        status=RecordLifecycleStatus(row.status),
        valid_from=_utc(row.valid_from) if hasattr(row, "valid_from") else datetime.now(UTC),
        version=row.version,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
        updated_at=_utc(row.updated_at) if hasattr(row, "updated_at") else datetime.now(UTC),
        monthly_fee_vnd=row.monthly_fee_vnd,
        purchase_price_vnd=row.purchase_price_vnd,
        included_distance_km=row.included_distance_km,
        excess_fee_per_km_vnd=row.excess_fee_per_km_vnd,
        deposit_amount_vnd=row.deposit_amount_vnd,
        warranty_months=row.warranty_months,
        warranty_distance_km=row.warranty_distance_km,
        valid_to=_utc(row.valid_to) if hasattr(row, "valid_to") else None,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _to_promotion_link(row: PromotionVehicleRow) -> PromotionVehicle:
    return PromotionVehicle(
        promotion_id=row.promotion_id,
        vehicle_id=row.vehicle_id,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
    )


def _to_vehicle(row: VehicleRow) -> Vehicle:
    return Vehicle(
        vehicle_id=row.vehicle_id,
        vehicle_type=VehicleType(row.vehicle_type),
        brand=row.brand,
        model_name=row.model_name,
        status=VehicleStatus(row.status),
        slug=row.slug,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
        updated_at=_utc(row.updated_at) if hasattr(row, "updated_at") else datetime.now(UTC),
        variant_name=row.variant_name,
        model_year=row.model_year,
        image_url=row.image_url,
        detail_url=row.detail_url,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _to_showcase_item(row: VehicleShowcaseItemRow) -> VehicleShowcaseItem:
    return VehicleShowcaseItem(
        showcase_item_id=row.showcase_item_id,
        vehicle_id=row.vehicle_id,
        section_key=row.section_key,
        item_key=row.item_key,
        title=row.title,
        description=row.description,
        media_url=row.media_url,
        media_alt=row.media_alt,
        display_order=row.display_order,
        source_url=row.source_url,
        source_retrieved_at=_utc(row.source_retrieved_at) or datetime.now(UTC),
        status=row.status,
        created_at=_utc(row.created_at) or datetime.now(UTC),
        updated_at=_utc(row.updated_at) or datetime.now(UTC),
    )


def _to_feature_definition(row: FeatureDefinitionRow) -> FeatureDefinition:
    return FeatureDefinition(
        feature_code=row.feature_code,
        name=row.name,
        category=row.category,
        value_type=row.value_type,  # type: ignore[arg-type]
        filter_behavior=row.filter_behavior,  # type: ignore[arg-type]
        status=FeatureDefinitionStatus(row.status),
        display_order=row.display_order,
        created_at=_utc(row.created_at) if hasattr(row, "created_at") else datetime.now(UTC),
        updated_at=_utc(row.updated_at) if hasattr(row, "updated_at") else datetime.now(UTC),
        description=row.description,
        vehicle_type=VehicleType(row.vehicle_type) if row.vehicle_type else None,
        unit=row.unit,
        allowed_values=list(row.allowed_values) if row.allowed_values else None,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _to_promotion(row: PromotionRow) -> Promotion:
    return Promotion(
        promotion_id=row.promotion_id,
        promotion_code=row.promotion_code,
        title=row.title,
        promotion_type=PromotionType(row.promotion_type),
        region_code=row.region_code,
        eligibility_rules=dict(row.eligibility_rules or {}),
        status=RecordLifecycleStatus(row.status),
        valid_from=_utc(row.valid_from),  # type: ignore[arg-type]
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
        description=row.description,
        discount_amount_vnd=row.discount_amount_vnd,
        discount_percent=row.discount_percent,
        valid_to=_utc(row.valid_to),
        created_by=row.created_by,
        approved_by=row.approved_by,
        approved_at=_utc(row.approved_at),
        gift_group=row.gift_group,
    )


def _build_detail(row: VehicleRow) -> VehicleDetail:
    specs: Car | Motorbike | None = None
    if row.car is not None:
        specs = _to_car(row.car)
    elif row.motorbike is not None:
        specs = _to_motorbike(row.motorbike)

    # Ensure prices list is not None
    prices = [_to_price_point(p) for p in (row.prices or [])]

    # Ensure battery_policies list is not None
    battery_policies = [_to_battery_policy(b) for b in (row.battery_policies or [])]

    # Ensure promotions list is not None
    promotions = [_to_promotion_link(p) for p in (row.promotion_links or [])]

    # Ensure feature_flags list is not None
    feature_flags = []
    if row.feature_flags:
        feature_flags = [_to_feature_flag_summary(f, getattr(f, "feature_def", None)) for f in row.feature_flags]

    showcase_items = sorted(
        (_to_showcase_item(item) for item in (row.showcase_items or []) if item.status == "ACTIVE"),
        key=lambda item: (item.section_key, item.display_order, item.item_key),
    )

    return VehicleDetail(
        vehicle=_to_vehicle(row),
        specs=specs,
        prices=prices,
        battery_policies=battery_policies,
        promotions=promotions,
        feature_flags=feature_flags,
        showcase_items=showcase_items,
    )


class SqlAlchemyVehicleRepository(VehicleRepository):
    """Refactored Repository querying unified Vehicle Registry and child tables."""

    # vehicle_type KHONG duoc PATCH: doi CAR <-> ELECTRIC_MOTORBIKE se lam mo côi
    # hang con cars/motorbikes (_build_detail chon specs theo hang con dang co,
    # khong theo vehicle_type) — can migration path rieng, ngoai pham vi PATCH nay.
    _UPDATABLE_COLUMNS = frozenset(
        {
            "brand",
            "model_name",
            "variant_name",
            "model_year",
            "slug",
            "status",
            "image_url",
            "detail_url",
        }
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_query(self):
        return select(VehicleRow).options(
            selectinload(VehicleRow.car),
            selectinload(VehicleRow.motorbike),
            selectinload(VehicleRow.prices),
            selectinload(VehicleRow.battery_policies),
            selectinload(VehicleRow.feature_flags).selectinload(VehicleFeatureFlagRow.feature_def),
            selectinload(VehicleRow.promotion_links),
            selectinload(VehicleRow.showcase_items),
        )

    async def get_vehicle(self, identifier: str) -> VehicleDetail | None:
        try:
            res = (
                await self._session.execute(self._base_query().where(VehicleRow.vehicle_id == str(identifier)))
            ).scalar_one_or_none()
            return _build_detail(res) if res else None
        except Exception as e:
            # Log the error and return None to avoid breaking the application
            print(f"Error getting vehicle by ID {identifier}: {e}")
            return None

    async def get_vehicle_by_slug(self, slug: str) -> VehicleDetail | None:
        try:
            stmt = self._base_query().where(func.lower(VehicleRow.slug) == slug.strip().lower())
            res = (await self._session.execute(stmt)).scalar_one_or_none()
            return _build_detail(res) if res else None
        except Exception as e:
            # Log the error and return None to avoid breaking the application
            print(f"Error getting vehicle by slug {slug}: {e}")
            return None

    async def get_vehicle_by_sku(self, sku: str) -> VehicleDetail | None:
        try:
            stmt = self._base_query().where(func.lower(VehicleRow.sku) == sku.strip().lower())
            res = (await self._session.execute(stmt)).scalar_one_or_none()
            return _build_detail(res) if res else None
        except Exception as e:
            # Log the error and return None to avoid breaking the application
            print(f"Error getting vehicle by SKU {sku}: {e}")
            return None

    async def list_vehicles(
        self,
        page: PageParams,
        status: VehicleStatus | None = None,
        vehicle_type: str | None = None,
    ) -> list[VehicleDetail]:
        try:
            stmt = self._base_query()
            if status is not None:
                stmt = stmt.where(VehicleRow.status == status.value)
            if vehicle_type:
                stmt = stmt.where(VehicleRow.vehicle_type == vehicle_type.upper())
            stmt = stmt.order_by(VehicleRow.brand, VehicleRow.model_name).offset(page.skip).limit(page.limit)
            rows = (await self._session.execute(stmt)).scalars().all()
            return [_build_detail(r) for r in rows]
        except Exception as e:
            # Log the error and return empty list to avoid breaking the application
            print(f"Error listing vehicles: {e}")
            return []

    async def search_vehicles(
        self,
        query: str,
        page: PageParams,
        status: VehicleStatus | None = None,
    ) -> list[VehicleDetail]:
        try:
            q = f"%{query.strip().lower()}%"
            stmt = self._base_query().where(
                or_(
                    func.lower(VehicleRow.brand).like(q),
                    func.lower(VehicleRow.model_name).like(q),
                    func.lower(func.coalesce(VehicleRow.variant_name, "")).like(q),
                )
            )
            if status is not None:
                stmt = stmt.where(VehicleRow.status == status.value)
            stmt = stmt.offset(page.skip).limit(page.limit)
            rows = (await self._session.execute(stmt)).scalars().all()
            return [_build_detail(r) for r in rows]
        except Exception as e:
            # Log the error and return empty list to avoid breaking the application
            print(f"Error searching vehicles for query '{query}': {e}")
            return []

    async def count_vehicles(
        self,
        status: VehicleStatus | None = None,
        vehicle_type: str | None = None,
    ) -> int:
        try:
            stmt = select(func.count()).select_from(VehicleRow)
            if status is not None:
                stmt = stmt.where(VehicleRow.status == status.value)
            if vehicle_type:
                stmt = stmt.where(VehicleRow.vehicle_type == vehicle_type.upper())
            return int((await self._session.execute(stmt)).scalar_one())
        except Exception as e:
            # Log the error and return 0 to avoid breaking the application
            print(f"Error counting vehicles: {e}")
            return 0

    async def create_vehicle(self, data: dict) -> VehicleDetail:
        try:
            brand = (data.get("brand") or "").strip()
            model_name = (data.get("model_name") or "").strip()
            variant_name = (data.get("variant_name") or "").strip() or None
            vehicle_type_raw = (data.get("vehicle_type") or "CAR").strip().upper()
            try:
                vehicle_type = VehicleType(vehicle_type_raw)
            except ValueError as exc:
                raise ValueError(f"vehicle_type không hợp lệ: {vehicle_type_raw}") from exc
            try:
                status = VehicleStatus((data.get("status") or "ACTIVE").strip().upper())
            except ValueError:
                status = VehicleStatus.ACTIVE
            model_year_raw = data.get("model_year")
            try:
                model_year = int(model_year_raw) if model_year_raw is not None else None
            except (TypeError, ValueError):
                model_year = None
            slug = data.get("slug") or re.sub(
                r"[-\s]+",
                "-",
                re.sub(r"[^\w\s-]", "", f"{brand}-{model_name}-{variant_name or ''}".lower().strip()),
            ).strip("-")
            # avoid slug collision
            base_slug = slug
            counter = 1
            while True:
                existing = (
                    await self._session.execute(select(VehicleRow).where(VehicleRow.slug == slug))
                ).scalar_one_or_none()
                if existing is None:
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1

            vehicle_id = str(uuid4())
            v_row = VehicleRow(
                vehicle_id=vehicle_id,
                vehicle_type=vehicle_type.value,
                brand=brand,
                model_name=model_name,
                variant_name=variant_name,
                model_year=model_year,
                status=status.value,
                slug=slug,
                image_url=data.get("image_url"),
                detail_url=data.get("detail_url"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self._session.add(v_row)
            await self._session.flush()

            specs = data.get("specs") or {}
            if vehicle_type is VehicleType.CAR:
                car = CarSpecRow(
                    vehicle_id=vehicle_id,
                    body_type=specs.get("body_type"),
                    seat_count=specs.get("seat_count"),
                    range_km=specs.get("range_km"),
                    range_cycle=specs.get("range_cycle"),
                    energy_consumption_kwh_per_100km=specs.get("energy_consumption_kwh_per_100km"),
                    battery_capacity_kwh=specs.get("battery_capacity_kwh"),
                    motor_power_kw=specs.get("motor_power_kw"),
                    torque_nm=specs.get("torque_nm"),
                    max_speed_kmh=specs.get("max_speed_kmh"),
                    acceleration_0_100_seconds=specs.get("acceleration_0_100_seconds"),
                    curb_weight_kg=specs.get("curb_weight_kg"),
                    gross_weight_kg=specs.get("gross_weight_kg"),
                    fast_charge_power_kw=specs.get("fast_charge_power_kw"),
                    fast_charge_time_minutes=specs.get("fast_charge_time_minutes"),
                    fast_charge_from_percent=specs.get("fast_charge_from_percent"),
                    fast_charge_to_percent=specs.get("fast_charge_to_percent"),
                    home_charge_time_minutes=specs.get("home_charge_time_minutes"),
                    charging_port=specs.get("charging_port"),
                    cargo_volume_standard_l=specs.get("cargo_volume_standard_l"),
                    cargo_volume_maximum_l=specs.get("cargo_volume_maximum_l"),
                    towing_supported=specs.get("towing_supported"),
                    towing_capacity_kg=specs.get("towing_capacity_kg"),
                    specs_version=1,
                    effective_from=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                self._session.add(car)
            elif vehicle_type is VehicleType.ELECTRIC_MOTORBIKE:
                mb = MotorbikeSpecRow(
                    vehicle_id=vehicle_id,
                    motor_power_w=specs.get("motor_power_w"),
                    max_power_w=specs.get("max_power_w"),
                    torque_nm=specs.get("torque_nm"),
                    max_speed_kmh=specs.get("max_speed_kmh"),
                    battery_type=specs.get("battery_type"),
                    battery_capacity_kwh=specs.get("battery_capacity_kwh"),
                    battery_quantity=specs.get("battery_quantity"),
                    battery_removable=specs.get("battery_removable"),
                    battery_swappable=specs.get("battery_swappable"),
                    energy_consumption_kwh_per_100km=specs.get("energy_consumption_kwh_per_100km"),
                    range_min_km=specs.get("range_min_km"),
                    range_max_km=specs.get("range_max_km"),
                    range_cycle=specs.get("range_cycle"),
                    charging_time_minutes=specs.get("charging_time_minutes"),
                    charging_method=specs.get("charging_method"),
                    curb_weight_kg=specs.get("curb_weight_kg"),
                    max_load_kg=specs.get("max_load_kg"),
                    seat_height_mm=specs.get("seat_height_mm"),
                    wheel_size_front_inch=specs.get("wheel_size_front_inch"),
                    wheel_size_rear_inch=specs.get("wheel_size_rear_inch"),
                    specs_version=1,
                    effective_from=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                self._session.add(mb)

            for price in data.get("prices") or []:
                self._session.add(
                    VehiclePriceRow(
                        price_id=str(uuid4()),
                        vehicle_id=vehicle_id,
                        price_type=price.get("price_type") or "STARTING_PRICE",
                        amount_vnd=int(price.get("amount_vnd") or price.get("amount") or 0),
                        currency=price.get("currency") or "VND",
                        region_code=price.get("region_code") or "VN",
                        status=price.get("status") or "ACTIVE",
                        valid_from=datetime.now(UTC),
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )

            await self._session.flush()
            refreshed = (
                await self._session.execute(self._base_query().where(VehicleRow.vehicle_id == vehicle_id))
            ).scalar_one()
            return _build_detail(refreshed)
        except Exception as e:
            # Log the error and re-raise to ensure proper error handling
            print(f"Error creating vehicle: {e}")
            raise

    async def _get_row_with_relations(self, vehicle_id: str) -> VehicleRow | None:
        """Doc mot VehicleRow kem het cac quan he can cho _build_detail.

        Dung truoc khi ghi de get_vehicle() (wrap try/except nuot loi) de tranh
        mot ghi thanh cong bi bao 404 gia neu buoc doc lai gap loi thoang qua.
        """
        return (
            await self._session.execute(self._base_query().where(VehicleRow.vehicle_id == str(vehicle_id)))
        ).scalar_one_or_none()

    async def archive_vehicle(self, vehicle_id: str) -> VehicleDetail | None:
        v = await self._get_row_with_relations(str(vehicle_id))
        if v is None:
            return None
        v.status = VehicleStatus.ARCHIVED.value
        v.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _build_detail(v)

    async def update_vehicle_price(self, vehicle_id: str, price_id: str, data: dict) -> VehicleDetail | None:
        p = await self._session.get(VehiclePriceRow, price_id)
        if not p or p.vehicle_id != vehicle_id:
            return None
        updatable_fields = ["price_type", "amount_vnd", "currency", "region_code", "status", "valid_from", "valid_to"]
        for k in updatable_fields:
            if k in data and data[k] is not None:
                setattr(p, k, data[k])
        p.updated_at = datetime.now(UTC)
        await self._session.flush()
        return await self.get_vehicle(vehicle_id)

    async def update_vehicle_specs(self, vehicle_id: str, data: dict) -> VehicleDetail | None:
        car = await self._session.get(CarSpecRow, vehicle_id)
        specs_dict = data.get("specs", data) if isinstance(data, dict) else data
        if car:
            for k, val in specs_dict.items():
                if hasattr(car, k) and val is not None and k not in ("vehicle_id", "specs_version", "created_at"):
                    setattr(car, k, val)
            car.specs_version = (car.specs_version or 1) + 1
            car.updated_at = datetime.now(UTC)
            await self._session.flush()
            return await self.get_vehicle(vehicle_id)

        mb = await self._session.get(MotorbikeSpecRow, vehicle_id)
        if mb:
            for k, val in specs_dict.items():
                if hasattr(mb, k) and val is not None and k not in ("vehicle_id", "specs_version", "created_at"):
                    setattr(mb, k, val)
            mb.specs_version = (mb.specs_version or 1) + 1
            mb.updated_at = datetime.now(UTC)
            await self._session.flush()
            return await self.get_vehicle(vehicle_id)

        return None

    async def update_feature_flag(self, vehicle_id: str, feature_code: str, data: dict) -> FeatureFlagSummary | None:
        flag = await self._session.get(VehicleFeatureFlagRow, (vehicle_id, feature_code))
        if not flag:
            return None
        updatable_fields = [
            "status",
            "verification_status",
            "value_text",
            "value_number",
            "value_boolean",
            "confidence",
            "updated_by",
        ]
        for k in updatable_fields:
            if k in data and data[k] is not None:
                setattr(flag, k, data[k])
        flag.updated_at = datetime.now(UTC)
        await self._session.flush()

        feature_def = await self._session.get(FeatureDefinitionRow, feature_code)
        name = feature_def.name if feature_def else feature_code

        return FeatureFlagSummary(
            feature_code=flag.feature_code,
            name=name,
            status=flag.status,
            verification_status=flag.verification_status,
            value_text=flag.value_text,
            value_number=flag.value_number,
            value_boolean=flag.value_boolean,
        )

    async def delete_vehicle(self, vehicle_id: str) -> bool:
        """Soft delete — chuyen sang ARCHIVED, khong xoa hang (§6.5 schema doc)."""
        v = await self._session.get(VehicleRow, str(vehicle_id))
        if v is None:
            return False
        v.status = VehicleStatus.ARCHIVED.value
        v.updated_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def restore_vehicle(self, vehicle_id: str) -> VehicleDetail | None:
        v = await self._get_row_with_relations(str(vehicle_id))
        if v is None:
            return None
        v.status = VehicleStatus.ACTIVE.value
        v.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _build_detail(v)

    async def update_vehicle(self, vehicle_id: str, data: dict) -> VehicleDetail | None:
        v = await self._get_row_with_relations(str(vehicle_id))
        if v is None:
            return None
        for key, value in data.items():
            if key not in self._UPDATABLE_COLUMNS or value is None:
                continue
            if key == "status":
                value = str(value).strip().upper()
            if key == "slug":
                conflict = (
                    await self._session.execute(
                        select(VehicleRow.vehicle_id).where(
                            VehicleRow.slug == value,
                            VehicleRow.vehicle_id != str(vehicle_id),
                        )
                    )
                ).scalar_one_or_none()
                if conflict is not None:
                    raise ValueError(f"slug đã được sử dụng bởi xe khác: {value}")
            setattr(v, key, value)
        v.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _build_detail(v)

    async def replace_vehicle_prices(self, vehicle_id: str, prices: list[dict]) -> VehicleDetail | None:
        v = await self._get_row_with_relations(str(vehicle_id))
        if v is None:
            return None
        now = datetime.now(UTC)

        # Dong moi gia dang ACTIVE thay vi xoa — giu lich su cho audit/snapshot.
        await self._session.execute(
            update(VehiclePriceRow)
            .where(
                VehiclePriceRow.vehicle_id == str(vehicle_id),
                VehiclePriceRow.status == RecordLifecycleStatus.ACTIVE.value,
            )
            .values(status=RecordLifecycleStatus.EXPIRED.value, valid_to=now, updated_at=now)
        )

        for entry in prices:
            # append() vao quan he (khong session.add() tho) de cascade insert
            # va giu v.prices dong bo trong bo nho.
            v.prices.append(
                VehiclePriceRow(
                    price_id=str(uuid4()),
                    vehicle_id=str(vehicle_id),
                    price_type=str(entry["price_type"]).strip().upper(),
                    amount_vnd=int(entry["amount_vnd"]),
                    currency=str(entry.get("currency", "VND")).strip().upper(),
                    region_code=str(entry.get("region_code", "VN")).strip().upper(),
                    status=RecordLifecycleStatus.ACTIVE.value,
                    valid_from=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._session.flush()
        # Bulk UPDATE o tren di thang qua DB, khong qua identity map, nen cac
        # gia cu (vua chuyen EXPIRED) trong v.prices dang bi stale — nap lai
        # dung quan he "prices" thay vi truy van lai toan bo detail.
        await self._session.refresh(v, attribute_names=["prices"])
        return _build_detail(v)

    async def get_rag_snapshot(self, identifier: str) -> CatalogSnapshot:
        # First try to get vehicle by ID
        detail = await self.get_vehicle(identifier)
        if detail is None:
            # Then try to get vehicle by slug
            detail = await self.get_vehicle_by_slug(identifier)

        if detail is None:
            raise ProductNotFoundError(f"Vehicle {identifier!r} not found")

        # Resolve feature definitions referenced by the vehicle.
        codes = {f.feature_code for f in detail.feature_flags}
        definitions: list[FeatureDefinition] = []
        if codes:
            stmt = select(FeatureDefinitionRow).where(FeatureDefinitionRow.feature_code.in_(codes))
            result = await self._session.execute(stmt)
            definitions = [_to_feature_definition(d) for d in result.scalars().all() if d is not None]

        # Resolve promotions via promotion_vehicles.
        promo_ids = [link.promotion_id for link in detail.promotions]
        promotions: list[Promotion] = []
        if promo_ids:
            stmt = select(PromotionRow).where(PromotionRow.promotion_id.in_(promo_ids))
            promotions = [
                _to_promotion(p) for p in (await self._session.execute(stmt)).scalars().all() if p is not None
            ]

        return CatalogSnapshot(
            vehicle=detail.vehicle,
            specs=detail.specs,
            prices=detail.prices,
            promotions=promotions,
            battery_policies=detail.battery_policies,
            feature_flags=detail.feature_flags,
            feature_definitions=definitions,
        )


class SqlAlchemyFeatureFlagRepository(FeatureFlagRepository):
    """Doc/duyet vehicle_feature_flags, join sang vehicles va feature_definitions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_query(self):
        return select(VehicleFeatureFlagRow).options(
            selectinload(VehicleFeatureFlagRow.vehicle),
            selectinload(VehicleFeatureFlagRow.feature_def),
        )

    def _to_detail(self, row) -> FeatureFlagDetail:  # noqa: ANN001
        vehicle = row.vehicle
        vehicle_name = f"{vehicle.brand} {vehicle.model_name}".strip() if vehicle is not None else ""
        return FeatureFlagDetail(
            vehicle_id=row.vehicle_id,
            feature_code=row.feature_code,
            status=row.status,
            verification_status=row.verification_status,
            vehicle_name=vehicle_name,
            feature_name=row.feature_def.name if row.feature_def is not None else row.feature_code,
            confidence=row.confidence,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    async def list_flags(
        self,
        page: PageParams,
        *,
        verification_status: str | None = None,
        vehicle_id: str | None = None,
    ) -> list[FeatureFlagDetail]:
        stmt = self._base_query()
        if verification_status is not None:
            stmt = stmt.where(VehicleFeatureFlagRow.verification_status == verification_status)
        if vehicle_id is not None:
            stmt = stmt.where(VehicleFeatureFlagRow.vehicle_id == vehicle_id)
        stmt = (
            stmt.order_by(VehicleFeatureFlagRow.updated_at.desc(), VehicleFeatureFlagRow.feature_code)
            .offset(page.skip)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_detail(r) for r in rows]

    async def count_flags(self, *, verification_status: str | None = None, vehicle_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(VehicleFeatureFlagRow)
        if verification_status is not None:
            stmt = stmt.where(VehicleFeatureFlagRow.verification_status == verification_status)
        if vehicle_id is not None:
            stmt = stmt.where(VehicleFeatureFlagRow.vehicle_id == vehicle_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def review_flag(
        self, vehicle_id: str, feature_code: str, decision: str, actor_id: str
    ) -> FeatureFlagDetail | None:
        row = await self._session.get(VehicleFeatureFlagRow, (vehicle_id, feature_code))
        if row is None:
            return None
        # Chi dong vao verification_status — cot `status` (YES/NO/UNKNOWN) la
        # su that ve chiec xe, khong phai ket qua cua viec duyet.
        row.verification_status = decision
        row.updated_by = actor_id
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        refreshed = (
            await self._session.execute(
                self._base_query().where(
                    VehicleFeatureFlagRow.vehicle_id == vehicle_id,
                    VehicleFeatureFlagRow.feature_code == feature_code,
                )
            )
        ).scalar_one()
        return self._to_detail(refreshed)


def _looks_like_uuid(value: str) -> bool:
    """`vehicle_id` là cột UUID — bind một chuỗi slug vào đó khiến asyncpg
    ném DataError ngay ở tầng driver (nó ép kiểu tham số trước khi biết
    nhánh OR nào khớp), nên phải tự lọc trước khi đưa vào truy vấn."""
    try:
        UUID(value)
        return True
    except (TypeError, ValueError):
        return False


def _assumption_snapshot(assumption: TcoAssumptionRow | None) -> dict | None:
    """Chuyển một hàng `tco_assumptions` thành dict cho tầng service.

    Mọi cột tiền trên `TcoAssumptionRow` đều `nullable=True` (xem
    `models.py`), nên một hàng ACTIVE vẫn có thể thiếu dữ liệu (ví dụ mới
    insert thủ công, chưa điền đủ). Nếu cứ `Decimal(str(None))` sẽ ném
    `decimal.InvalidOperation` — lộ ra thành lỗi 500 thay vì `tco_unavailable`
    (422) như hợp đồng API yêu cầu. Nên trả `None` sớm ở đây để
    `TcoService.estimate()` bắt được bằng nhánh `if not assumptions` sẵn có.
    """
    if assumption is None:
        return None

    required = (
        assumption.electricity_vnd_per_kwh,
        assumption.registration_fee_percent,
        assumption.registration_fee_flat_vnd,
        assumption.plate_fee_vnd,
        assumption.inspection_fee_vnd,
        assumption.mandatory_insurance_vnd_per_year,
        assumption.road_fee_vnd_per_year,
        assumption.maintenance_vnd_per_service,
        assumption.maintenance_interval_km,
        assumption.source_note,
    )
    if any(field is None for field in required):
        return None

    return {
        "assumption_id": assumption.assumption_id,
        "region_code": assumption.region_code,
        "assumption_version": assumption.assumption_version,
        "electricity_vnd_per_kwh": Decimal(str(assumption.electricity_vnd_per_kwh)),
        "registration_fee_percent": Decimal(str(assumption.registration_fee_percent)),
        "registration_fee_flat_vnd": Decimal(str(assumption.registration_fee_flat_vnd)),
        "plate_fee_vnd": Decimal(str(assumption.plate_fee_vnd)),
        "inspection_fee_vnd": Decimal(str(assumption.inspection_fee_vnd)),
        "inspection_first_month": assumption.inspection_first_month,
        "inspection_interval_months": assumption.inspection_interval_months,
        "inspection_interval_months_after_7y": (assumption.inspection_interval_months_after_7y),
        "mandatory_insurance_vnd_per_year": Decimal(str(assumption.mandatory_insurance_vnd_per_year)),
        "road_fee_vnd_per_year": Decimal(str(assumption.road_fee_vnd_per_year)),
        "maintenance_vnd_per_service": Decimal(str(assumption.maintenance_vnd_per_service)),
        "maintenance_interval_km": Decimal(str(assumption.maintenance_interval_km)),
        "horizon_months": assumption.horizon_months,
        "source_note": assumption.source_note,
    }


class SqlAlchemyTcoRepository:
    """Đọc xe, giá và giả định trong đúng một lượt truy vấn mỗi bảng."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def get_tco_snapshot(self, identifier: str, *, region_code: str) -> dict | None:
        """Snapshot xe + giá + giả định phí của ĐÚNG khu vực khách chọn.

        `region_code` bắt buộc, không có mặc định: lệ phí biển số ô tô chênh
        nhau 100 lần giữa hai khu vực, nên một giá trị mặc định lặng lẽ là một
        con số sai gửi cho khách. Không khớp khu vực nào → `assumptions=None` →
        service trả `tco_unavailable`, chứ không rơi về dòng của vùng khác.
        """

        async with self._session_factory() as session:
            lookup = (
                or_(VehicleRow.vehicle_id == identifier, VehicleRow.slug == identifier)
                if _looks_like_uuid(identifier)
                else VehicleRow.slug == identifier
            )
            vehicle = (await session.execute(select(VehicleRow).where(lookup))).scalar_one_or_none()
            if vehicle is None:
                return None

            price_rows = (
                await session.execute(
                    select(VehiclePriceRow.price_type, VehiclePriceRow.amount_vnd).where(
                        VehiclePriceRow.vehicle_id == vehicle.vehicle_id,
                        VehiclePriceRow.status == "ACTIVE",
                    )
                )
            ).all()
            prices = {price_type: Decimal(str(amount)) for price_type, amount in price_rows}

            assumption = (
                await session.execute(
                    select(TcoAssumptionRow)
                    .where(
                        TcoAssumptionRow.vehicle_type == vehicle.vehicle_type,
                        TcoAssumptionRow.region_code == region_code,
                        TcoAssumptionRow.status == "ACTIVE",
                    )
                    .order_by(TcoAssumptionRow.assumption_version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if vehicle.vehicle_type == "CAR":
                spec = (
                    await session.execute(select(CarSpecRow).where(CarSpecRow.vehicle_id == vehicle.vehicle_id))
                ).scalar_one_or_none()
                range_km = None if spec is None else spec.range_km
            else:
                spec = (
                    await session.execute(
                        select(MotorbikeSpecRow).where(MotorbikeSpecRow.vehicle_id == vehicle.vehicle_id)
                    )
                ).scalar_one_or_none()
                range_km = None if spec is None else spec.range_max_km

        return {
            "vehicle_id": vehicle.vehicle_id,
            "vehicle_type": vehicle.vehicle_type,
            "prices": prices,
            "energy_consumption_kwh_per_100km": (None if spec is None else spec.energy_consumption_kwh_per_100km),
            "battery_capacity_kwh": None if spec is None else spec.battery_capacity_kwh,
            "range_km": range_km,
            "assumptions": _assumption_snapshot(assumption),
        }


class SqlAlchemyOfferPolicyRepository:
    """Luu/dia offer_adjustment_policies qua SQLAlchemy."""

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def list(self) -> list[OfferAdjustmentPolicy]:
        async with self._factory() as session:
            rows = (await session.execute(select(OfferAdjustmentPolicyRow))).scalars().all()
            return [_to_offer_policy(r) for r in rows]

    async def get(self, promotion_type: str) -> OfferAdjustmentPolicy | None:
        async with self._factory() as session:
            row = await session.get(OfferAdjustmentPolicyRow, promotion_type)
            return None if row is None else _to_offer_policy(row)

    async def create(self, policy: OfferAdjustmentPolicy, *, created_by: str) -> OfferAdjustmentPolicy:
        async with self._factory() as session, session.begin():
            row = OfferAdjustmentPolicyRow(
                promotion_type=policy.promotion_type.value,
                adjust_min_vnd=policy.adjust_min_vnd,
                adjust_max_vnd=policy.adjust_max_vnd,
                adjust_min_percent=policy.adjust_min_percent,
                adjust_max_percent=policy.adjust_max_percent,
                financing_months_min=policy.financing_months_min,
                financing_months_max=policy.financing_months_max,
                financing_support_max_vnd=policy.financing_support_max_vnd,
                gift_value_max_vnd=policy.gift_value_max_vnd,
                allowed_gift_codes=policy.allowed_gift_codes,
                registration_support_max_vnd=policy.registration_support_max_vnd,
                other_max_vnd=policy.other_max_vnd,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                created_by=created_by,
            )
            session.add(row)
            await session.flush()
            return _to_offer_policy(row)

    async def update(
        self,
        promotion_type: str,
        updates: dict[str, object],
        *,
        updated_by: str,
    ) -> OfferAdjustmentPolicy | None:
        async with self._factory() as session, session.begin():
            row = await session.get(OfferAdjustmentPolicyRow, promotion_type)
            if row is None:
                return None
            for key, value in updates.items():
                if key == "allowed_gift_codes":
                    row.allowed_gift_codes = value  # type: ignore[assignment]
                elif hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return _to_offer_policy(row)

    async def delete(self, promotion_type: str) -> bool:
        async with self._factory() as session, session.begin():
            row = await session.get(OfferAdjustmentPolicyRow, promotion_type)
            if row is None:
                return False
            await session.delete(row)
            await session.flush()
            return True


def _to_offer_policy(row: OfferAdjustmentPolicyRow) -> OfferAdjustmentPolicy:
    return OfferAdjustmentPolicy(
        promotion_type=PromotionType(row.promotion_type),
        adjust_min_vnd=row.adjust_min_vnd,
        adjust_max_vnd=row.adjust_max_vnd,
        adjust_min_percent=row.adjust_min_percent,
        adjust_max_percent=row.adjust_max_percent,
        financing_months_min=row.financing_months_min,
        financing_months_max=row.financing_months_max,
        financing_support_max_vnd=row.financing_support_max_vnd,
        gift_value_max_vnd=row.gift_value_max_vnd,
        allowed_gift_codes=row.allowed_gift_codes,
        registration_support_max_vnd=row.registration_support_max_vnd,
        other_max_vnd=row.other_max_vnd,
    )


__all__ = [
    "SqlAlchemyVehicleRepository",
    "SqlAlchemyFeatureFlagRepository",
    "SqlAlchemyTcoRepository",
    "SqlAlchemyOfferPolicyRepository",
]
