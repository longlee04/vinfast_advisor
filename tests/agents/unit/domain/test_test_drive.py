from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.agents.domain.nearby_location import UserLocation
from src.agents.domain.test_drive import (
    VIETNAM_TZ,
    ShowroomSlots,
    candidate_slots,
    format_date,
    format_day_label,
    format_slot,
    parse_business_hours,
)
from src.agents.domain.values import VehicleType
from src.agents.ports import NearbyPlace
from src.agents.services.operations.booking import SLOT_CAPACITY
from src.agents.services.test_drive import TestDriveServiceImpl, build_test_drive_card


def _issue(showroom: str, when) -> str:
    """Giấy phép giả cho test THUẦN: đủ để phân biệt ô, không cần khoá thật."""

    return f"__ky__|{showroom}|{when.isoformat()}"


class FakeLocations:
    def __init__(self, places: list[NearbyPlace]) -> None:
        self.places = places

    async def nearest(self, **kwargs: object) -> list[NearbyPlace]:
        return self.places


class FakeBookings:
    def __init__(self, full_showrooms: set[str]) -> None:
        self.full_showrooms = full_showrooms

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int:
        return SLOT_CAPACITY if showroom in self.full_showrooms else 0

    async def book(self, **kwargs: object) -> None:
        return None


def _place(name: str, distance: float, address: str) -> NearbyPlace:
    return NearbyPlace(
        id=str(uuid4()),
        location_type="SHOWROOM_CAR",
        category_label="Showroom",
        name=name,
        address=address,
        latitude=21.0,
        longitude=105.0,
        distance_km=distance,
        hotline=None,
        open_time="09:00",
        close_time="18:00",
        status="OPEN",
    )


@pytest.mark.anyio
async def test_test_drive_chon_showroom_gan_nhat_ke_ca_khi_khung_da_co_nguoi_dat() -> None:
    """ĐỔI KỲ VỌNG 2026-08-31 (Sếp: bỏ giới hạn đặt lịch). Trước đây showroom
    "đầy" bị né và khách bị đẩy sang chỗ xa hơn; nay một khung nhận bao nhiêu
    khách cũng được nên GẦN NHẤT luôn thắng."""

    service = TestDriveServiceImpl(
        locations=FakeLocations([_place("Gần nhưng đông", 1.0, "Địa chỉ A"), _place("Gần tiếp", 2.0, "Địa chỉ B")]),
        bookings=FakeBookings({"Gần nhưng đông"}),
    )

    result = await service.answer(
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        user_message="vâng",
        vehicle_name="VF 8",
        vehicle_type=VehicleType.CAR,
        known_location=UserLocation(latitude=21.0, longitude=105.0, source="browser"),
    )

    assert result.slot_options
    assert {option.showroom for option in result.slot_options} == {"Gần nhưng đông"}
    assert all("h" in option.label for option in result.slot_options)
    assert result.card is not None and result.card.showrooms[0].name == "Gần nhưng đông"


def test_parse_business_hours_reads_hour_part() -> None:
    assert parse_business_hours("08:00", "17:30") == (8, 17)


def test_parse_business_hours_falls_back_to_defaults() -> None:
    assert parse_business_hours(None, None) == (9, 18)
    assert parse_business_hours("garbage", "") == (9, 18)


def test_parse_business_hours_guards_close_not_after_open() -> None:
    assert parse_business_hours("09:00", "08:00") == (9, 18)


def test_candidate_slots_skips_past_hours_today() -> None:
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    slots = candidate_slots(open_time="09:00", close_time="18:00", now=now)
    assert slots
    assert all(slot > now for slot in slots)
    assert all(slot.hour in range(9, 18) for slot in slots)


def test_format_slot_and_date() -> None:
    slot = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
    assert format_slot(slot) == "9h00"
    assert format_date(slot, today=datetime(2026, 8, 25, tzinfo=UTC)) == "hôm nay"
    assert format_date(slot, today=datetime(2026, 8, 24, tzinfo=UTC)) == "ngày mai"


def _row(name: str, slots: tuple[datetime, ...], *, distance: float = 1.0) -> ShowroomSlots:
    return ShowroomSlots(
        showroom_id=f"id-{name}",
        showroom_name=name,
        address=f"Địa chỉ {name}",
        distance_km=distance,
        slots=slots,
    )


DAY_ONE = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
DAY_TWO = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def test_the_card_shares_one_time_column_across_showrooms() -> None:
    """Cột giờ là HỢP của mọi showroom — đổi showroom thì lưới không nhảy.

    Sếp 2026-08-28: *"khi 1 showroom không còn trống giờ đó thì ô chọn giờ đó sẽ
    bị mờ đi nên sẽ tận dụng được cột giờ, chỉ cần thay đổi cột các showroom"*.
    """

    gan = _row("Gần", (DAY_ONE, DAY_ONE.replace(hour=11)), distance=1.0)
    xa = _row("Xa", (DAY_ONE.replace(hour=10),), distance=5.0)

    card = build_test_drive_card("VF 5", [gan, xa], issue=_issue)

    assert card is not None
    assert [item.name for item in card.showrooms] == ["Gần", "Xa"]
    assert [day.date for day in card.days] == ["2026-08-28"]
    assert [time.label for time in card.days[0].times] == ["9h00", "10h00", "11h00"]


def test_only_free_cells_carry_a_button_code() -> None:
    """Ô hết chỗ VẮNG MẶT khỏi `options` — client suy ra "mờ" từ đúng một nguồn."""

    gan = _row("Gần", (DAY_ONE,))
    xa = _row("Xa", (DAY_ONE.replace(hour=10),), distance=5.0)

    card = build_test_drive_card("VF 5", [gan, xa], issue=_issue)

    assert card is not None
    free = {(option.showroom_id, option.scheduled_at) for option in card.options}
    assert ("id-Gần", DAY_ONE) in free
    # "Gần" không có khung 10h ⇒ ô đó phải mờ, tức không có mã nút.
    assert ("id-Gần", DAY_ONE.replace(hour=10)) not in free
    assert ("id-Xa", DAY_ONE.replace(hour=10)) in free
    # Mã nút do HỆ cấp, không phải chữ khách gõ: mỗi ô một mã, và mã của ô này
    # không dùng được cho ô kia. Phép ký thật (chữ ký, hạn, ràng buộc phiên) có
    # bộ riêng — `tests/agents/unit/domain/test_slot_token.py`.
    assert len({option.value for option in card.options}) == len(card.options)
    assert all(option.value for option in card.options)


def test_the_card_opens_on_the_earliest_day_and_a_showroom_free_that_day() -> None:
    """Mở sẵn ngày sớm nhất còn chỗ, và showroom gần nhất CÓ chỗ trong ngày đó.

    Chọn mặc định showroom gần nhất mà bỏ qua "có chỗ hôm đó không" sẽ mở ra một
    lưới mờ toàn bộ — thẻ trông như hỏng ngay từ giây đầu.
    """

    gan_nhung_ban = _row("Gần nhưng bận", (DAY_TWO,), distance=1.0)
    xa_nhung_ranh = _row("Xa nhưng rảnh", (DAY_ONE,), distance=9.0)

    card = build_test_drive_card("VF 5", [gan_nhung_ban, xa_nhung_ranh], issue=_issue)

    assert card is not None
    assert card.default_date == "2026-08-28"
    assert card.default_showroom_id == "id-Xa nhưng rảnh"
    assert [day.date for day in card.days] == ["2026-08-28", "2026-08-29"]


def test_no_free_slot_means_no_card() -> None:
    """Không còn khung nào thì KHÔNG dựng thẻ rỗng cho khách nhìn."""

    assert build_test_drive_card("VF 5", [], issue=_issue) is None
    assert build_test_drive_card("VF 5", [_row("Trống rỗng", ())], issue=_issue) is None


@pytest.mark.anyio
async def test_every_answer_with_free_slots_also_carries_the_card() -> None:
    """Có khung trống là có thẻ chọn — cả hai nhánh gọi ở `chain` đều đọc `card`.

    Nhánh sau đề xuất và nhánh vừa giải xong vị trí gọi cùng `answer()` này. Trả
    khung giờ mà quên thẻ nghĩa là một trong hai nhánh rơi về đúng cái danh sách
    chữ mà thẻ sinh ra để thay.
    """

    service = TestDriveServiceImpl(
        locations=FakeLocations([_place("Gần", 1.0, "Địa chỉ A"), _place("Xa", 6.0, "Địa chỉ B")]),
        bookings=FakeBookings(set()),
    )

    result = await service.answer(
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        user_message="vâng",
        vehicle_name="VF 8",
        vehicle_type=VehicleType.CAR,
        known_location=UserLocation(latitude=21.0, longitude=105.0, source="browser"),
    )

    assert result.slot_options
    assert result.card is not None
    # Giữ CẢ HAI showroom còn chỗ, không dừng ở cái đầu tiên.
    assert [item.name for item in result.card.showrooms] == ["Gần", "Xa"]
    # Từ hai showroom trở lên, chữ KHÔNG chép lại địa chỉ nữa — thẻ đã bày rồi.
    assert "Địa chỉ A" not in result.answer


@pytest.mark.anyio
async def test_slot_hours_follow_vietnam_time_not_the_process_clock() -> None:
    """Khung giờ theo giờ KHÁCH, dù tiến trình chạy múi nào.

    BUG THẬT prod 2026-08-28: container backend chạy UTC (`TZ` không đặt), nên
    lưới sinh ra 9h–18h UTC = 16h–01h giờ Việt Nam — mời khách tới showroom lúc
    một giờ sáng, và nhãn ngày lệch một ngày.
    """

    service = TestDriveServiceImpl(
        locations=FakeLocations([_place("Gần", 1.0, "Địa chỉ A")]),
        bookings=FakeBookings(set()),
    )

    result = await service.answer(
        session_id="11111111-1111-1111-1111-111111111111",
        customer_id="customer-1",
        user_message="vâng",
        vehicle_name="VF 8",
        vehicle_type=VehicleType.CAR,
        known_location=UserLocation(latitude=21.0, longitude=105.0, source="browser"),
    )

    assert result.card is not None
    moments = [time.scheduled_at for day in result.card.days for time in day.times]
    assert moments
    assert {moment.utcoffset() for moment in moments} == {VIETNAM_TZ.utcoffset(None)}
    assert all(9 <= moment.hour < 18 for moment in moments)


def test_the_day_label_always_carries_the_date() -> None:
    """Nhãn ngày luôn kèm ngày tháng — "hôm nay" trong tin nhắn cũ là chữ nói dối."""

    today = datetime(2026, 8, 28, 8, 0, tzinfo=VIETNAM_TZ)

    assert format_day_label(today.replace(hour=9), today=today) == "Hôm nay 28/08"
    assert format_day_label(today + timedelta(days=1), today=today) == "Ngày mai 29/08"
    assert format_day_label(today + timedelta(days=2), today=today) == "30/08"
