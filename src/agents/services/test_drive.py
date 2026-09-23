"""[TEST_DRIVE] Use case gợi ý showroom gần + khung giờ trống cho đặt lịch lái thử.

Tất định: showroom đọc qua `NearbyLocationPort` (đã xếp theo khoảng cách), khung
giờ sinh từ `open_time`/`close_time` của showroom rồi lọc giờ đã đầy bằng
`count_active_at`. Không gọi LLM — cùng nhóm với `CATALOG_BROWSE`/`COMPARE_VEHICLES`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import date as date_type
from datetime import datetime
from typing import Final, Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.agents.contracts import (
    TestDriveCardView,
    TestDriveDayView,
    TestDriveOptionView,
    TestDriveResult,
    TestDriveShowroomView,
    TestDriveSlotOption,
    TestDriveTimeView,
)
from src.agents.domain.nearby_location import (
    LocationKind,
    UserLocation,
    format_distance,
    location_types_for,
    pending_for_user_location,
)
from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.reply_format import bold
from src.agents.domain.test_drive import (
    MAX_BUTTON_SLOTS,
    MAX_SHOWROOMS,
    MAX_SLOTS_PER_DAY,
    ShowroomSlots,
    candidate_slots,
    format_date,
    format_day_label,
    format_slot,
    now_in_vietnam,
)
from src.agents.domain.values import VehicleType
from src.agents.ports import NearbyLocationPort
from src.agents.services.operations.booking import BookingUnitOfWork
from src.agents.services.slot_token import issue_slot_token

logger = logging.getLogger(__name__)

#: Index UNIQUE giữ sức chứa một khung giờ (migration `agent_0031`). Chỉ vi phạm
#: ĐÚNG nó mới có nghĩa "khung vừa đầy" — xem `BookingUnitOfWorkSlotCounter.book`.
SLOT_UNIQUE_INDEX: Final[str] = "ix_test_drive_bookings_showroom_time"

TEST_DRIVE_PENDING_MARKER = "test_drive_vehicle_name"
TEST_DRIVE_VEHICLE_TYPE = "test_drive_vehicle_type"

ASK_LOCATION_FOR_TEST_DRIVE = (
    "Để gợi ý showroom gần nhất và khung giờ lái thử, anh/chị cho em biết vị trí (quận/huyện, tỉnh thành) ạ."
)


class BookingSlotSource(Protocol):
    """Đếm lượt đặt đã tồn tại cho một showroom tại một giờ, và GHI lượt mới.

    `book` nằm cùng chỗ với `count_active_at` một cách cố ý: đặt lịch mà không
    đếm lại sức chứa là hai khách cùng nhận một khung giờ.
    """

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int: ...

    async def book(
        self, *, customer_id: str, vehicle_id: UUID, showroom: str, scheduled_at: datetime
    ) -> UUID | None: ...


def _is_slot_conflict(error: IntegrityError) -> bool:
    """Đúng index sức chứa khung giờ bị vi phạm, hay một lỗi dữ liệu khác.

    Phải lần theo CHUỖI ngoại lệ: driver bọc `asyncpg.UniqueViolationError` vào
    một `IntegrityError` của phương ngữ, rồi SQLAlchemy bọc thêm một lớp nữa —
    nên `error.orig.constraint_name` chỉ có ở bản gốc trong cùng, không có ở lớp
    ngoài. Đọc mỗi lớp ngoài là kết luận "không phải" cho đúng ca đang xét.

    Rơi về so chuỗi là cố ý và vẫn HẸP: nó tìm đúng tên index, không tìm chữ
    "unique" chung chung.
    """

    seen: list[BaseException | None] = [error, error.orig]
    current = error.orig
    for _ in range(4):
        if current is None:
            break
        current = current.__cause__ or current.__context__
        seen.append(current)
    for item in seen:
        if item is not None and getattr(item, "constraint_name", None) == SLOT_UNIQUE_INDEX:
            return True
    return SLOT_UNIQUE_INDEX in str(error)


class BookingUnitOfWorkSlotCounter:
    """Bọc `BookingUnitOfWork` thành `BookingSlotSource` cho service test-drive."""

    def __init__(self, unit_of_work: BookingUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int:
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.count_active_at(showroom, scheduled_at)

    async def busy_slots_between(self, *, showroom: str, start: datetime, end: datetime) -> list[datetime]:
        """Khung đã đầy trong khoảng — một truy vấn cho cả showroom."""

        async with self._unit_of_work.transaction() as transaction:
            return await transaction.bookings.busy_slots_between(showroom=showroom, start=start, end=end)

    async def book(self, *, customer_id: str, vehicle_id: UUID, showroom: str, scheduled_at: datetime) -> UUID | None:
        """Ghi lịch, hoặc `None` khi khung giờ vừa đầy.

        Đếm lại sức chứa TRONG cùng transaction với lần ghi: đếm ở một transaction
        rồi ghi ở transaction khác là để ngỏ đúng khoảng giữa hai khách bấm cùng
        một nút.
        """

        # Bấm ĐÚP không phải là mất chỗ. Nút khung giờ rất dễ bấm hai lần, và
        # trả "khung này vừa có người đặt mất" cho chính người vừa đặt là nói dối
        # họ rồi đẩy họ đi chọn khung khác trong khi lịch của họ đã có.
        mine = await self._existing_booking(customer_id, showroom, scheduled_at)
        if mine is not None:
            return mine
        try:
            return await self._create(customer_id, vehicle_id, showroom, scheduled_at)
        except IntegrityError as error:
            # Đua THẬT: cả hai transaction cùng đếm ra 0 rồi cùng ghi. Sức chứa ở
            # mức ứng dụng không đóng được khoảng đó — chỉ index UNIQUE
            # `ix_test_drive_bookings_showroom_time` (agent_0031) đóng được.
            #
            # Chỉ ĐÚNG index đó mới có nghĩa "khung vừa đầy". `None` được
            # `chain._book_test_drive` đọc thành câu "khung giờ này vừa có người
            # đặt mất", nên nuốt một khoá ngoại hỏng hay một `CHECK` sai vào cùng
            # câu ấy là kể một lỗi dữ liệu cho khách như chuyện chỗ đã kín — và
            # lỗi bị giấu sau một câu trấn an là lỗi không ai đi tìm.
            if not _is_slot_conflict(error):
                raise
            # Đọc LẠI trước khi kết luận "hết chỗ".
            #
            # Kẻ thua có thể chính là khách vừa bấm đúp. Trả `None` lúc đó là nói
            # với chính người vừa đặt rằng "khung này vừa có người đặt mất" — một
            # câu nói dối, và nó đẩy họ đi chọn khung khác trong khi lịch của họ
            # đã có. Người thắng đã commit xong nên hàng chắc chắn đọc được.
            mine_now = await self._existing_booking(customer_id, showroom, scheduled_at)
            if mine_now is not None:
                return mine_now
            logger.info("test_drive: khung %s %s vua day trong luc ghi", showroom, scheduled_at.isoformat())
            return None

    async def _existing_booking(self, customer_id: str, showroom: str, scheduled_at: datetime) -> UUID | None:
        async with self._unit_of_work.transaction() as transaction:
            reader = getattr(transaction.bookings, "booking_of", None)
            if not callable(reader):
                return None
            return await reader(customer_id=customer_id, showroom=showroom, scheduled_at=scheduled_at)

    async def _create(self, customer_id: str, vehicle_id: UUID, showroom: str, scheduled_at: datetime) -> UUID | None:
        async with self._unit_of_work.transaction() as transaction:
            # KHÔNG còn chặn "khung đã có người" (Sếp 2026-08-31): showroom nhiều
            # xe và nhiều tư vấn viên, bao nhiêu khách đặt một khung cũng nhận.
            booking_id = await transaction.bookings.create_booking(
                run_id=None,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                advisor_id=None,
                showroom=showroom,
                scheduled_at=scheduled_at,
            )
            await transaction.notices.create_notice(
                title="Yêu cầu lái thử mới từ khách hàng",
                content=(
                    f"Khách {customer_id} đặt lái thử tại {showroom} lúc "
                    f"{scheduled_at.strftime('%d/%m/%Y %H:%M')} (đặt qua trợ lý)."
                ),
                priority="URGENT",
                created_by="agent",
            )
            return booking_id


class TestDriveServiceImpl:
    """Trả câu gợi ý showroom + khung giờ, hoặc hỏi vị trí khi chưa biết."""

    def __init__(self, *, locations: NearbyLocationPort, bookings: BookingSlotSource) -> None:
        self._locations = locations
        self._bookings = bookings
        self._showroom_addresses: dict[str, str] = {}

    async def answer(
        self,
        *,
        user_message: str,
        vehicle_name: str,
        vehicle_type: VehicleType,
        known_location: UserLocation | None,
        session_id: str,
        customer_id: str,
    ) -> TestDriveResult:
        kinds = _kinds_for(vehicle_type)
        if known_location is None:
            return TestDriveResult(
                answer=ASK_LOCATION_FOR_TEST_DRIVE,
                needs_location=True,
                pending_request=_pending_test_drive_location(
                    user_message=user_message,
                    vehicle_name=vehicle_name,
                    vehicle_type=vehicle_type,
                    kinds=kinds,
                ),
            )
        places = await self._locations.nearest(
            latitude=known_location.latitude,
            longitude=known_location.longitude,
            radius_km=50.0,
            location_types=location_types_for(kinds),
            limit=MAX_SHOWROOMS,
        )
        # GIỮ cả ba showroom, không dừng ở cái đầu tiên còn chỗ.
        #
        # Sếp 2026-08-28: thẻ chọn phải bày ba showroom gần nhất để khách tự cân
        # giữa "gần hơn" và "giờ đẹp hơn". Bản trước `break` ngay showroom đầu,
        # nên khách chỉ có đúng một nơi và không có gì để cân.
        rows: list[ShowroomSlots] = []
        for place in places:
            row = await self._with_slots(place)
            if row.slots:
                rows.append(row)
        self._showroom_addresses.update({row.showroom_name: row.address for row in rows})
        if not rows:
            return TestDriveResult(
                answer=(
                    f"Dạ hiện em chưa tìm thấy showroom có khung giờ trống gần vị trí "
                    f"anh/chị. Em sẽ nhờ tư vấn viên liên hệ hỗ trợ đặt lịch lái thử "
                    f"{vehicle_name} ạ."
                )
            )
        issue = self._issuer(session_id=session_id, customer_id=customer_id)
        return TestDriveResult(
            answer=_render(vehicle_name, rows),
            slot_options=_slot_options(rows, issue),
            # Chỉ chở ô giờ của NGÀY MẶC ĐỊNH. Cửa sổ 7 ngày × 6 khung × 3
            # showroom là 126 ô trong một lượt chat; thẻ ba ngày trước đây đã 54.
            # Ngày khác nạp khi khách bấm sang.
            card=build_test_drive_card(vehicle_name, rows, issue=issue, only_date=_default_card_date(rows)),
        )

    async def availability(
        self,
        *,
        latitude: float,
        longitude: float,
        vehicle_type: VehicleType,
        on_date: date_type,
        session_id: str,
        customer_id: str,
    ) -> tuple[TestDriveOptionView, ...]:
        """Ô giờ còn trống của ĐÚNG một ngày, cho mọi showroom quanh khách.

        Nốt còn thiếu của bước nạp lười. Lượt chat chỉ chở ô của ngày mặc định
        (126 ô → 18), nhưng thẻ vẫn bày đủ bảy ngày — mà client không có đường
        nào xin sáu ngày còn lại. Khách bấm sang ngày thứ tư thì mọi khung đều
        mờ: payload nhẹ đi, chức năng thì gãy.

        Dùng LẠI đúng `_with_slots` của lượt chat, không viết một phép tính thứ
        hai. Hai bản tính ô trống là hai chỗ để lệch, và chỗ lệch ấy chỉ lộ ra
        khi khách tới showroom.

        `latitude`/`longitude` do TẦNG ROUTE đọc từ phiên, không nhận từ client:
        cùng nguồn với lượt chat đã dựng thẻ, nên không ai tự chọn được mình
        đứng ở đâu để moi lịch của một nơi khác.

        Ngoài cửa sổ đặt lịch thì trả RỖNG chứ không ném — ngày đến từ nút trên
        trình duyệt, và một ngày lạ phải dẫn tới "hôm đó không còn khung nào",
        không phải một màn hình hỏng.
        """

        places = await self._locations.nearest(
            latitude=latitude,
            longitude=longitude,
            radius_km=50.0,
            location_types=location_types_for(_kinds_for(vehicle_type)),
            limit=MAX_SHOWROOMS,
        )
        issue = self._issuer(session_id=session_id, customer_id=customer_id)
        options: list[TestDriveOptionView] = []
        for place in places:
            row = await self._with_slots(place)
            self._showroom_addresses.setdefault(row.showroom_name, row.address)
            options.extend(
                TestDriveOptionView(
                    showroom_id=row.showroom_id,
                    scheduled_at=slot,
                    value=issue(row.showroom_name, slot),
                )
                for slot in row.slots
                if slot.date() == on_date
            )
        return tuple(options)

    def _issuer(self, *, session_id: str, customer_id: str) -> Callable[[str, datetime], str]:
        """Hàm cấp giấy phép cho MỘT phiên/khách, dùng lại cho mọi ô của lượt đó.

        Cấp ở đây chứ không ở chỗ gọi: chỉ tầng service biết khoá, và chỗ gọi tự
        ghép chuỗi chính là cách lỗ hổng cũ sống sót.
        """

        issued_at = now_in_vietnam()
        return lambda showroom, when: issue_slot_token(
            showroom=showroom,
            scheduled_at=when,
            session_id=session_id,
            customer_id=customer_id,
            issued_at=issued_at,
        )

    async def book(self, *, customer_id: str, vehicle_id: UUID, showroom: str, scheduled_at: datetime) -> UUID | None:
        """Chốt một khung giờ khách vừa chọn. `None` khi khung vừa đầy."""

        return await self._bookings.book(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            showroom=showroom,
            scheduled_at=scheduled_at,
        )

    async def _busy_slots(self, showroom: str, slots: tuple[datetime, ...]) -> set[datetime]:
        """Không còn khung nào bị coi là ĐẦY (Sếp 2026-08-31: bỏ giới hạn đặt).

        Showroom nhiều xe và nhiều tư vấn viên — một khung giờ nhận bao nhiêu
        khách cũng được, nên mọi ô giờ trong cửa sổ đều bấm được. Giữ chữ ký để
        chỗ gọi không đổi; muốn khôi phục giới hạn thì đọc lại lịch sử hàm này.
        """

        del showroom, slots
        return set()

    async def _with_slots(self, place) -> ShowroomSlots:
        # Giờ VIỆT NAM, không phải giờ tiến trình: container prod chạy UTC, và
        # `datetime.now().astimezone()` ở đó sinh ra lưới 9h–18h UTC — tức
        # 16h–01h giờ khách (`domain/test_drive.VIETNAM_TZ`).
        slots = candidate_slots(open_time=place.open_time, close_time=place.close_time, now=now_in_vietnam())
        busy = await self._busy_slots(place.name, slots)
        # Trần tính THEO NGÀY, không theo tổng.
        #
        # Bản trước dừng sau sáu khung ĐẦU TIÊN còn trống, tức gần như luôn dừng
        # trong ngày hôm nay — nên nút "Xem ngày khác" sẽ không có gì để xem.
        per_day: dict[str, int] = {}
        free: list[datetime] = []
        for slot in slots:
            if slot in busy:
                continue
            key = slot.date().isoformat()
            if per_day.get(key, 0) >= MAX_SLOTS_PER_DAY:
                continue
            per_day[key] = per_day.get(key, 0) + 1
            free.append(slot)
        return ShowroomSlots(
            showroom_id=place.id,
            showroom_name=place.name,
            address=place.address,
            distance_km=place.distance_km,
            slots=tuple(free),
            latitude=getattr(place, "latitude", None),
            longitude=getattr(place, "longitude", None),
        )


def _kinds_for(vehicle_type: VehicleType) -> tuple[LocationKind, ...]:
    if vehicle_type is VehicleType.ELECTRIC_MOTORBIKE:
        return (LocationKind.SHOWROOM_MOTORBIKE,)
    return (LocationKind.SHOWROOM_CAR,)


def _render(vehicle_name: str, rows: list[ShowroomSlots]) -> str:
    """Câu dẫn cho bước chọn khung giờ — KHÔNG chép lại danh sách giờ.

    Sếp 2026-08-27: phần hiển thị bước đặt lịch chưa gọn. Bản cũ in mọi khung giờ
    thành chữ RỒI hiện đúng ngần ấy giờ một lần nữa dưới dạng nút — khách đọc hai
    lần cùng một danh sách, và cái đọc được thì không bấm được.

    Giờ chỉ nằm trên NÚT (`_slot_options`), vì chỉ nút mới chốt được lịch: mã nút
    mang cả showroom lẫn mốc thời gian nên bước này không phải đoán gì
    (`domain/test_drive_booking`). Chữ chỉ còn nói ba điều khách cần để quyết —
    ở đâu, cách bao xa, địa chỉ nào.

    Số thứ tự cũng bỏ: `answer()` chỉ trả về MỘT showroom (`rows = [row]; break`),
    nên "1." và chữ "các showroom" đều nói sai về thứ đang hiện.
    """

    if not rows:
        return ""
    lead = (
        f"Dạ em tìm được showroom gần anh/chị nhất để lái thử {vehicle_name} ạ:"
        if len(rows) == 1
        else f"Dạ em gợi ý {len(rows)} showroom gần anh/chị để lái thử {vehicle_name} ạ:"
    )
    lines = [lead]
    # Tên + địa chỉ chỉ in ra chữ khi CHỈ CÓ MỘT showroom. Từ hai trở lên thì thẻ
    # chọn (`build_test_drive_card`) đã bày đủ tên, khoảng cách và địa chỉ ngay
    # cạnh cột giờ — in lại thành chữ là đúng lỗi Sếp bắt 2026-08-27: khách đọc
    # hai lần cùng một danh sách, mà cái đọc được thì không bấm được.
    if len(rows) == 1:
        row = rows[0]
        lines.append(f"\n{bold(row.showroom_name)} — cách {format_distance(row.distance_km)}")
        lines.append(row.address)
    lines.append("\nAnh/chị chọn giúp em showroom và khung giờ bên dưới ạ.")
    return "\n".join(lines)


def _group_by_day(slots: tuple[datetime, ...]) -> list[tuple[str, list[datetime]]]:
    grouped: list[tuple[str, list[datetime]]] = []
    for slot in slots:
        label = format_date(slot)
        if grouped and grouped[-1][0] == label:
            grouped[-1][1].append(slot)
        else:
            grouped.append((label, [slot]))
    return grouped


def _pending_test_drive_location(
    *, user_message: str, vehicle_name: str, vehicle_type: VehicleType, kinds: tuple[LocationKind, ...]
) -> PendingSlotRequest:
    """Keep test-drive context while reusing pending user-location flow."""

    pending = pending_for_user_location(user_message=user_message, kinds=kinds)
    return replace(
        pending,
        partial_form={
            **pending.partial_form,
            TEST_DRIVE_PENDING_MARKER: vehicle_name,
            TEST_DRIVE_VEHICLE_TYPE: vehicle_type.value,
        },
    )


def _default_card_date(rows: list[ShowroomSlots]) -> date_type | None:
    """Ngày SỚM NHẤT còn chỗ trong bất kỳ showroom nào.

    Cùng ngày mà `build_test_drive_card` sẽ chọn làm mặc định — tính ở đây để
    truyền vào làm bộ lọc, thay vì để hàm kia tự chọn rồi mới cắt.
    """

    moments = sorted(slot for row in rows for slot in row.slots)
    return moments[0].date() if moments else None


def build_test_drive_card(
    vehicle_name: str,
    rows: list[ShowroomSlots],
    *,
    issue: Callable[[str, datetime], str],
    only_date: date_type | None = None,
) -> TestDriveCardView | None:
    """Lưới chọn: cột showroom × cột giờ dùng chung. `None` khi không còn khung nào.

    THUẦN: chỉ đọc `rows`, không chạm database — nên test được thẳng, không cần
    dựng port giả.

    **Cột giờ là HỢP của mọi showroom** (Sếp 2026-08-28). Ô nào showroom đang
    chọn không còn chỗ thì mờ đi, chứ cột không co lại: đổi showroom mà lưới nhảy
    thì khách mất mốc để so.

    **Chỉ ô CÒN CHỖ mới nằm trong `options`.** Client suy ra "mờ" bằng phép vắng
    mặt thay vì đọc một cờ `available` riêng — một nguồn sự thật thì không có chỗ
    nào để hai bản lệch nhau.

    `only_date` — NẠP LƯỜI
    ----------------------
    Cửa sổ nay là 7 ngày. Gửi hết ô giờ của cả bảy là tới **189 ô** trong một
    lượt chat, trong khi thẻ ba ngày hôm nay đã 54. Truyền `only_date` thì
    `options` chỉ chở ô của ĐÚNG ngày đó.

    `days` vẫn liệt kê ĐỦ bảy ngày: cắt ô giờ không được cắt luôn danh sách ngày,
    nếu không "nạp lười" biến thành "chỉ có một ngày" và khách không biết mình
    chọn được gì.
    """

    rows = [row for row in rows if row.slots]
    if not rows:
        return None
    showrooms = tuple(
        TestDriveShowroomView(
            showroom_id=row.showroom_id,
            name=row.showroom_name,
            address=row.address,
            distance_label=format_distance(row.distance_km),
            lat=row.latitude,
            lng=row.longitude,
            distance_km=row.distance_km,
        )
        for row in rows
    )
    moments = sorted({slot for row in rows for slot in row.slots})
    days: list[TestDriveDayView] = []
    for moment in moments:
        key = moment.date().isoformat()
        time_view = TestDriveTimeView(scheduled_at=moment, label=format_slot(moment))
        if days and days[-1].date == key:
            days[-1] = replace(days[-1], times=(*days[-1].times, time_view))
            continue
        days.append(TestDriveDayView(date=key, label=format_day_label(moment), times=(time_view,)))
    shown_date = only_date.isoformat() if only_date is not None else None
    options = tuple(
        TestDriveOptionView(
            showroom_id=row.showroom_id,
            scheduled_at=slot,
            value=issue(row.showroom_name, slot),
        )
        for row in rows
        for slot in row.slots
        if shown_date is None or slot.date().isoformat() == shown_date
    )
    # Mặc định mở ở ngày SỚM NHẤT còn chỗ, và ở showroom GẦN NHẤT còn chỗ trong
    # đúng ngày đó — nếu không thì thẻ mở ra với một lưới mờ toàn bộ.
    first_day = shown_date or days[0].date
    default_row = next(
        (row for row in rows if any(slot.date().isoformat() == first_day for slot in row.slots)),
        rows[0],
    )
    return TestDriveCardView(
        vehicle_name=vehicle_name,
        showrooms=showrooms,
        days=tuple(days),
        options=options,
        default_showroom_id=default_row.showroom_id,
        default_date=first_day,
    )


__all__ = ["BookingSlotSource", "TestDriveServiceImpl", "build_test_drive_card"]


def _slot_options(rows: list[ShowroomSlots], issue: Callable[[str, datetime], str]) -> tuple[TestDriveSlotOption, ...]:
    """Từng khung giờ trống thành một lựa chọn CÓ CẤU TRÚC.

    `_render` ở trên viết cho người đọc; hàm này giữ đúng showroom và đúng mốc
    thời gian để dựng nút. Hai bản đọc cùng một dữ liệu, sinh từ CÙNG `rows` nên
    không lệch nhau được.

    Trần `MAX_BUTTON_SLOTS`: mỗi khung là một nút, mà một màn chat đầy nút thì
    khách không chọn nổi — và khung đầu bao giờ cũng là khung gần nhất.
    """

    options: list[TestDriveSlotOption] = []
    for row in rows:
        for slot in row.slots:
            options.append(
                TestDriveSlotOption(
                    showroom=row.showroom_name,
                    scheduled_at=slot,
                    label=f"{format_date(slot)} {format_slot(slot)}",
                    value=issue(row.showroom_name, slot),
                )
            )
            if len(options) >= MAX_BUTTON_SLOTS:
                return tuple(options)
    return tuple(options)
