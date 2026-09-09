"""Catalog source for immutable run snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.adapters.vehicle_price_choice import PRICE_PREFERENCE
from src.agents.services.snapshotting import SnapshotCandidate, SnapshotFact
from src.products.infrastructure.models import (
    CarSpecRow,
    MotorbikeSpecRow,
    VehiclePriceRow,
    VehicleRow,
)


class SqlAlchemyCatalogSnapshotSource:
    """Load effective catalog facts for requested candidate IDs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Mở session mới mỗi lần load() để snapshot luôn dựng từ dữ liệu
        # catalog mới nhất, không kẹt trong transaction cũ giữ suốt vòng đời.
        self._session_factory = session_factory

    async def load(self, *, candidate_ids: tuple[UUID, ...], at: datetime) -> Sequence[SnapshotCandidate]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(VehicleRow).where(VehicleRow.vehicle_id.in_(tuple(map(str, candidate_ids))))
                    )
                )
                .scalars()
                .all()
            )
            prices = (
                (
                    await session.execute(
                        select(VehiclePriceRow).where(
                            VehiclePriceRow.vehicle_id.in_([row.vehicle_id for row in rows]),
                            VehiclePriceRow.status == "ACTIVE",
                            VehiclePriceRow.valid_from <= at,
                            (VehiclePriceRow.valid_to.is_(None)) | (VehiclePriceRow.valid_to > at),
                        )
                    )
                )
                .scalars()
                .all()
            )
            car_specs = (
                (
                    await session.execute(
                        select(CarSpecRow).where(CarSpecRow.vehicle_id.in_([row.vehicle_id for row in rows]))
                    )
                )
                .scalars()
                .all()
            )
            motorbike_specs = (
                (
                    await session.execute(
                        select(MotorbikeSpecRow).where(
                            MotorbikeSpecRow.vehicle_id.in_([row.vehicle_id for row in rows])
                        )
                    )
                )
                .scalars()
                .all()
            )
        prices_by_vehicle: dict[str, list[VehiclePriceRow]] = {}
        for price in prices:
            prices_by_vehicle.setdefault(price.vehicle_id, []).append(price)
        cars = {spec.vehicle_id: spec for spec in car_specs}
        motorbikes = {spec.vehicle_id: spec for spec in motorbike_specs}
        by_id = {row.vehicle_id: row for row in rows}
        return [
            SnapshotCandidate(
                vehicle_id=vehicle_id,
                # [I2] Ghép đủ brand + model_name + variant_name ngay tại snapshot,
                # cùng công thức với `catalog_reader.vehicle_facts` (bỏ phần rỗng).
                # Ghép ở đây, không để `model_name` trần: hai variant của cùng một
                # model (ràng buộc unique (model_name, variant_name)) sống sót cùng
                # lượt lọc sẽ ra hai card trùng tên nếu chỉ lấy `model_name`.
                model_name=_display_name(by_id[str(vehicle_id)]),
                facts=tuple(
                    fact
                    for fact in (
                        _vehicle_type_fact(by_id[str(vehicle_id)]),
                        _price_fact(prices_by_vehicle.get(str(vehicle_id), [])),
                        *_car_facts(cars.get(str(vehicle_id))),
                        *_motorbike_facts(motorbikes.get(str(vehicle_id))),
                    )
                    if fact is not None
                ),
            )
            for vehicle_id in candidate_ids
            if str(vehicle_id) in by_id
        ]


def _display_name(row: VehicleRow) -> str:
    """Ghép brand + model_name + variant_name, bỏ phần rỗng — cùng luật với
    `resolved_name` trong `catalog_reader.vehicle_facts`, để tên hiển thị nhất
    quán trên mọi mặt khách hàng nhìn thấy."""

    return " ".join(part for part in (row.brand, row.model_name, row.variant_name) if part)


def _vehicle_type_fact(row: VehicleRow) -> SnapshotFact:
    # vehicle_type là NOT NULL trên bảng vehicles nên luôn sinh fact;
    # nếu cột trả về enum SQLAlchemy thì lấy .value, tránh lọt chuỗi
    # dạng "VehicleType.CAR" vào snapshot.
    raw_value = getattr(row.vehicle_type, "value", row.vehicle_type)
    return SnapshotFact(
        fact_code="VEHICLE_TYPE",
        value_text=str(raw_value),
        source_table="vehicles",
        source_id=UUID(str(row.vehicle_id)),
    )


def _price_fact(prices: Sequence[VehiclePriceRow]) -> SnapshotFact | None:
    """Giá niêm yết theo ĐÚNG thứ tự ưu tiên dùng chung (`vehicle_price_choice`).

    `STARTING_PRICE` của xe máy là giá **thuê pin** — hình thức đã ngừng 1/3/2025.
    Lấy thẳng nó ở đây khiến hồ sơ gửi tư vấn viên mang một con số khác con số
    bảng chi phí tính ra cho cùng chiếc xe.
    """

    by_type = {item.price_type: item for item in prices}
    price = next((by_type[name] for name in PRICE_PREFERENCE if name in by_type), None)
    if price is None:
        return None
    return SnapshotFact(
        fact_code="STARTING_PRICE_VND",
        value_text=str(price.amount_vnd),
        source_table="vehicle_prices",
        source_id=UUID(str(price.price_id)),
    )


def _car_facts(spec: CarSpecRow | None) -> tuple[SnapshotFact, ...]:
    if spec is None:
        return ()
    return _facts(
        ("CAR_RANGE_KM", spec.range_km, "cars"),
        ("CAR_SEAT_COUNT", spec.seat_count, "cars"),
        ("FAST_CHARGE_TIME_MINUTES", spec.fast_charge_time_minutes, "cars"),
        ("HOME_CHARGE_TIME_MINUTES", spec.home_charge_time_minutes, "cars"),
        ("ENERGY_CONSUMPTION_KWH_PER_100KM", spec.energy_consumption_kwh_per_100km, "cars"),
        ("CARGO_VOLUME_STANDARD_L", spec.cargo_volume_standard_l, "cars"),
        # Mở rộng 2026-08-25 (Sếp: pitch nêu quá ít, khó thuyết phục khách). Sáu
        # thông số dưới đây đã nằm sẵn trong bảng `cars` và đủ dữ liệu cho cả
        # mười một mẫu — đưa vào snapshot là điều kiện CẦN để pitch được phép nêu
        # chúng, vì guardrail A6-1 chỉ chấp nhận số nào đối chiếu được với snapshot.
        ("CAR_BATTERY_CAPACITY_KWH", spec.battery_capacity_kwh, "cars"),
        ("CAR_MOTOR_POWER_KW", spec.motor_power_kw, "cars"),
        ("CAR_TORQUE_NM", spec.torque_nm, "cars"),
        ("CAR_MAX_SPEED_KMH", spec.max_speed_kmh, "cars"),
        ("CAR_ACCELERATION_0_100_SECONDS", spec.acceleration_0_100_seconds, "cars"),
        ("CAR_FAST_CHARGE_POWER_KW", spec.fast_charge_power_kw, "cars"),
        ("CARGO_VOLUME_MAXIMUM_L", spec.cargo_volume_maximum_l, "cars"),
        ("CAR_TOWING_CAPACITY_KG", spec.towing_capacity_kg, "cars"),
        # Kiểu dáng — thông số CHỮ đầu tiên của nhánh ô tô (Sếp 2026-08-26).
        #
        # Đủ cho 11/11 mẫu, và là căn cứ duy nhất trong catalog cho câu "xe gầm
        # cao": bảng `cars` không có cột khoảng sáng gầm nào. Không có nó thì
        # `perceptual_traits` không cấp phép được, và pitch phải im về đúng thứ
        # khách hay hỏi.
        ("CAR_BODY_TYPE", spec.body_type, "cars"),
        spec_id=spec.vehicle_id,
    )


def _motorbike_facts(spec: MotorbikeSpecRow | None) -> tuple[SnapshotFact, ...]:
    if spec is None:
        return ()
    return _facts(
        ("MOTORBIKE_RANGE_MAX_KM", spec.range_max_km, "motorbikes"),
        ("MOTORBIKE_MAX_LOAD_KG", spec.max_load_kg, "motorbikes"),
        ("ENERGY_CONSUMPTION_KWH_PER_100KM", spec.energy_consumption_kwh_per_100km, "motorbikes"),
        ("BATTERY_REMOVABLE", spec.battery_removable, "motorbikes"),
        ("BATTERY_SWAPPABLE", spec.battery_swappable, "motorbikes"),
        # Đối xứng với `_car_facts`: xe máy điện cũng có sẵn công suất, mô-men,
        # tốc độ, dung lượng pin, thời gian sạc và chiều cao yên cho cả bốn mươi mẫu.
        ("MOTORBIKE_MOTOR_POWER_W", spec.motor_power_w, "motorbikes"),
        ("MOTORBIKE_MAX_POWER_W", spec.max_power_w, "motorbikes"),
        ("MOTORBIKE_TORQUE_NM", spec.torque_nm, "motorbikes"),
        ("MOTORBIKE_MAX_SPEED_KMH", spec.max_speed_kmh, "motorbikes"),
        ("MOTORBIKE_BATTERY_CAPACITY_KWH", spec.battery_capacity_kwh, "motorbikes"),
        ("MOTORBIKE_CHARGING_TIME_MINUTES", spec.charging_time_minutes, "motorbikes"),
        ("MOTORBIKE_SEAT_HEIGHT_MM", spec.seat_height_mm, "motorbikes"),
        spec_id=spec.vehicle_id,
    )


def _facts(*values: tuple[str, object | None, str], spec_id: str) -> tuple[SnapshotFact, ...]:
    source_id = UUID(str(spec_id))
    return tuple(
        SnapshotFact(
            fact_code=code,
            value_text=_format_fact_value(value),
            source_table=table,
            source_id=source_id,
        )
        for code, value, table in values
        if value is not None
    )


def _format_fact_value(value: object) -> str:
    # bool là subclass của int nên phải chặn trước: str(True) ra "True"
    # viết hoa, trong khi _fact_bool ở recommendation.py chỉ nhận "true"/"false".
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
