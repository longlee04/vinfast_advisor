"""CatalogReadAdapter — Layer 1 SQL Hard Filter implementation (mục 7.1 schema, A1-2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.vehicle_price_choice import preferred_price_join
from src.agents.contracts import FilterCriteria, VehicleFacts, VehicleMatch
from src.agents.domain.catalog_browse import BrowseEntry
from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger, log_file_execution
from src.products.infrastructure.models import (
    CarSpecRow,
    FeatureDefinitionRow,
    MotorbikeSpecRow,
    VehicleFeatureFlagRow,
    VehiclePriceRow,
    VehicleRow,
)

logger = get_agent_logger("agent.adapters.catalog_reader")


class CatalogReadAdapter:
    """Deterministic Query Builder for Layer 1 Hard Filter without text-to-SQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        log_file_execution("src/agents/adapters/catalog_reader.py", logger)
        # Mở session mới cho từng lời gọi — Admin sửa giá/khuyến mại xong,
        # câu tra cứu kế tiếp phải thấy ngay, không giữ transaction cũ.
        self._session_factory = session_factory

    async def hard_filter(self, criteria: FilterCriteria) -> list[UUID]:
        """Execute deterministic SQL query filter based on verified user slots."""
        logger.info("Executing Layer 1 hard filter for vehicle_type=%s", criteria.vehicle_type)

        v_type = (
            criteria.vehicle_type.value
            if isinstance(criteria.vehicle_type, VehicleType)
            else str(criteria.vehicle_type)
        )

        # Base query: Vehicles with status = ACTIVE and STARTING_PRICE active
        stmt = (
            select(VehicleRow.vehicle_id)
            # `.select_from` BẮT BUỘC: điều kiện join nhắc `VehicleRow` bên trong
            # một subquery tương quan, nên ORM không tự suy ra được vế TRÁI và ném
            # `InvalidRequestError` LÚC CHẠY. Đã làm sập chat trên prod 27/8.
            .select_from(VehicleRow)
            .join(
                VehiclePriceRow,
                preferred_price_join(),
            )
            .where(
                VehicleRow.status == "ACTIVE",
                VehicleRow.vehicle_type == v_type,
            )
        )

        if criteria.budget_max_vnd is not None:
            stmt = stmt.where(VehiclePriceRow.amount_vnd <= criteria.budget_max_vnd)

        if v_type == VehicleType.CAR.value or v_type == "CAR":
            stmt = stmt.join(CarSpecRow, VehicleRow.vehicle_id == CarSpecRow.vehicle_id)
            if criteria.passenger_count is not None:
                stmt = stmt.where(CarSpecRow.seat_count >= criteria.passenger_count)
            if criteria.required_range_km is not None:
                stmt = stmt.where(CarSpecRow.range_km >= criteria.required_range_km)

        elif v_type == VehicleType.ELECTRIC_MOTORBIKE.value or v_type == "ELECTRIC_MOTORBIKE":
            stmt = stmt.join(MotorbikeSpecRow, VehicleRow.vehicle_id == MotorbikeSpecRow.vehicle_id)
            if criteria.required_range_km is not None:
                stmt = stmt.where(MotorbikeSpecRow.range_max_km >= criteria.required_range_km)
            if criteria.required_load_kg is not None:
                stmt = stmt.where(MotorbikeSpecRow.max_load_kg >= criteria.required_load_kg)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            raw_ids = result.scalars().all()
        vehicle_uuids = [UUID(str(vid)) for vid in raw_ids]

        logger.info("Layer 1 hard filter returned %d candidates", len(vehicle_uuids))
        return vehicle_uuids

    async def browse_catalog(self, vehicle_type: VehicleType) -> list[BrowseEntry]:
        """[A4-7] Toàn bộ xe ĐANG BÁN của một loại, kèm giá khởi điểm nếu có.

        `OUTER JOIN` sang `vehicle_prices` chứ không `INNER JOIN` như
        `hard_filter`: xe chưa công bố giá (VF Wild) vẫn đang nằm trong danh mục,
        và một câu "cửa hàng có những xe gì" mà giấu nó đi là trả lời thiếu.
        Renderer đẩy nhóm chưa có giá xuống cuối, không bịa một con số thay thế.

        Chỉ `status='ACTIVE'`: xe ngừng bán không còn là thứ khách mua được.
        """

        price_column = VehiclePriceRow.amount_vnd
        # Thông số đi kèm để renderer viết được câu giới thiệu từng DÒNG xe. Nối
        # CẢ HAI bảng spec và để loại xe quyết định cột nào có giá trị — cùng khuôn
        # với `lookup_facts` ở dưới, thay vì dựng hai câu SELECT khác hình dạng.
        # `outerjoin` chứ không `join`: xe thiếu bản ghi spec vẫn phải xuất hiện
        # trong danh mục, chỉ là dòng của nó rút lại còn tên xe.
        stmt = (
            select(
                VehicleRow.vehicle_id,
                VehicleRow.brand,
                VehicleRow.model_name,
                VehicleRow.variant_name,
                VehicleRow.slug,
                price_column,
                CarSpecRow.body_type,
                CarSpecRow.seat_count,
                CarSpecRow.range_km,
                MotorbikeSpecRow.range_max_km,
                MotorbikeSpecRow.max_speed_kmh,
                MotorbikeSpecRow.license_requirement,
            )
            .select_from(VehicleRow)
            .outerjoin(
                VehiclePriceRow,
                preferred_price_join(),
            )
            .outerjoin(CarSpecRow, VehicleRow.vehicle_id == CarSpecRow.vehicle_id)
            .outerjoin(MotorbikeSpecRow, VehicleRow.vehicle_id == MotorbikeSpecRow.vehicle_id)
            .where(
                VehicleRow.status == "ACTIVE",
                VehicleRow.vehicle_type == vehicle_type.value,
            )
            # Sắp ngay trong SQL để hai lần gọi cho cùng một thứ tự; renderer vẫn
            # sắp lại theo giá, nhưng thứ tự ổn định là thứ test dựa vào.
            .order_by(VehicleRow.model_name, VehicleRow.variant_name, VehicleRow.vehicle_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()

        entries: list[BrowseEntry] = []
        for (
            vehicle_id,
            brand,
            model_name,
            variant_name,
            slug,
            amount_vnd,
            body_type,
            seat_count,
            car_range_km,
            motorbike_range_max_km,
            max_speed_kmh,
            license_requirement,
        ) in rows:
            # Ô tô đọc `cars.range_km`, xe máy đọc `motorbikes.range_max_km`; bên
            # kia luôn `NULL` vì một xe chỉ có bản ghi ở đúng một bảng spec.
            range_value = car_range_km if vehicle_type is VehicleType.CAR else motorbike_range_max_km
            display_name = " ".join(part for part in (brand, model_name, variant_name) if part)
            entries.append(
                BrowseEntry(
                    vehicle_id=UUID(str(vehicle_id)),
                    display_name=display_name,
                    vehicle_type=vehicle_type,
                    starting_price_vnd=(Decimal(amount_vnd) if amount_vnd is not None else None),
                    model_name=model_name or "",
                    variant_name=variant_name,
                    slug=slug or "",
                    body_type=body_type,
                    seat_count=seat_count,
                    range_km=None if range_value is None else Decimal(range_value),
                    max_speed_kmh=(None if max_speed_kmh is None else Decimal(max_speed_kmh)),
                    license_requirement=license_requirement,
                )
            )
        logger.info(
            "Catalog browse returned %d vehicles for vehicle_type=%s",
            len(entries),
            vehicle_type.value,
        )
        return entries

    async def resolve_vehicle_names(self, mentions: Sequence[str]) -> list[VehicleMatch]:
        """Resolve exact catalog names without inferring vehicle identity.

        So khớp trên dạng đã BỎ HẲN KHOẢNG TRẮNG: catalog ghi "VF 3" còn khách gõ
        "vf3", và khoảng trắng giữa dòng xe với số hiệu không mang thông tin phân
        biệt nào — không có hai mẫu xe nào chỉ khác nhau ở đúng dấu cách. Đây vẫn
        là khớp CHÍNH XÁC, không phải khớp mờ: "vf" vẫn không ra "VF 3", nên cam
        kết "không suy đoán danh tính xe" của A4-1 giữ nguyên.
        """
        normalized_mentions = [squashed for mention in mentions if (squashed := _squash(mention))]
        if not normalized_mentions:
            return []

        model_variant_name = func.concat_ws(" ", VehicleRow.model_name, VehicleRow.variant_name)
        display_name = func.concat_ws(" ", VehicleRow.brand, VehicleRow.model_name, VehicleRow.variant_name)
        stmt = (
            select(VehicleRow)
            .where(
                VehicleRow.status == "ACTIVE",
                or_(
                    _sql_squash(VehicleRow.model_name).in_(normalized_mentions),
                    _sql_squash(model_variant_name).in_(normalized_mentions),
                    _sql_squash(display_name).in_(normalized_mentions),
                ),
            )
            .order_by(VehicleRow.model_name, VehicleRow.variant_name, VehicleRow.vehicle_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        full_matches_by_name: dict[str, list[VehicleMatch]] = {}
        model_matches_by_name: dict[str, list[VehicleMatch]] = {}
        for row in rows:
            resolved_name = " ".join(part for part in (row.brand, row.model_name, row.variant_name) if part)
            match = VehicleMatch(
                vehicle_id=UUID(row.vehicle_id),
                display_name=resolved_name,
                vehicle_type=VehicleType(row.vehicle_type),
                model_name=row.model_name,
            )
            model_matches_by_name.setdefault(_squash(row.model_name), []).append(match)
            for alias in (
                _squash(" ".join(part for part in (row.model_name, row.variant_name) if part)),
                _squash(resolved_name),
            ):
                full_matches_by_name.setdefault(alias, []).append(match)

        resolved: list[VehicleMatch] = []
        seen: set[UUID] = set()
        for mention in normalized_mentions:
            # "Evo Grand" squash thành "evogrand" khớp CẢ model_name "Evo Grand"
            # (dòng Evo Grand Lite) LẪN model+variant "Evo Grand" (dòng Evo/Grand).
            # Ưu tiên khớp ĐẦY ĐỦ (model+variant) để tên khách nêu về đúng dòng xe,
            # thay vì rơi vào nhánh mập mờ chỉ vì một dòng khác tình cờ trùng tên.
            full = full_matches_by_name.get(mention, [])
            candidates = full if full else model_matches_by_name.get(mention, [])
            if not candidates and len(mention) >= 3:
                # "Evo" trơ trọi không phải model nào, nhưng là TIỀN TỐ của Evo 200,
                # Evo Grand, Evo Max… Gom hết để tầng trên hỏi "Evo nào ạ?" thay vì
                # hỏi ngân sách như chưa nghe thấy tên xe (đo 2026-08-28).
                candidates = [
                    match
                    for key, matches in model_matches_by_name.items()
                    if key.startswith(mention)
                    for match in matches
                ]
            for match in candidates:
                if match.vehicle_id not in seen:
                    resolved.append(match)
                    seen.add(match.vehicle_id)
        return resolved

    async def vehicle_facts(self, vehicle_ids: Sequence[UUID]) -> list[VehicleFacts]:
        """Read active starting prices and type-specific catalog specs."""
        if not vehicle_ids:
            return []

        str_ids = [str(vehicle_id) for vehicle_id in vehicle_ids]
        stmt = (
            select(VehicleRow, VehiclePriceRow, CarSpecRow, MotorbikeSpecRow)
            .select_from(VehicleRow)
            .outerjoin(
                VehiclePriceRow,
                preferred_price_join(),
            )
            .outerjoin(CarSpecRow, VehicleRow.vehicle_id == CarSpecRow.vehicle_id)
            .outerjoin(MotorbikeSpecRow, VehicleRow.vehicle_id == MotorbikeSpecRow.vehicle_id)
            .where(VehicleRow.status == "ACTIVE", VehicleRow.vehicle_id.in_(str_ids))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        facts_by_id: dict[UUID, VehicleFacts] = {}
        for vehicle, price, car, motorbike in rows:
            vehicle_id = UUID(vehicle.vehicle_id)
            resolved_name = " ".join(part for part in (vehicle.brand, vehicle.model_name, vehicle.variant_name) if part)
            vehicle_type = VehicleType(vehicle.vehicle_type)
            match vehicle_type:
                case VehicleType.CAR:
                    specs = _car_specs(car)
                case VehicleType.ELECTRIC_MOTORBIKE:
                    specs = _motorbike_specs(motorbike)
            facts_by_id[vehicle_id] = VehicleFacts(
                vehicle_id=vehicle_id,
                display_name=resolved_name,
                vehicle_type=vehicle_type,
                starting_price_vnd=Decimal(price.amount_vnd) if price is not None else None,
                specs=specs,
            )
        features = await self._approved_features(str_ids)
        return [
            replace(facts_by_id[vehicle_id], features=features.get(vehicle_id, {}))
            for vehicle_id in vehicle_ids
            if vehicle_id in facts_by_id
        ]

    async def image_urls(self, vehicle_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Ảnh của các xe đang ACTIVE; xe không có ảnh thì vắng mặt trong dict."""

        if not vehicle_ids:
            return {}
        stmt = select(VehicleRow.vehicle_id, VehicleRow.image_url).where(
            VehicleRow.status == "ACTIVE",
            VehicleRow.vehicle_id.in_([str(value) for value in vehicle_ids]),
            VehicleRow.image_url.is_not(None),
            VehicleRow.image_url != "",
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return {UUID(str(vehicle_id)): image_url for vehicle_id, image_url in rows}

    async def _approved_features(self, vehicle_ids: Sequence[str]) -> dict[UUID, dict[str, str]]:
        """Tính năng ĐÃ DUYỆT của từng xe: `feature_code` → tên hiển thị.

        Lọc `status='YES'` và `verification_status='APPROVED'` ngay trong SQL:
        bảng thông số gửi khách không được nhắc tới thứ chưa ai xác minh, và một
        dòng `status='NO'` lọt ra ngoài thì thành quảng cáo ngược.
        """

        stmt = (
            select(
                VehicleFeatureFlagRow.vehicle_id,
                VehicleFeatureFlagRow.feature_code,
                FeatureDefinitionRow.name,
            )
            .join(
                FeatureDefinitionRow,
                FeatureDefinitionRow.feature_code == VehicleFeatureFlagRow.feature_code,
            )
            .where(
                VehicleFeatureFlagRow.vehicle_id.in_(vehicle_ids),
                VehicleFeatureFlagRow.status == "YES",
                VehicleFeatureFlagRow.verification_status == "APPROVED",
            )
            .order_by(VehicleFeatureFlagRow.feature_code)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        grouped: dict[UUID, dict[str, str]] = {}
        for raw_vehicle_id, feature_code, name in rows:
            grouped.setdefault(UUID(raw_vehicle_id), {})[feature_code] = name
        return grouped

    async def active_feature_codes(self, vehicle_type: VehicleType) -> frozenset[str]:
        """Toàn bộ mã tính năng ACTIVE cho `vehicle_type` (Bước 2 — allowlist lượt
        2 đọc DB thay vì bảng cứng `feature_askable.ASKABLE_FEATURES`).

        Mirror đúng câu lọc của `adapters/feature_vocabulary.py::list_active_features`
        (status ACTIVE, vehicle_type khớp hoặc rỗng/NULL = dùng chung cả hai nhánh).
        """

        stmt = select(FeatureDefinitionRow.feature_code).where(
            FeatureDefinitionRow.status == "ACTIVE",
            or_(
                FeatureDefinitionRow.vehicle_type == vehicle_type.value,
                FeatureDefinitionRow.vehicle_type.is_(None),
                FeatureDefinitionRow.vehicle_type == "",
            ),
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return frozenset(rows)

    async def discriminating_feature_map(self, vehicle_ids: Sequence[UUID]) -> dict[UUID, dict[str, str]]:
        """Tính năng đã duyệt của từng xe: `feature_code` → tên hiển thị (T7)."""
        str_ids = [str(vid) for vid in vehicle_ids]
        return await self._approved_features(str_ids)

    async def feature_descriptions(self, codes: Sequence[str]) -> dict[str, str]:
        """Mô tả tiếng Việt của từng mã tính năng (Sếp 2026-08-26).

        Câu hỏi lượt 2 nay liệt kê mỗi tính năng một dòng KÈM giải thích, thay
        cho một chuỗi tên nối bằng chữ "hay". `feature_definitions.description`
        là nguồn DUY NHẤT của mô tả — chép sang một bảng cứng trong prompt sẽ
        thành bản thứ hai và hai bản sẽ lệch nhau.
        """

        if not codes:
            return {}
        stmt = select(FeatureDefinitionRow.feature_code, FeatureDefinitionRow.description).where(
            FeatureDefinitionRow.feature_code.in_(list(codes))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return {row[0]: row[1].strip() for row in rows if row[1] and row[1].strip()}

    async def differentiators(self, vehicle_ids: Sequence[UUID]) -> list[str]:
        """Fetch differentiating features across candidate vehicles."""
        if not vehicle_ids:
            return []

        str_ids = [str(vid) for vid in vehicle_ids]
        approved = await self._approved_features(str_ids)
        union: set[str] = set()
        for codes in approved.values():
            union.update(codes.values())
        return list(union)


def _squash(text: str | None) -> str:
    """Hạ chữ thường và bỏ mọi khoảng trắng — dạng chuẩn để so tên xe.

    "VF 3", "vf3", " Vf  3 " đều về "vf3". Khoảng trắng trong tên mẫu xe không
    phân biệt được xe nào với xe nào, nhưng lại là chỗ khách gõ khác nhau nhiều
    nhất.
    """

    return "".join((text or "").split()).casefold()


def _sql_squash(column):
    """Bản SQL của `_squash` — cùng phép chuẩn hoá phải chạy ở cả hai phía.

    Chuẩn hoá lệch nhau giữa câu WHERE và bảng alias trong Python thì hàng lọt
    qua SQL vẫn không tra được alias, và kết quả là im lặng không khớp gì.
    """

    return func.replace(func.lower(column), " ", "")


def _text(value: object) -> str | None:
    """Số/chuỗi về dạng text, `None` giữ nguyên `None`.

    `None` phải đi tới tận renderer để nhóm thiếu dữ liệu bị BỎ QUA. Thay nó
    bằng "" hay "chưa có" ở đây là ép câu trả lời nói về thứ catalog không biết.
    """

    return None if value is None else str(value)


def _car_specs(car: CarSpecRow | None) -> dict[str, str | int | None]:
    """Thông số ô tô cho bảng gửi khách — chỉ cột catalog THẬT SỰ có.

    Không có cột nào cho kích thước DxRxC, chiều dài cơ sở, hệ thống treo, điều
    hoà hay bảng màu, nên các nhóm đó không xuất hiện ở đây và renderer sẽ bỏ
    qua chúng. Bịa ra để bảng trông đầy đủ là đúng thứ tiêu chí "mọi số rời hệ
    thống phải truy được về bản ghi nguồn" cấm.
    """

    if car is None:
        return {}
    return {
        "body_type": car.body_type,
        "seat_count": car.seat_count,
        "range_km": _text(car.range_km),
        "range_cycle": car.range_cycle,
        "motor_power_kw": _text(car.motor_power_kw),
        "torque_nm": _text(car.torque_nm),
        "battery_capacity_kwh": _text(car.battery_capacity_kwh),
        "max_speed_kmh": _text(car.max_speed_kmh),
        "acceleration_0_100_seconds": _text(car.acceleration_0_100_seconds),
        "charging_port": car.charging_port,
        "fast_charge_time_minutes": car.fast_charge_time_minutes,
        "cargo_volume_standard_l": _text(car.cargo_volume_standard_l),
    }


def _motorbike_specs(motorbike: MotorbikeSpecRow | None) -> dict[str, str | int | None]:
    """Thông số xe máy điện, cùng nguyên tắc với `_car_specs`."""

    if motorbike is None:
        return {}
    return {
        "range_max_km": _text(motorbike.range_max_km),
        "range_cycle": motorbike.range_cycle,
        "max_load_kg": _text(motorbike.max_load_kg),
        "license_requirement": motorbike.license_requirement,
        "motor_power_w": motorbike.motor_power_w,
        "torque_nm": _text(motorbike.torque_nm),
        "battery_capacity_kwh": _text(motorbike.battery_capacity_kwh),
        "battery_type": motorbike.battery_type,
        "max_speed_kmh": _text(motorbike.max_speed_kmh),
        "charging_time_minutes": motorbike.charging_time_minutes,
        "seat_height_mm": _text(motorbike.seat_height_mm),
    }
