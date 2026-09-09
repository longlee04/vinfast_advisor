"""Truy vấn Postgres cho module Locations.

Khoảng cách tính bằng công thức Haversine viết thẳng trong SQL. Postgres đang
chạy không có PostGIS, và với 60 nghìn điểm thì lọc thô bằng bbox trên index
btree rồi mới tính chính xác là đủ nhanh — thêm một extension chỉ để tránh một
mệnh đề WHERE là chi phí vận hành không đáng.
"""

import math
from decimal import Decimal

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.locations.application.contracts import (
    CategoryCount,
    LocationPage,
    LocationSummary,
    RegionEntry,
)
from src.locations.application.ports import LocationStore
from src.locations.domain.values import BoundingBox, Coordinate
from src.locations.infrastructure.models import LocationRow

EARTH_RADIUS_KM = 6371.0
KM_PER_LATITUDE_DEGREE = 111.0


def _escape_like(term: str) -> str:
    """Vô hiệu hoá ký tự đại diện do người dùng nhập."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _haversine_km(origin: Coordinate):
    """Biểu thức SQL tính khoảng cách từ `origin` tới mỗi hàng."""
    origin_lat = math.radians(float(origin.latitude))
    origin_lon = math.radians(float(origin.longitude))
    row_lat = func.radians(cast(LocationRow.latitude, Float))
    row_lon = func.radians(cast(LocationRow.longitude, Float))
    return EARTH_RADIUS_KM * func.acos(
        func.least(
            1.0,
            math.sin(origin_lat) * func.sin(row_lat)
            + math.cos(origin_lat) * func.cos(row_lat) * func.cos(row_lon - origin_lon),
        )
    )


def _to_summary(row: LocationRow, distance_km: float | None = None) -> LocationSummary:
    return LocationSummary(
        location_id=row.location_id,
        external_id=row.external_id,
        location_type=row.location_type,
        category_name=row.category_name,
        name=row.name,
        address=row.address,
        city=row.city,
        district=row.district,
        latitude=Decimal(str(row.latitude)),
        longitude=Decimal(str(row.longitude)),
        hotline=row.hotline,
        directions_url=row.directions_url,
        open_time=row.open_time,
        close_time=row.close_time,
        status=row.status,
        distance_km=None if distance_km is None else Decimal(str(round(distance_km, 3))),
    )


class SqlAlchemyLocationStore(LocationStore):
    """Cài đặt `LocationStore` trên SQLAlchemy async."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def _filters(
        self,
        *,
        bounds: BoundingBox | None,
        types: tuple[str, ...],
        city: str | None,
        district: str | None,
        query: str | None,
    ) -> list:
        conditions: list = []
        if bounds is not None:
            conditions.append(LocationRow.latitude.between(bounds.south, bounds.north))
            conditions.append(LocationRow.longitude.between(bounds.west, bounds.east))
        if types:
            conditions.append(LocationRow.location_type.in_(types))
        if city:
            conditions.append(LocationRow.city == city)
        if district:
            conditions.append(LocationRow.district == district)
        if query:
            pattern = f"%{_escape_like(query)}%"
            conditions.append(
                LocationRow.name.ilike(pattern, escape="\\") | LocationRow.address.ilike(pattern, escape="\\")
            )
        return conditions

    async def list_in_bounds(
        self,
        *,
        bounds: BoundingBox | None,
        types: tuple[str, ...],
        city: str | None,
        district: str | None,
        query: str | None,
        limit: int,
    ) -> LocationPage:
        conditions = self._filters(bounds=bounds, types=types, city=city, district=district, query=query)
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(LocationRow).where(*conditions))
            rows = (
                (
                    await session.execute(
                        select(LocationRow)
                        .where(*conditions)
                        .order_by(LocationRow.city, LocationRow.name, LocationRow.location_id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        matched = total or 0
        return LocationPage(
            items=tuple(_to_summary(row) for row in rows),
            total=matched,
            truncated=matched > limit,
        )

    async def list_nearby(
        self,
        *,
        origin: Coordinate,
        radius_km: Decimal,
        types: tuple[str, ...],
        limit: int,
    ) -> LocationPage:
        latitude_delta = float(radius_km) / KM_PER_LATITUDE_DEGREE
        cosine = max(0.01, abs(math.cos(math.radians(float(origin.latitude)))))
        longitude_delta = float(radius_km) / (KM_PER_LATITUDE_DEGREE * cosine)
        rough = [
            LocationRow.latitude.between(
                float(origin.latitude) - latitude_delta, float(origin.latitude) + latitude_delta
            ),
            LocationRow.longitude.between(
                float(origin.longitude) - longitude_delta,
                float(origin.longitude) + longitude_delta,
            ),
        ]
        if types:
            rough.append(LocationRow.location_type.in_(types))
        distance = _haversine_km(origin)
        async with self._session_factory() as session:
            statement = (
                select(LocationRow, distance.label("distance_km"))
                .where(and_(*rough))
                .where(distance <= float(radius_km))
                .order_by(distance)
                .limit(limit)
            )
            result = (await session.execute(statement)).all()
            total = await session.scalar(
                select(func.count()).select_from(LocationRow).where(and_(*rough)).where(distance <= float(radius_km))
            )
        matched = total or 0
        return LocationPage(
            items=tuple(_to_summary(row, distance_km) for row, distance_km in result),
            total=matched,
            truncated=matched > limit,
        )

    async def count_by_category(self) -> tuple[CategoryCount, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        LocationRow.location_type,
                        func.min(LocationRow.category_name),
                        func.count(),
                    )
                    .group_by(LocationRow.location_type)
                    .order_by(LocationRow.location_type)
                )
            ).all()
        return tuple(CategoryCount(location_type=code, category_name=label, count=count) for code, label, count in rows)

    async def list_regions(self) -> tuple[RegionEntry, ...]:
        """Danh mục tỉnh/quận cho bộ lọc — CHỈ đọc từ SHOWROOM.

        Prod 2026-08-31: ~60k hàng trạm sạc/tủ pin crawl mang cột city bẩn
        (13.487 giá trị khác nhau — địa chỉ, tên người, cả kinh độ), đổ hết vào
        dropdown thì khách không chọn nổi tỉnh nào. Showroom seed chuẩn đúng
        danh mục tỉnh/phường sau sáp nhập nên là nguồn tên vùng duy nhất; dữ
        liệu bẩn vẫn nằm trong bảng cho tìm-theo-bản-đồ, chỉ không góp TÊN.
        """

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(LocationRow.city, LocationRow.district)
                    .where(
                        LocationRow.district.is_not(None),
                        LocationRow.location_type.in_(("showroom_car", "showroom_escooter")),
                    )
                    .distinct()
                    .order_by(LocationRow.city, LocationRow.district)
                )
            ).all()
        grouped: dict[str, list[str]] = {}
        for city, district in rows:
            if district is not None:
                grouped.setdefault(city, []).append(district)
        return tuple(RegionEntry(city=city, districts=tuple(districts)) for city, districts in grouped.items())
