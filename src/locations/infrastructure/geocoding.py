"""Địa danh → toạ độ, qua Nominatim (OpenStreetMap) và một bộ nhớ đệm Postgres.

[GIẢ ĐỊNH] Chọn Nominatim thay vì Google Geocoding API: miễn phí, không cần API
key, và repo hiện KHÔNG có sẵn khoá Google nào để dùng chung (đã soát cả
`.env.example` lẫn `src/config.py`). Nút "Chỉ đường" vẫn mở Google Maps, nhưng
đó là một deep link công khai — không phải lời gọi API, không liên quan tới lựa
chọn này.

Điều kiện sử dụng của Nominatim yêu cầu (a) một `User-Agent` định danh được ứng
dụng và (b) tối đa một request mỗi giây. Cả hai được tôn trọng ở đây: header đặt
tường minh, và bộ nhớ đệm Postgres cắt phần lớn lưu lượng lặp lại — một địa danh
chỉ tốn đúng một lần gọi trong `GEOCODE_TTL_DAYS` ngày.

Mọi lỗi mạng/HTTP đều bị NUỐT và quy về `None`. Đây là quyết định của tính năng,
không phải sự cẩu thả: nhà cung cấp geocoding nằm ngoài tầm kiểm soát, và một lần
timeout của nó không được biến câu hỏi của khách thành HTTP 500. Người gọi đọc
`None` rồi mời khách nói rõ hơn hoặc bật chia sẻ vị trí.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Final

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.locations.infrastructure.models import GeocodeCacheRow

logger = logging.getLogger("src.locations.geocoding")

NOMINATIM_URL: Final[str] = "https://nominatim.openstreetmap.org/search"
PROVIDER: Final[str] = "nominatim"

#: Nominatim cần một `User-Agent` định danh được ứng dụng; giá trị mặc định
#: `python-httpx/x.y` bị dịch vụ này chặn thẳng.
DEFAULT_USER_AGENT: Final[str] = "P150-VinFast-Assistant/1.0 (charging-station-finder)"

#: `countrycodes=vn` — mọi trạm sạc trong dữ liệu đều ở Việt Nam, nên một kết quả
#: ngoài Việt Nam chắc chắn là kết quả sai. Không giới hạn thì "Cầu Giấy" có thể
#: khớp một địa danh trùng tên ở nơi khác và khách nhận về "trạm gần nhất cách
#: 8.000 km".
COUNTRY_CODES: Final[str] = "vn"

#: [GIẢ ĐỊNH] 30 ngày, đúng con số bản mô tả tính năng nêu. Ranh giới hành chính
#: đổi hiếm hơn thế nhiều, nên TTL này thiên về an toàn.
GEOCODE_TTL_DAYS: Final[int] = 30

#: Timeout ngắn: khách đang chờ trong một khung chat. Thà mời họ gõ lại rõ hơn
#: sau 5 giây còn hơn treo cả lượt.
REQUEST_TIMEOUT_SECONDS: Final[float] = 5.0


def normalize_query(location_text: str) -> str:
    """Khoá cache: gộp khoảng trắng, hạ thường. Cắt 255 ký tự theo độ dài cột."""

    return " ".join((location_text or "").split()).casefold()[:255]


class NominatimGeocoder:
    """Gọi Nominatim, không đệm. Bọc trong `CachedGeocoder` để dùng thật."""

    def __init__(self, *, user_agent: str | None = None) -> None:
        self._user_agent = user_agent or os.environ.get("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)

    async def geocode(self, location_text: str) -> tuple[float, float, str] | None:
        """Toạ độ + tên chuẩn hoá, hoặc `None` khi không tra ra / gọi hỏng."""

        query = " ".join((location_text or "").split())
        if not query:
            return None
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": COUNTRY_CODES,
            "addressdetails": "0",
        }
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    NOMINATIM_URL,
                    params=params,
                    headers={"User-Agent": self._user_agent, "Accept-Language": "vi"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("geocode that bai cho %r", query[:80], exc_info=True)
            return None
        if not isinstance(payload, list) or not payload:
            return None
        first = payload[0]
        try:
            latitude = float(first["lat"])
            longitude = float(first["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        display_name = str(first.get("display_name") or query)
        return latitude, longitude, display_name


class CachedGeocoder:
    """Đọc `geocode_cache` trước, chỉ gọi ra ngoài khi chưa có hoặc đã hết hạn.

    Ghi cả kết quả RỖNG (`latitude`/`longitude` NULL): "địa danh này nhà cung cấp
    không biết" cũng là một câu trả lời đáng nhớ, và không nhớ nó thì mỗi lần
    khách gõ lại một địa danh sai chính tả là thêm một lần gọi ra ngoài.

    Một sự cố database ở đây KHÔNG được làm hỏng lượt: cả đọc lẫn ghi cache đều
    bọc trong `try`, và hỏng thì tính năng rơi về "gọi thẳng nhà cung cấp" — chậm
    hơn, vẫn đúng.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        upstream: NominatimGeocoder | None = None,
        ttl: timedelta | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._upstream = upstream or NominatimGeocoder()
        self._ttl = ttl or timedelta(days=GEOCODE_TTL_DAYS)
        # Nominatim cho phép 1 request/giây. Khoá này tuần tự hoá các lần gọi
        # RA NGOÀI trong cùng tiến trình; lần đọc cache không đi qua đây nên
        # đường chạy phổ biến không bị nối tiếp.
        self._upstream_lock = asyncio.Lock()

    async def geocode(self, location_text: str) -> tuple[float, float, str] | None:
        key = normalize_query(location_text)
        if not key:
            return None
        cached = await self._read(key)
        if cached is not None:
            hit, value = cached
            if hit:
                return value
        async with self._upstream_lock:
            resolved = await self._upstream.geocode(location_text)
        await self._write(key, resolved)
        return resolved

    async def _read(self, key: str) -> tuple[bool, tuple[float, float, str] | None] | None:
        """`None` = chưa có/hết hạn. `(True, value)` = đã đệm, `value` có thể `None`."""

        try:
            async with self._session_factory() as session:
                row = await session.scalar(select(GeocodeCacheRow).where(GeocodeCacheRow.query == key))
                if row is None:
                    return None
                expires_at = row.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at <= datetime.now(UTC):
                    return None
                if row.latitude is None or row.longitude is None:
                    return (True, None)
                return (
                    True,
                    (
                        float(row.latitude),
                        float(row.longitude),
                        row.display_name or key,
                    ),
                )
        except Exception:
            logger.warning("khong doc duoc geocode_cache cho %r", key[:80], exc_info=True)
            return None

    async def _write(self, key: str, resolved: tuple[float, float, str] | None) -> None:
        now = datetime.now(UTC)
        values = {
            "query": key,
            "display_name": None if resolved is None else resolved[2],
            "latitude": None if resolved is None else Decimal(str(round(resolved[0], 6))),
            "longitude": None if resolved is None else Decimal(str(round(resolved[1], 6))),
            "provider": PROVIDER,
            "created_at": now,
            "expires_at": now + self._ttl,
        }
        try:
            async with self._session_factory() as session:
                statement = insert(GeocodeCacheRow).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[GeocodeCacheRow.query],
                    set_={
                        key_name: values[key_name]
                        for key_name in (
                            "display_name",
                            "latitude",
                            "longitude",
                            "provider",
                            "created_at",
                            "expires_at",
                        )
                    },
                )
                await session.execute(statement)
                await session.commit()
        except Exception:
            logger.warning("khong ghi duoc geocode_cache cho %r", key[:80], exc_info=True)


__all__ = [
    "COUNTRY_CODES",
    "GEOCODE_TTL_DAYS",
    "NOMINATIM_URL",
    "CachedGeocoder",
    "NominatimGeocoder",
    "normalize_query",
]
