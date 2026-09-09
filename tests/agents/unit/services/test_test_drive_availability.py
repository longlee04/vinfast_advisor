"""Nạp ô giờ của MỘT ngày khác — nốt còn thiếu của bước nạp lười.

Bước trước cắt `options` xuống còn ô của ngày mặc định (126 → 18 ô). Nhưng thẻ
vẫn bày đủ bảy ngày, mà client không có đường nào xin ô của sáu ngày còn lại —
nên khách bấm sang ngày thứ tư thì MỌI khung giờ đều mờ. Payload nhẹ đi, chức
năng thì gãy.

Hợp đồng ở đây: hỏi ô trống của một showroom trong một ngày, trả về đúng ngày
đó. Vị trí khách KHÔNG đi qua tham số — nó đọc từ phiên ở tầng route, cùng nguồn
với lượt chat đã dựng thẻ, nên client không tự chọn được mình đứng ở đâu.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.agents.domain.test_drive import VIETNAM_TZ, now_in_vietnam
from src.agents.domain.values import VehicleType
from src.agents.ports import NearbyPlace
from src.agents.services.test_drive import TestDriveServiceImpl

NOW = datetime(2026, 8, 28, 8, 0, tzinfo=VIETNAM_TZ)


class _Locations:
    """Ba showroom cố định, không phụ thuộc toạ độ truyền vào."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def nearest(self, **kwargs) -> list[NearbyPlace]:
        self.calls.append(kwargs)
        return [
            NearbyPlace(
                id=f"sr-{index}",
                location_type="SHOWROOM_CAR",
                category_label="Showroom",
                name=f"Showroom {index}",
                address=f"Số {index} Phố Huế",
                latitude=21.0,
                longitude=105.8,
                distance_km=1.0 + index,
                hotline=None,
                open_time="09:00",
                close_time="18:00",
                status="ACTIVE",
            )
            for index in range(1, 4)
        ]


class _NoBookings:
    """Không khung nào đã đầy."""

    async def count_active_at(self, showroom: str, moment: datetime) -> int:
        del showroom, moment
        return 0


class _EverythingBusy:
    async def count_active_at(self, showroom: str, moment: datetime) -> int:
        del showroom, moment
        return 99


def _service(bookings=None) -> TestDriveServiceImpl:
    return TestDriveServiceImpl(locations=_Locations(), bookings=bookings or _NoBookings())


@pytest.mark.asyncio
async def test_hoi_mot_ngay_thi_chi_nhan_o_cua_ngay_do() -> None:
    service = _service()
    target = (NOW + timedelta(days=3)).date()

    options = await service.availability(
        latitude=21.0,
        longitude=105.8,
        vehicle_type=VehicleType.CAR,
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        on_date=target,
    )

    assert options, "ngày trong cửa sổ phải có ô để chọn"
    assert {option.scheduled_at.date() for option in options} == {target}


@pytest.mark.asyncio
async def test_moi_o_deu_mang_ma_nut_dat_duoc_lich() -> None:
    """Ô trả về phải bấm được ngay, không bắt client tự ghép mã.

    Client tự ghép mã là mở thêm một nguồn sự thật thứ hai cho cùng một khung
    giờ — và hai bản ghép lệch nhau thì lịch đặt sai giờ mà không ai thấy.
    """

    from src.agents.services.slot_token import read_slot_token

    service = _service()

    options = await service.availability(
        latitude=21.0,
        longitude=105.8,
        vehicle_type=VehicleType.CAR,
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        on_date=(NOW + timedelta(days=2)).date(),
    )

    for option in options:
        choice = read_slot_token(
            option.value,
            session_id="11111111-1111-1111-1111-111111111111",
            customer_id="customer-1",
            now=now_in_vietnam(),
        )
        assert choice is not None, f"mã nút không đọc lại được: {option.value!r}"
        assert choice.scheduled_at == option.scheduled_at


@pytest.mark.asyncio
async def test_ngay_ngoai_cua_so_thi_rong_chu_khong_no() -> None:
    """Ngoài cửa sổ đặt lịch trả RỖNG — không ném, không bịa ô.

    Ngày đến từ nút trên trình duyệt, tức từ ngoài. Một ngày lạ phải dẫn tới
    "hôm đó không còn khung nào", chứ không làm hỏng cả màn hình.
    """

    service = _service()

    options = await service.availability(
        latitude=21.0,
        longitude=105.8,
        vehicle_type=VehicleType.CAR,
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        on_date=(NOW + timedelta(days=60)).date(),
    )

    assert options == ()


@pytest.mark.asyncio
async def test_khung_da_day_thi_khong_tra_ve() -> None:
    service = _service(bookings=_EverythingBusy())

    options = await service.availability(
        latitude=21.0,
        longitude=105.8,
        vehicle_type=VehicleType.CAR,
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        on_date=(NOW + timedelta(days=1)).date(),
    )

    assert options == ()
