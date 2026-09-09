"""SQLAlchemy ORM models for the Product module.

Three separate table families, all prefixed ``product_``:

* ``product_cars``      — EV car catalogue (ev-database.org)
* ``product_motorbikes``— VinFast electric scooters
* ``product_policies``  — VinFast policy documents
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProductBase(DeclarativeBase):
    """Declarative base for Product tables only.

    Keeping it separate from AuthBase ensures Alembic autogenerate cannot
    touch auth tables when generating product migrations and vice-versa.
    """


# ---------------------------------------------------------------------------
# Car
# ---------------------------------------------------------------------------


class CarRow(ProductBase):
    """EV car row (all_cars.csv)."""

    __tablename__ = "product_cars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    variant: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    body_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    year: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    range_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    efficiency_wh_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acceleration_0_100_sec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    one_stop_range_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    battery_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    fastcharge_kw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    towing_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cargo_volume_l: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_product_cars_brand", "brand"),
        Index("ix_product_cars_year", "year"),
    )


# ---------------------------------------------------------------------------
# Motorbike
# ---------------------------------------------------------------------------


class MotorbikeRow(ProductBase):
    """VinFast electric scooter row (motobike_vin.csv)."""

    __tablename__ = "product_motorbikes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    variant: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    vehicle_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    year: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    motor_power: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_power: Mapped[str | None] = mapped_column(Text, nullable=True)
    torque: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_speed: Mapped[str | None] = mapped_column(Text, nullable=True)
    battery_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    battery_capacity: Mapped[str | None] = mapped_column(Text, nullable=True)
    battery_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_removable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    range_km: Mapped[str | None] = mapped_column(Text, nullable=True)
    charging_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    charging_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    weight: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_load: Mapped[str | None] = mapped_column(Text, nullable=True)
    seat_height: Mapped[str | None] = mapped_column(Text, nullable=True)
    wheel_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    front_brake: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rear_brake: Mapped[str | None] = mapped_column(String(64), nullable=True)
    front_suspension: Mapped[str | None] = mapped_column(Text, nullable=True)
    rear_suspension: Mapped[str | None] = mapped_column(Text, nullable=True)
    smart_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_product_motorbikes_brand", "brand"),
        Index("ix_product_motorbikes_year", "year"),
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class PolicyRow(ProductBase):
    """VinFast policy document row (policies.csv)."""

    __tablename__ = "product_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    year: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preview_pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawl_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_product_policies_category", "category"),
        Index("ix_product_policies_year", "year"),
    )


__all__ = ["CarRow", "MotorbikeRow", "PolicyRow", "ProductBase"]
