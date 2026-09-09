"""Exact catalog-scope resolution for reviewed policy documents."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.document.application.errors import PolicyVehicleResolutionError
from src.document.domain.policy_scopes import BatteryChemistry, PolicyVehicleType
from src.products.infrastructure.models import MotorbikeSpecRow, VehicleRow


class SqlAlchemyPolicyVehicleResolver:
    """Resolve model names or slugs without fuzzy guessing across active cars."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve_vehicle_ids(
        self,
        affected_models: tuple[str, ...],
        *,
        vehicle_type: PolicyVehicleType | None = None,
        battery_chemistry: BatteryChemistry | None = None,
    ) -> tuple[str, ...]:
        """Return stable unique IDs or reject every unresolved reviewed scope."""

        requested = tuple(item.strip() for item in affected_models if item.strip())
        if not requested:
            raise PolicyVehicleResolutionError(("<missing affected_models>",))
        async with self._session_factory() as session:
            statement = (
                select(
                    VehicleRow.vehicle_id,
                    VehicleRow.model_name,
                    VehicleRow.variant_name,
                    VehicleRow.slug,
                    MotorbikeSpecRow.battery_type,
                )
                .outerjoin(MotorbikeSpecRow, MotorbikeSpecRow.vehicle_id == VehicleRow.vehicle_id)
                .where(VehicleRow.status == "ACTIVE")
            )
            if vehicle_type is PolicyVehicleType.CAR:
                statement = statement.where(VehicleRow.vehicle_type == "CAR")
            elif vehicle_type is PolicyVehicleType.MOTORBIKE:
                statement = statement.where(VehicleRow.vehicle_type == "ELECTRIC_MOTORBIKE")
            rows = (
                await session.execute(
                    statement
                )
            ).all()
        rows = [row for row in rows if _chemistry_matches(row.battery_type, battery_chemistry)]
        if requested == ("*",):
            return tuple(sorted(str(row.vehicle_id) for row in rows))

        requested_keys = {_scope_key(item) for item in requested}
        if requested_keys == {"motorbikelfp"}:
            return tuple(sorted(str(row.vehicle_id) for row in rows if _is_lfp(row.battery_type)))
        if requested_keys == {"motorbikenonlfp"}:
            return tuple(
                sorted(str(row.vehicle_id) for row in rows if _is_reviewed_non_lfp(row.battery_type))
            )

        ids_by_alias: dict[str, set[str]] = {}
        for vehicle_id, model_name, variant_name, slug, _battery_type in rows:
            identifier = str(vehicle_id)
            aliases = {model_name, slug}
            if variant_name:
                aliases.add(f"{model_name} {variant_name}")
            for alias in aliases:
                ids_by_alias.setdefault(_scope_key(alias), set()).add(identifier)

        resolved: set[str] = set()
        unresolved: list[str] = []
        for item in requested:
            matches = ids_by_alias.get(_scope_key(item))
            if not matches:
                unresolved.append(item)
                continue
            if len(matches) > 1:
                unresolved.append(f"{item} (ambiguous variant)")
                continue
            resolved.update(matches)
        if unresolved:
            raise PolicyVehicleResolutionError(tuple(unresolved))
        return tuple(sorted(resolved))


def _scope_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in folded if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def _is_lfp(value: str | None) -> bool:
    return value is not None and "lfp" in _scope_key(value)


def _is_reviewed_non_lfp(value: str | None) -> bool:
    if value is None or _is_lfp(value):
        return False
    normalized = _scope_key(value)
    return any(token in normalized for token in ("lithiumion", "liion", "leadacid", "chi"))


def _chemistry_matches(value: str | None, chemistry: BatteryChemistry | None) -> bool:
    if chemistry is None:
        return True
    if chemistry is BatteryChemistry.LFP:
        return _is_lfp(value)
    if chemistry is BatteryChemistry.LITHIUM_ION:
        return value is not None and any(
            token in _scope_key(value) for token in ("lithiumion", "liion")
        )
    if chemistry is BatteryChemistry.LEAD_ACID:
        return value is not None and any(
            token in _scope_key(value) for token in ("leadacid", "chi")
        )
    return value is not None and bool(_scope_key(value)) and not _is_lfp(value)
