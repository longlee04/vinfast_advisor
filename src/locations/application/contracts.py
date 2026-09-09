"""Kiểu dữ liệu vào/ra của tầng application, không dính SQLAlchemy."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LocationSummary:
    """Một địa điểm như hiển thị trên bản đồ và danh sách."""

    location_id: str
    external_id: str
    location_type: str
    category_name: str
    name: str
    address: str
    city: str
    district: str | None
    latitude: Decimal
    longitude: Decimal
    hotline: str | None
    directions_url: str | None
    open_time: str | None
    close_time: str | None
    status: str | None
    distance_km: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LocationPage:
    """Một lát kết quả.

    `total` là tổng số bản ghi khớp điều kiện, không phải số phần tử trong
    `items`. Chỉ khi hai giá trị này khác nhau thì giao diện mới biết mình
    đang xem một phần.
    """

    items: tuple[LocationSummary, ...]
    total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """Một loại địa điểm kèm số lượng."""

    location_type: str
    category_name: str
    count: int


@dataclass(frozen=True, slots=True)
class RegionEntry:
    """Một tỉnh/thành kèm danh sách quận/huyện của nó."""

    city: str
    districts: tuple[str, ...]
