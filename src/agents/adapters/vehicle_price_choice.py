"""Một nguồn giá NIÊM YẾT duy nhất cho mọi câu trả lời về xe.

Vì sao có file này (đo trên prod 2026-08-27): `tools/tco.py` và
`services/on_road_price.py` đọc giá theo thứ tự `BATTERY_INCLUDED` →
`STARTING_PRICE`, còn ba adapter dựng câu đề xuất / pitch / bảng thông số lại chỉ
đọc `STARTING_PRICE`. Với xe MÁY hai giá đó khác nhau, vì `STARTING_PRICE` là giá
**thuê pin** — hình thức VinFast đã ngừng từ 1/3/2025.

Hậu quả khách nhìn thấy: cùng một chiếc, pitch nói một giá và bảng chi phí tính
theo giá khác. Bảy dòng xe máy đang lệch, nặng nhất là `Kinet Standard`: pitch
40.000.000đ, bảng chi phí tính trên 49.900.000đ.

Ô tô không dính — hai giá bằng nhau ở cả 9 dòng.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import aliased

from src.products.infrastructure.models import VehiclePriceRow, VehicleRow

#: Thứ tự ưu tiên, GIỐNG `tools/tco.py` và `services/on_road_price.py`.
#:
#: Đổi ở đây thì phải đổi cả hai chỗ kia — ba nơi cùng trả lời một câu hỏi
#: "chiếc này giá bao nhiêu", nên chúng phải cùng một câu trả lời.
PRICE_PREFERENCE: Final[tuple[str, ...]] = ("BATTERY_INCLUDED", "STARTING_PRICE")


def preferred_price_id():
    """`price_id` của giá niêm yết nên dùng cho `VehicleRow` đang truy vấn.

    Dùng CASE + ORDER BY + LIMIT chứ không `array_position`: nó chạy được trên cả
    Postgres (prod) lẫn SQLite (một phần test tích hợp).
    """

    inner = aliased(VehiclePriceRow)
    rank = case(
        *[(inner.price_type == price_type, index) for index, price_type in enumerate(PRICE_PREFERENCE)],
        else_=len(PRICE_PREFERENCE),
    )
    return (
        select(inner.price_id)
        .where(
            inner.vehicle_id == VehicleRow.vehicle_id,
            inner.status == "ACTIVE",
            inner.price_type.in_(PRICE_PREFERENCE),
            # Chỉ chọn trong các dòng ĐANG hiệu lực. Thiếu vế này thì một dòng
            # `BATTERY_INCLUDED` hết hạn vẫn thắng, và join ngoài (vốn lọc theo
            # cửa sổ hiệu lực) không khớp gì cả — mất luôn giá của chiếc xe.
            inner.valid_from <= func.now(),
            or_(inner.valid_to.is_(None), inner.valid_to > func.now()),
        )
        .order_by(rank)
        .limit(1)
        .correlate(VehicleRow)
        .scalar_subquery()
    )


def preferred_price_join():
    """Điều kiện join lấy ĐÚNG một dòng giá — dòng được ưu tiên cao nhất."""

    # Giữ luôn vế `vehicle_id ==`: nó là thứ cho SQLAlchemy biết vế TRÁI của join.
    # Thiếu nó, điều kiện chỉ còn nhắc `VehicleRow` bên trong subquery tương quan
    # và ORM báo "Can't determine which FROM clause to join from".
    return (VehicleRow.vehicle_id == VehiclePriceRow.vehicle_id) & (VehiclePriceRow.price_id == preferred_price_id())


__all__ = ["PRICE_PREFERENCE", "preferred_price_id", "preferred_price_join"]
