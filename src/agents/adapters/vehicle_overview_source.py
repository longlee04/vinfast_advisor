"""Read-only catalog and document source for structured vehicle overviews."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from src.agents.adapters.vehicle_price_choice import preferred_price_join
from src.agents.contracts import VehicleFacts
from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_overview import (
    AmbiguousVehicleResolution,
    ColorInfo,
    DimensionsInfo,
    EngineSpecs,
    EngineVariantSpecs,
    EvidenceItem,
    PriceVariant,
    ResolvedVehicleFamily,
)
from src.agents.ports import EmbeddingPort
from src.document.infrastructure.models import (
    VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS,
    VehicleDocumentRow,
)
from src.products.infrastructure.models import (
    CarSpecRow,
    FeatureDefinitionRow,
    MotorbikeSpecRow,
    VehicleFeatureFlagRow,
    VehiclePriceRow,
    VehicleRow,
)

logger = logging.getLogger(__name__)

TOPIC_QUERIES: Final[dict[str, str]] = {
    "highlights": "ưu điểm nổi bật thiết kế vận hành",
    "features": "trang bị tiện nghi công nghệ nổi bật",
    "safety": "hệ thống an toàn hỗ trợ lái",
    "colors": "màu sắc ngoại thất nội thất",
}
RRF_K: Final[int] = 60
RAG_FETCH_LIMIT: Final[int] = 12
RAG_RESULT_LIMIT: Final[int] = 3


#: Cột `CarSpecRow` bơm thêm vào `VehicleFacts.specs` cho câu hỏi một thông số.
_EXTRA_CAR_SPEC_CODES: tuple[str, ...] = (
    "battery_capacity_kwh",
    "motor_power_kw",
    "torque_nm",
    "max_speed_kmh",
    "acceleration_0_100_seconds",
    "fast_charge_time_minutes",
    "cargo_volume_standard_l",
)

#: Cột `MotorbikeSpecRow` bơm vào `VehicleFacts.specs` (đợt 9). Trước đây
#: `lookup_facts` chỉ join `cars`, nên "Evo đi được bao xa" / "cần bằng gì" của
#: xe máy điện luôn rơi về bảng tổng quan dù catalog có số. Cùng luật chuỗi-không-
#: Decimal như xe hơi: `specs` được ghi JSON, Decimal làm cả lượt 503 trên prod.
_EXTRA_MOTORBIKE_SPEC_CODES: tuple[str, ...] = (
    "range_max_km",
    "battery_capacity_kwh",
    "battery_type",
    "motor_power_w",
    "max_speed_kmh",
    "max_load_kg",
    "charging_time_minutes",
    "seat_height_mm",
    "license_requirement",
)


def _active_window(spec_row: type[CarSpecRow] | type[MotorbikeSpecRow]):
    """Điều kiện join "bản thông số đang hiệu lực" — chung cho `cars` và `motorbikes`."""

    return (
        (VehicleRow.vehicle_id == spec_row.vehicle_id)
        & or_(spec_row.effective_from.is_(None), spec_row.effective_from <= func.now())
        & or_(spec_row.effective_to.is_(None), spec_row.effective_to > func.now())
    )


class SqlAlchemyVehicleOverviewSource:
    """Read current catalog facts and approved brochure evidence without writes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding: EmbeddingPort,
    ) -> None:
        self._session_factory = session_factory
        self._embedding = embedding

    async def resolve(self, vehicle_name: str) -> ResolvedVehicleFamily | AmbiguousVehicleResolution | None:
        """Resolve an exact normalized model or model-plus-variant mention."""

        normalized_name = _squash(vehicle_name)
        if not normalized_name:
            return None
        model_variant_name = func.concat_ws(" ", VehicleRow.model_name, VehicleRow.variant_name)
        display_name = func.concat_ws(" ", VehicleRow.brand, VehicleRow.model_name, VehicleRow.variant_name)
        statement = (
            select(VehicleRow)
            .where(
                VehicleRow.status == "ACTIVE",
                or_(
                    _sql_squash(VehicleRow.model_name) == normalized_name,
                    _sql_squash(model_variant_name) == normalized_name,
                    _sql_squash(display_name) == normalized_name,
                ),
            )
            .order_by(VehicleRow.variant_name, VehicleRow.vehicle_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        if not rows:
            return None

        family_keys = {(row.brand, row.model_name, row.vehicle_type) for row in rows}
        if len(family_keys) > 1:
            return AmbiguousVehicleResolution(vehicle_name=vehicle_name)

        first = rows[0]
        return ResolvedVehicleFamily(
            vehicle_name=" ".join(part for part in (first.brand, first.model_name) if part),
            vehicle_type=VehicleType(first.vehicle_type),
            vehicle_ids=tuple(UUID(str(row.vehicle_id)) for row in rows),
            variant_names=tuple(row.variant_name or row.model_name for row in rows),
        )

    async def lookup_prices(self, vehicle_ids: tuple[UUID, ...]) -> list[PriceVariant]:
        """Read active starting prices, preserving stable variant order."""

        if not vehicle_ids:
            return []
        statement = (
            select(VehicleRow, VehiclePriceRow)
            .select_from(VehicleRow)
            .join(
                VehiclePriceRow,
                preferred_price_join(),
            )
            .where(
                VehicleRow.status == "ACTIVE",
                VehicleRow.vehicle_id.in_(_string_ids(vehicle_ids)),
            )
            .order_by(
                VehicleRow.variant_name,
                VehicleRow.vehicle_id,
                VehiclePriceRow.region_code,
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [
            PriceVariant(
                vehicle_id=UUID(str(vehicle.vehicle_id)),
                variant_name=vehicle.variant_name or vehicle.model_name,
                amount_vnd=Decimal(price.amount_vnd),
                price_type=price.price_type,
                region_code=price.region_code,
            )
            for vehicle, price in rows
        ]

    async def lookup_dimensions(self, vehicle_ids: tuple[UUID, ...]) -> DimensionsInfo | None:
        """Return no deterministic dimensions until the product schema stores them."""

        del vehicle_ids
        # [GIẢ ĐỊNH] Product schema 2026-08-14 chưa có dimensions; không suy từ brochure
        # ở nhánh lookup deterministic. Trả None để renderer bỏ section tương ứng.
        return None

    async def lookup_engine_specs(self, vehicle_ids: tuple[UUID, ...]) -> EngineSpecs | None:
        """Read the available car powertrain values grouped by catalog variant."""

        if not vehicle_ids:
            return None
        statement = (
            select(VehicleRow, CarSpecRow)
            .outerjoin(
                CarSpecRow,
                (VehicleRow.vehicle_id == CarSpecRow.vehicle_id)
                & or_(
                    CarSpecRow.effective_from.is_(None),
                    CarSpecRow.effective_from <= func.now(),
                )
                & or_(
                    CarSpecRow.effective_to.is_(None),
                    CarSpecRow.effective_to > func.now(),
                ),
            )
            .where(
                VehicleRow.status == "ACTIVE",
                VehicleRow.vehicle_id.in_(_string_ids(vehicle_ids)),
            )
            .order_by(VehicleRow.variant_name, VehicleRow.vehicle_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        variants = [
            EngineVariantSpecs(
                variant_name=vehicle.variant_name or vehicle.model_name,
                motor_power_kw=car.motor_power_kw,
                torque_nm=car.torque_nm,
                drivetrain=None,
                battery_capacity_kwh=getattr(car, "battery_capacity_kwh", None),
                range_km=getattr(car, "range_km", None),
                range_cycle=getattr(car, "range_cycle", None),
                max_speed_kmh=getattr(car, "max_speed_kmh", None),
                fast_charge_time_minutes=getattr(car, "fast_charge_time_minutes", None),
                fast_charge_from_percent=getattr(car, "fast_charge_from_percent", None),
                fast_charge_to_percent=getattr(car, "fast_charge_to_percent", None),
            )
            for vehicle, car in rows
            if car is not None and (car.motor_power_kw is not None or car.torque_nm is not None)
        ]
        return EngineSpecs(variants=variants) if variants else None

    async def lookup_colors(self, vehicle_ids: tuple[UUID, ...]) -> ColorInfo | None:
        """Return no catalog colors because the current schema has no color fields."""

        del vehicle_ids
        return None

    async def lookup_facts(self, vehicle_ids: tuple[UUID, ...]) -> list[VehicleFacts]:
        """Read active price and car facts for the downstream deterministic quote gate."""

        if not vehicle_ids:
            return []
        statement = (
            select(VehicleRow, VehiclePriceRow, CarSpecRow, MotorbikeSpecRow)
            .select_from(VehicleRow)
            .outerjoin(
                VehiclePriceRow,
                preferred_price_join(),
            )
            .outerjoin(CarSpecRow, _active_window(CarSpecRow))
            # Xe máy điện nằm ở `motorbikes`, không có hàng `cars`: outerjoin cả hai
            # thì một câu SQL phục vụ được cả hai loại, hàng nào không có thì `None`.
            .outerjoin(MotorbikeSpecRow, _active_window(MotorbikeSpecRow))
            .where(
                VehicleRow.status == "ACTIVE",
                VehicleRow.vehicle_id.in_(_string_ids(vehicle_ids)),
            )
            .order_by(
                VehicleRow.variant_name,
                VehicleRow.vehicle_id,
                VehiclePriceRow.region_code,
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        facts_by_id: dict[UUID, VehicleFacts] = {}
        for vehicle, price, car, bike in rows:
            vehicle_id = UUID(str(vehicle.vehicle_id))
            if vehicle_id in facts_by_id:
                continue
            facts_by_id[vehicle_id] = VehicleFacts(
                vehicle_id=vehicle_id,
                display_name=" ".join(
                    part for part in (vehicle.brand, vehicle.model_name, vehicle.variant_name) if part
                ),
                vehicle_type=VehicleType(vehicle.vehicle_type),
                starting_price_vnd=(Decimal(price.amount_vnd) if price is not None else None),
                specs={
                    "body_type": car.body_type if car is not None else None,
                    "seat_count": car.seat_count if car is not None else None,
                    "range_km": (str(car.range_km) if car is not None and car.range_km is not None else None),
                    # Cột thêm cho lõi v2 trả lời MỘT thông số ("sạc bao lâu",
                    # "cốp rộng không") mà không đổ cả bảng — probe H-7 2026-08-30.
                    # `render.spec_answer` tự đọc chuỗi số và định dạng lại.
                    # Chuỗi, không Decimal: `specs` được ghi JSON (outcome/trace) —
                    # Decimal làm cả lượt 503 trên prod 2026-08-30.
                    **{
                        code: str(getattr(car, code))
                        for code in _EXTRA_CAR_SPEC_CODES
                        if car is not None and getattr(car, code, None) is not None
                    },
                    **{
                        code: str(getattr(bike, code))
                        for code in _EXTRA_MOTORBIKE_SPEC_CODES
                        if bike is not None and getattr(bike, code, None) is not None
                    },
                },
            )
        try:
            approved = await self._approved_features([str(item) for item in vehicle_ids])
        except Exception:  # noqa: BLE001 — thiếu cờ thì overview vẫn phải ra, chỉ thiếu một dòng
            logger.warning("overview: khong doc duoc co tinh nang", exc_info=True)
            approved = {}
        return [
            replace(
                facts_by_id[item],
                features={code: name for code, (name, _category) in approved.get(item, {}).items()},
                feature_categories={code: category for code, (_name, category) in approved.get(item, {}).items()},
            )
            for item in vehicle_ids
            if item in facts_by_id
        ]

    async def _approved_features(self, vehicle_ids: Sequence[str]) -> dict[UUID, dict[str, tuple[str, str]]]:
        """Cờ `YES` + `APPROVED` → {vehicle_id: {code: (tên, nhóm)}} — cùng luật với `catalog_reader`."""

        stmt = (
            select(
                VehicleFeatureFlagRow.vehicle_id,
                VehicleFeatureFlagRow.feature_code,
                FeatureDefinitionRow.name,
                FeatureDefinitionRow.category,
            )
            .join(FeatureDefinitionRow, FeatureDefinitionRow.feature_code == VehicleFeatureFlagRow.feature_code)
            .where(
                VehicleFeatureFlagRow.vehicle_id.in_(vehicle_ids),
                VehicleFeatureFlagRow.status == "YES",
                VehicleFeatureFlagRow.verification_status == "APPROVED",
            )
            .order_by(VehicleFeatureFlagRow.feature_code)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        grouped: dict[UUID, dict[str, tuple[str, str]]] = {}
        for raw_vehicle_id, feature_code, name, category in rows:
            grouped.setdefault(UUID(str(raw_vehicle_id)), {})[feature_code] = (str(name), str(category or ""))
        return grouped

    async def retrieve(self, vehicle_ids: tuple[UUID, ...], *, topic: str) -> list[EvidenceItem]:
        """Read approved evidence for a fixed overview topic."""

        if not vehicle_ids:
            return []
        try:
            query_text = TOPIC_QUERIES[topic]
        except KeyError as error:
            raise ValueError(f"unsupported overview topic: {topic}") from error

        vectors = await self._embedding.embed([query_text])
        if not vectors:
            return []
        query_vector = _fit_document_embedding(vectors[0])
        string_ids = _string_ids(vehicle_ids)
        text_query = func.plainto_tsquery("simple", query_text)
        full_text_statement = (
            select(VehicleDocumentRow.document_id, VehicleDocumentRow.content)
            .where(
                VehicleDocumentRow.vehicle_id.in_(string_ids),
                VehicleDocumentRow.status == "ACTIVE",
                or_(
                    VehicleDocumentRow.valid_from.is_(None),
                    VehicleDocumentRow.valid_from <= func.now(),
                ),
                or_(
                    VehicleDocumentRow.valid_to.is_(None),
                    VehicleDocumentRow.valid_to > func.now(),
                ),
                VehicleDocumentRow.content_tsv.op("@@")(text_query),
            )
            .order_by(
                func.ts_rank_cd(VehicleDocumentRow.content_tsv, text_query).desc(),
                VehicleDocumentRow.document_id,
            )
            .limit(RAG_FETCH_LIMIT)
        )
        dense_statement = (
            select(VehicleDocumentRow.document_id, VehicleDocumentRow.content)
            .where(
                VehicleDocumentRow.vehicle_id.in_(string_ids),
                VehicleDocumentRow.status == "ACTIVE",
                or_(
                    VehicleDocumentRow.valid_from.is_(None),
                    VehicleDocumentRow.valid_from <= func.now(),
                ),
                or_(
                    VehicleDocumentRow.valid_to.is_(None),
                    VehicleDocumentRow.valid_to > func.now(),
                ),
                VehicleDocumentRow.embedding.is_not(None),
            )
            .order_by(
                VehicleDocumentRow.embedding.cosine_distance(query_vector),
                VehicleDocumentRow.document_id,
            )
            .limit(RAG_FETCH_LIMIT)
        )
        async with self._session_factory() as session:
            full_text_rows = (await session.execute(full_text_statement)).all()
            dense_rows = (await session.execute(dense_statement)).all()

        return _fuse_evidence(full_text_rows, dense_rows)


def _string_ids(vehicle_ids: tuple[UUID, ...]) -> list[str]:
    """Convert domain UUIDs to the string UUID representation used by ORM rows."""

    return [str(vehicle_id) for vehicle_id in vehicle_ids]


def _fit_document_embedding(vector: Sequence[float]) -> list[float]:
    """Fit injected embeddings to the fixed pgvector dimension used by documents."""

    fitted = list(vector[:VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS])
    missing = VEHICLE_DOCUMENT_EMBEDDING_DIMENSIONS - len(fitted)
    return fitted + ([0.0] * missing)


def _fuse_evidence(
    full_text_rows: Sequence[tuple[str, str]],
    dense_rows: Sequence[tuple[str, str]],
) -> list[EvidenceItem]:
    """Deduplicate two rankings with reciprocal-rank fusion and a stable tie-break."""

    scores: dict[str, float] = {}
    contents: dict[str, str] = {}
    for rows in (full_text_rows, dense_rows):
        seen_in_ranking: set[str] = set()
        for rank, (raw_document_id, content) in enumerate(rows, start=1):
            document_id = str(raw_document_id)
            if document_id in seen_in_ranking:
                continue
            seen_in_ranking.add(document_id)
            scores[document_id] = scores.get(document_id, 0.0) + 1.0 / (RRF_K + rank)
            contents.setdefault(document_id, content)

    ranked_ids = sorted(scores, key=lambda item: (-scores[item], item))[:RAG_RESULT_LIMIT]
    return [EvidenceItem(content=contents[document_id], evidence_id=document_id) for document_id in ranked_ids]


def _squash(text: str | None) -> str:
    """Normalize exact vehicle-name matching like ``CatalogReadAdapter``."""

    return "".join((text or "").split()).casefold()


def _sql_squash(column: ColumnElement[str]) -> ColumnElement[str]:
    """Apply the SQL equivalent of ``_squash`` to a catalog text column."""

    return func.replace(func.lower(column), " ", "")
