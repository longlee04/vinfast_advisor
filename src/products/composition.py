"""Product composition root.

Constructs and owns all Product infrastructure (engine, session factory,
repositories, services). Attaches itself to ``app.state.product`` so routes
can resolve services via the request object.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.products.application import FeatureFlagRepository, VehicleRepository
from src.products.application.feature_flag_service import FeatureFlagService
from src.products.application.offer_policy_service import OfferPolicyService
from src.products.application.tco_service import TcoService
from src.products.application.vehicle_service import VehicleCatalogService
from src.products.infrastructure.repositories import (
    SqlAlchemyFeatureFlagRepository,
    SqlAlchemyOfferPolicyRepository,
    SqlAlchemyTcoRepository,
    SqlAlchemyVehicleRepository,
)


@dataclass(frozen=True, slots=True)
class ProductResources:
    """Concrete adapters cho Product feature (schema mới)."""

    vehicle_service: VehicleCatalogService
    feature_flag_service: FeatureFlagService
    tco_service: TcoService | None = None
    offer_policy_service: OfferPolicyService | None = None
    engine: AsyncEngine | None = None


class ProductComposition:
    """Build and tear-down all Product infrastructure."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._resources: ProductResources | None = None

    @property
    def resources(self) -> ProductResources | None:
        return self._resources

    async def start(self) -> None:
        """Create engine + session factory, wire repository and service."""
        engine = create_async_engine(self._database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        vehicle_repo = _SessionVehicleRepository(session_factory)
        flag_repo = _SessionFeatureFlagRepository(session_factory)
        offer_policy_repo = _SessionOfferPolicyRepository(session_factory)
        self._resources = ProductResources(
            vehicle_service=VehicleCatalogService(vehicle_repo),
            feature_flag_service=FeatureFlagService(flag_repo),
            tco_service=TcoService(SqlAlchemyTcoRepository(session_factory)),
            offer_policy_service=OfferPolicyService(offer_policy_repo),
            engine=engine,
        )

    async def shutdown(self) -> None:
        resources, self._resources = self._resources, None
        if resources is not None and resources.engine is not None:
            await resources.engine.dispose()


# ---------------------------------------------------------------------------
# Session-scoped repository wrapper
# ---------------------------------------------------------------------------


class _SessionVehicleRepository(VehicleRepository):
    """Mở một session mới cho mỗi call; tương thích với SqlAlchemyVehicleRepository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def get_vehicle(self, identifier):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).get_vehicle(identifier)

    async def get_vehicle_by_slug(self, slug):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).get_vehicle_by_slug(slug)

    async def get_vehicle_by_sku(self, sku):  # type: ignore[override]
        # Thiếu wrapper này từ đầu: `vehicle_service.get_vehicle_detail` rơi tới
        # nhánh SKU (id/slug không khớp) là AttributeError → 500 cho khách
        # (prod 2026-08-31, GET /vehicles/vf-5).
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).get_vehicle_by_sku(sku)

    async def list_vehicles(self, page, status=None, vehicle_type=None):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).list_vehicles(page, status=status, vehicle_type=vehicle_type)

    async def search_vehicles(self, query, page, status=None):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).search_vehicles(query, page, status=status)

    async def count_vehicles(self, status=None, vehicle_type=None):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).count_vehicles(status=status, vehicle_type=vehicle_type)

    async def create_vehicle(self, data):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).create_vehicle(data)

    async def update_vehicle_price(self, vehicle_id, price_id, data):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).update_vehicle_price(vehicle_id, price_id, data)

    async def update_vehicle_specs(self, vehicle_id, data):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).update_vehicle_specs(vehicle_id, data)

    async def update_feature_flag(self, vehicle_id, feature_code, data):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).update_feature_flag(vehicle_id, feature_code, data)

    async def delete_vehicle(self, vehicle_id):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).delete_vehicle(vehicle_id)

    async def archive_vehicle(self, vehicle_id):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).archive_vehicle(vehicle_id)

    async def restore_vehicle(self, vehicle_id):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).restore_vehicle(vehicle_id)

    async def update_vehicle(self, vehicle_id, data):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).update_vehicle(vehicle_id, data)

    async def replace_vehicle_prices(self, vehicle_id, prices):  # type: ignore[override]
        async with self._factory() as s, s.begin():
            return await SqlAlchemyVehicleRepository(s).replace_vehicle_prices(vehicle_id, prices)

    async def get_rag_snapshot(self, identifier):  # type: ignore[override]
        async with self._factory() as s:
            return await SqlAlchemyVehicleRepository(s).get_rag_snapshot(identifier)


class _SessionFeatureFlagRepository(FeatureFlagRepository):
    """Mo mot session moi cho moi call — cung pattern _SessionVehicleRepository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def list_flags(self, page, *, verification_status=None, vehicle_id=None):  # type: ignore[override]
        async with self._factory() as session:
            return await SqlAlchemyFeatureFlagRepository(session).list_flags(
                page, verification_status=verification_status, vehicle_id=vehicle_id
            )

    async def count_flags(self, *, verification_status=None, vehicle_id=None):  # type: ignore[override]
        async with self._factory() as session:
            return await SqlAlchemyFeatureFlagRepository(session).count_flags(
                verification_status=verification_status, vehicle_id=vehicle_id
            )

    async def review_flag(self, vehicle_id, feature_code, decision, actor_id):  # type: ignore[override]
        async with self._factory() as session, session.begin():
            return await SqlAlchemyFeatureFlagRepository(session).review_flag(
                vehicle_id, feature_code, decision, actor_id
            )


class _SessionOfferPolicyRepository:
    """Mo mot session moi cho moi call cho offer_adjustment_policies."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def list(self):
        async with self._factory() as session:
            return await SqlAlchemyOfferPolicyRepository(session).list()

    async def get(self, promotion_type):
        async with self._factory() as session:
            return await SqlAlchemyOfferPolicyRepository(session).get(promotion_type)

    async def create(self, policy, *, created_by):
        async with self._factory() as session, session.begin():
            return await SqlAlchemyOfferPolicyRepository(session).create(policy, created_by=created_by)

    async def update(self, promotion_type, updates, *, updated_by):
        async with self._factory() as session, session.begin():
            return await SqlAlchemyOfferPolicyRepository(session).update(promotion_type, updates, updated_by=updated_by)

    async def delete(self, promotion_type):
        async with self._factory() as session, session.begin():
            return await SqlAlchemyOfferPolicyRepository(session).delete(promotion_type)


__all__ = ["ProductComposition", "ProductResources"]
