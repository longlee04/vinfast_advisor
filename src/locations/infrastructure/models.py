"""SQLAlchemy models for the Locations module."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class LocationsBase(DeclarativeBase):
    """Declarative base carrying only `locations` tables."""


class LocationRow(LocationsBase):
    """A VinFast facility: charging station, battery swap point, showroom, workshop."""

    __tablename__ = "locations"
    __table_args__ = (
        Index("ix_locations_lat_lon", "latitude", "longitude"),
        Index("ix_locations_type", "location_type"),
        Index("ix_locations_city_district", "city", "district"),
    )

    location_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    location_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category_name: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str | None] = mapped_column(String(128), nullable=True)
    province_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    district_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    hotline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    directions_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    close_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GeocodeCacheRow(LocationsBase):
    """Kết quả geocode một địa danh, giữ lại để khỏi hỏi nhà cung cấp hai lần.

    Nominatim yêu cầu tối đa 1 request/giây và cấm dùng ồ ạt. Không có bảng này
    thì mỗi lần một khách gõ "Cầu Giấy" là một lần gọi ra ngoài — cùng một câu
    trả lời, trả tiền bằng độ trễ của khách và bằng nguy cơ bị chặn IP.

    Khoá là dạng ĐÃ CHUẨN HOÁ của địa danh (thường, gộp khoảng trắng), không phải
    chuỗi thô: "Cầu Giấy", "cầu giấy" và " Cầu  Giấy " là một chỗ.

    `latitude`/`longitude` NULL là một trạng thái hợp lệ và có ích: nó ghi lại
    "địa danh này đã hỏi rồi và nhà cung cấp không biết". Thiếu nó, mỗi lần khách
    gõ lại một địa danh không tồn tại là một lần gọi ra ngoài nữa.
    """

    __tablename__ = "geocode_cache"
    __table_args__ = (Index("ix_geocode_cache_expires_at", "expires_at"),)

    query: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
