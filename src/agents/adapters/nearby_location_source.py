"""[FIND_NEARBY_LOCATION] Adapter đọc địa điểm và geocode, bắc sang module Locations.

Không dựng truy vấn Haversine thứ hai ở đây, dù chỉ khoảng ba mươi dòng SQL. Bảng
`locations` đã có sẵn `SqlAlchemyLocationStore.list_nearby` — lọc thô bằng bounding
box trên index btree rồi mới tính chính xác, đúng cách nó cần được truy vấn với
60 nghìn điểm. Chép lại phép tính ấy sang `src/agents/` là dựng nguồn sự thật thứ
hai cho cùng một con số: sửa bán kính ở một chỗ, chỗ kia lặng lẽ trả kết quả khác.

Đi qua `LocationService` (tầng application) chứ không qua `SqlAlchemyLocationStore`
(tầng infrastructure) khi có thể: service nhận toàn tham số nguyên thuỷ, nên
module `agents` không phải import value object của module khác. Cùng ranh giới mà
`adapters/tco_source.py` đang giữ với `src.products`.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.ports import GeocodedPlace, NearbyPlace
from src.locations.application.location_service import LocationService
from src.locations.domain.errors import InvalidBoundsError, InvalidRadiusError
from src.locations.infrastructure.geocoding import CachedGeocoder
from src.locations.infrastructure.repositories import SqlAlchemyLocationStore

logger = logging.getLogger(__name__)


class LocationsNearbySource:
    """Cài đặt `NearbyLocationPort` trên module Locations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        service: LocationService | None = None,
    ) -> None:
        self._service = service or LocationService(SqlAlchemyLocationStore(session_factory))

    async def nearest(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        location_types,
        limit: int,
    ) -> list[NearbyPlace]:
        """Địa điểm gần nhất trong bán kính, đã sắp tăng dần theo khoảng cách.

        Toạ độ/bán kính không hợp lệ trả về danh sách RỖNG thay vì ném lên: cả
        hai giá trị này đến từ trình duyệt hoặc từ kết quả geocode, tức từ ngoài,
        và một lượt chat không được chết vì một con số lạ. Rỗng dẫn tới đúng câu
        "chưa tìm thấy trạm nào quanh đây", vốn là câu đúng trong ca đó.
        """

        try:
            page = await self._service.list_nearby(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                types=tuple(location_types),
                limit=limit,
            )
        except (InvalidBoundsError, InvalidRadiusError):
            logger.warning(
                "toa do/ban kinh khong hop le: lat=%s lon=%s radius=%s",
                latitude,
                longitude,
                radius_km,
            )
            return []
        return [
            NearbyPlace(
                id=item.external_id or item.location_id,
                location_type=item.location_type,
                category_label=item.category_name,
                name=item.name.strip(),
                address=item.address,
                latitude=float(item.latitude),
                longitude=float(item.longitude),
                distance_km=None if item.distance_km is None else float(item.distance_km),
                hotline=item.hotline,
                open_time=item.open_time,
                close_time=item.close_time,
                status=item.status,
            )
            for item in page.items
        ]


class LocationsGeocoder:
    """Cài đặt `GeocodePort` trên `CachedGeocoder` của module Locations."""

    def __init__(self, geocoder: CachedGeocoder) -> None:
        self._geocoder = geocoder

    async def geocode(self, location_text: str) -> GeocodedPlace | None:
        resolved = await self._geocoder.geocode(location_text)
        if resolved is None:
            return None
        latitude, longitude, display_name = resolved
        return GeocodedPlace(latitude=latitude, longitude=longitude, display_name=display_name)


__all__ = ["LocationsGeocoder", "LocationsNearbySource"]
