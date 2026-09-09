"""Pydantic model cho bề mặt HTTP của Locations."""

from decimal import Decimal

from pydantic import BaseModel


class LocationOut(BaseModel):
    """Một địa điểm trả về cho client."""

    id: str
    external_id: str
    type: str
    category_label: str
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


class LocationListOut(BaseModel):
    """Một lát kết quả kèm cờ báo đã bị cắt."""

    items: list[LocationOut]
    total: int
    truncated: bool


class CategoryOut(BaseModel):
    """Một loại địa điểm kèm số lượng."""

    id: str
    label: str
    count: int


class RegionOut(BaseModel):
    """Một tỉnh/thành kèm quận/huyện."""

    city: str
    districts: list[str]


class LocationsError(BaseModel):
    """Lỗi máy đọc được, cùng khuôn với module Auth."""

    error: str
