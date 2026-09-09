"""A8-2 acceptance tests — test-drive booking, slot limit, and one-transaction writes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.booking_routes import booking_operations, router
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.security import StaffIdentity, current_staff
from src.agents.models import (
    AgentRunRow,
    ConversationSessionRow,
    InternalNoticeRow,
    ReviewQueueRow,
)
from src.agents.models import TestDriveBookingRow as BookingRow
from src.agents.services.operations.booking import BookingOperations
from src.auth.domain.authorization import Role

NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
SLOT = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
SHOWROOM = "VinFast Long Bien"
VEHICLE_ID = uuid4()


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class ExplodingNoticeRepository:
    """Fake implementing the notice surface, failing exactly at the write step."""

    async def create_notice(self, title: str, content: str, priority: str, created_by: str) -> UUID:
        raise RuntimeError("notice store is down")

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None:
        raise NotImplementedError

    async def exists(self, notice_id: UUID) -> bool:
        raise NotImplementedError

    async def list_for(self, advisor_id: str) -> list[object]:
        raise NotImplementedError


async def _seed_run(engine: AsyncEngine, *, review_status: str = "APPROVED") -> UUID:
    """A run whose queue item is in `review_status` — stands in for A6-1 until Ráp 3."""
    session_id = uuid4()
    run_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id="customer-1",
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="APPROVED",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=uuid4(),
                session_id=session_id,
                run_id=run_id,
                content="ban nhap",
                status=review_status,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return run_id


async def _seed_booking_at(engine: AsyncEngine, *, scheduled_at: datetime, status: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(BookingRow).values(
                booking_id=uuid4(),
                customer_id="customer-khac",
                vehicle_id=uuid4(),
                showroom=SHOWROOM,
                scheduled_at=scheduled_at,
                status=status,
                created_at=NOW,
                updated_at=NOW,
            )
        )


def _build_app(engine: AsyncEngine, *, break_notices: bool = False) -> FastAPI:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FrozenClock(NOW)

    def factory(session: AsyncSession) -> object:
        transaction = build_agent_transaction(session, clock=clock)
        if break_notices:
            return replace(transaction, notices=ExplodingNoticeRepository())  # type: ignore[arg-type]
        return transaction

    unit_of_work = AgentUnitOfWork(session_factory=session_factory, transaction_factory=factory)
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[booking_operations] = lambda: BookingOperations(unit_of_work=unit_of_work)
    application.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="advisor-a", role=Role.ADVISOR)
    return application


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    return _build_app(migrated_engine)


async def _book(app: FastAPI, run_id: UUID, *, scheduled_at: datetime = SLOT) -> tuple[int, object]:
    payload = {
        "run_id": str(run_id),
        "vehicle_id": str(VEHICLE_ID),
        "showroom": SHOWROOM,
        "scheduled_at": scheduled_at.isoformat(),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.post("/agent/bookings", json=payload)
    body = response.json() if response.content else None
    return response.status_code, body


async def _count(engine: AsyncEngine, table: type) -> int:
    async with engine.connect() as connection:
        total = await connection.scalar(select(func.count()).select_from(table))
    return int(total or 0)


@pytest.mark.asyncio
async def test_booking_from_a_run_that_is_not_approved_is_blocked(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    run_id = await _seed_run(migrated_engine, review_status="PENDING")

    # When
    status_code, _body = await _book(app, run_id)

    # Then
    assert status_code == 409
    assert await _count(migrated_engine, BookingRow) == 0


@pytest.mark.asyncio
async def test_booking_a_slot_that_is_already_full_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    run_id = await _seed_run(migrated_engine)
    await _seed_booking_at(migrated_engine, scheduled_at=SLOT, status="CONFIRMED")

    # When
    status_code, _body = await _book(app, run_id)

    # Then
    assert status_code == 409
    assert await _count(migrated_engine, BookingRow) == 1


@pytest.mark.asyncio
async def test_a_failing_notice_write_rolls_the_booking_back(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given — the notice step is made to fail on purpose
    run_id = await _seed_run(migrated_engine)
    app = _build_app(migrated_engine, break_notices=True)

    # When
    with pytest.raises(RuntimeError):
        await _book(app, run_id)

    # Then — no orphan booking left behind
    assert await _count(migrated_engine, BookingRow) == 0
    assert await _count(migrated_engine, InternalNoticeRow) == 0


@pytest.mark.asyncio
async def test_booking_an_approved_run_writes_booking_and_notice_together(
    app: FastAPI, migrated_engine: AsyncEngine
) -> None:
    # Given
    run_id = await _seed_run(migrated_engine)

    # When
    status_code, _body = await _book(app, run_id)

    # Then
    assert status_code == 201
    assert await _count(migrated_engine, BookingRow) == 1
    assert await _count(migrated_engine, InternalNoticeRow) == 1
    async with migrated_engine.connect() as connection:
        row = (await connection.execute(select(BookingRow))).one()
    assert row.customer_id == "customer-1"
    assert row.advisor_id == "advisor-a"


@pytest.mark.asyncio
async def test_a_cancelled_booking_does_not_hold_the_slot(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: cancelled bookings must not count toward capacity
    run_id = await _seed_run(migrated_engine)
    await _seed_booking_at(migrated_engine, scheduled_at=SLOT, status="CANCELLED")

    # When
    status_code, _body = await _book(app, run_id)

    # Then
    assert status_code == 201


@pytest.mark.asyncio
async def test_a_different_time_slot_is_still_free(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given
    run_id = await _seed_run(migrated_engine)
    await _seed_booking_at(migrated_engine, scheduled_at=SLOT, status="CONFIRMED")

    # When
    status_code, _body = await _book(app, run_id, scheduled_at=SLOT + timedelta(hours=1))

    # Then
    assert status_code == 201


@pytest.mark.asyncio
async def test_booking_an_unknown_run_is_rejected(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — negative case: nothing seeded for this identifier
    # When
    status_code, _body = await _book(app, uuid4())

    # Then
    assert status_code == 404
    assert await _count(migrated_engine, BookingRow) == 0


# ── Hai khách bấm cùng một khung giờ ──────────────────────────────────────────


async def _live_booking(engine: AsyncEngine, customer: str, *, slot: datetime = SLOT) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(BookingRow).values(
                booking_id=uuid4(),
                customer_id=customer,
                vehicle_id=VEHICLE_ID,
                showroom=SHOWROOM,
                scheduled_at=slot,
                status="REQUESTED",
                created_at=NOW,
                updated_at=NOW,
            )
        )


@pytest.mark.asyncio
async def test_the_database_itself_refuses_two_live_bookings_for_one_slot(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """`SLOT_CAPACITY = 1` phải được CHÍNH CSDL giữ, không chỉ mã ứng dụng.

    `book` đếm rồi ghi trong cùng một transaction, nhưng ở mức cô lập mặc định
    (READ COMMITTED) hai transaction song song vẫn cùng đếm ra 0 rồi cùng ghi.
    Chỉ một ràng buộc duy nhất mới đóng được khoảng đó — đúng khoảng thời gian
    hai khách bấm cùng một nút.

    Hậu quả nếu để hở: hai khách cùng được nhắn "đã đặt lịch", cùng tới showroom
    một giờ, và không ai biết cho tới lúc họ có mặt.
    """

    from sqlalchemy.exc import IntegrityError

    await _live_booking(migrated_engine, "customer-1")

    with pytest.raises(IntegrityError):
        await _live_booking(migrated_engine, "customer-2")


@pytest.mark.asyncio
async def test_a_cancelled_row_leaves_the_slot_bookable_again(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Ràng buộc mới KHÔNG được khoá một khung đã huỷ — nếu không thì huỷ lịch
    xong khung đó chết vĩnh viễn."""

    async with migrated_engine.begin() as connection:
        await connection.execute(
            insert(BookingRow).values(
                booking_id=uuid4(),
                customer_id="customer-1",
                vehicle_id=VEHICLE_ID,
                showroom=SHOWROOM,
                scheduled_at=SLOT,
                status="CANCELLED",
                created_at=NOW,
                updated_at=NOW,
            )
        )

    await _live_booking(migrated_engine, "customer-2")

    async with migrated_engine.connect() as connection:
        live = await connection.execute(
            select(func.count()).select_from(BookingRow).where(BookingRow.status != "CANCELLED")
        )
    assert live.scalar_one() == 1


@pytest.mark.asyncio
async def test_two_customers_racing_for_one_slot_leave_exactly_one_booking(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Đường của KHUNG CHAT: kẻ thua phải nhận `None`, không phải một ngoại lệ.

    `chain._book_test_drive` đọc `None` thành câu "khung giờ này vừa có người đặt
    mất ạ". Để ngoại lệ thoát ra thì khách nhận câu "chưa đặt được, em nhờ tư vấn
    viên" — đọc như hệ thống hỏng, trong khi thật ra chỉ là chậm chân.
    """

    import asyncio

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)

    def factory(session: AsyncSession):
        return build_agent_transaction(session, clock=clock)

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    results = await asyncio.gather(
        booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        booker.book(customer_id="customer-2", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        return_exceptions=True,
    )

    assert not any(isinstance(item, BaseException) for item in results), results
    assert sum(1 for item in results if item is not None) == 1

    async with migrated_engine.connect() as connection:
        live = await connection.execute(
            select(func.count()).select_from(BookingRow).where(BookingRow.status != "CANCELLED")
        )
    assert live.scalar_one() == 1


# ── Đua THẬT: ép hai transaction cùng qua `count = 0` ────────────────────────


@pytest.mark.asyncio
async def test_ke_thua_cuoc_dua_nhan_none_chu_khong_phai_ngoai_le(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Rào ép ĐÚNG khoảng hở, không trông vào may rủi của bộ lập lịch.

    Bộ test trước dùng `asyncio.gather` trần — nó có thể chạy đủ tuần tự để
    `count_active_at` của người thứ hai đã thấy hàng của người thứ nhất, và test
    xanh mà chưa hề chạm vào khoảng hở. Ở đây hai transaction bị GIỮ lại sau khi
    cùng đếm ra 0, rồi mới thả cho ghi.

    Kẻ thua phải nhận `None` — `chain._book_test_drive` đọc `None` thành "khung
    giờ này vừa có người đặt mất". Để `IntegrityError` thoát ra thì khách nhận
    "chưa đặt được, em nhờ tư vấn viên" — đọc như hệ thống hỏng, và kéo một
    người vào việc không cần người.
    """

    import asyncio

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)
    counted = asyncio.Event()
    both_counted = asyncio.Barrier(2)

    def factory(session: AsyncSession):
        transaction = build_agent_transaction(session, clock=clock)
        bookings = transaction.bookings
        original = bookings.count_active_at

        async def counting(showroom: str, scheduled_at: datetime) -> int:
            result = await original(showroom, scheduled_at)
            counted.set()
            # Giữ cả hai lại ĐÚNG sau khi đếm: đây là khoảng mà sức chứa mức ứng
            # dụng không còn nghĩa gì.
            await both_counted.wait()
            return result

        bookings.count_active_at = counting  # type: ignore[method-assign]
        return transaction

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    results = await asyncio.gather(
        booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        booker.book(customer_id="customer-2", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        return_exceptions=True,
    )

    assert not any(isinstance(item, BaseException) for item in results), results
    assert sum(1 for item in results if item is not None) == 1

    async with migrated_engine.connect() as connection:
        live = await connection.execute(
            select(func.count()).select_from(BookingRow).where(BookingRow.status != "CANCELLED")
        )
    assert live.scalar_one() == 1


@pytest.mark.asyncio
async def test_cung_khach_bam_hai_lan_nhan_lai_dung_lich_cu(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Bấm hai lần KHÔNG phải là mất chỗ.

    Nút khung giờ rất dễ bấm đúp. Trả "khung giờ này vừa có người đặt mất" cho
    chính người vừa đặt là nói dối họ, và đẩy họ đi chọn một khung khác trong
    khi lịch của họ đã có.
    """

    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)

    def factory(session: AsyncSession):
        return build_agent_transaction(session, clock=clock)

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    first = await booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT)
    second = await booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT)

    assert first is not None
    assert second == first, "cùng khách, cùng khung ⇒ trả lại đúng lịch cũ"

    async with migrated_engine.connect() as connection:
        live = await connection.execute(
            select(func.count()).select_from(BookingRow).where(BookingRow.status != "CANCELLED")
        )
    assert live.scalar_one() == 1, "không được sinh lịch thứ hai"


@pytest.mark.asyncio
async def test_khach_khac_khong_bao_gio_nhin_thay_ma_lich_cua_nguoi_kia(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Khoá idempotency phải gồm KHÁCH.

    Chỉ khoá theo `showroom + scheduled_at` thì khách B bấm trùng giờ sẽ nhận
    `booking_id` của khách A — rò dữ liệu người khác, tệ hơn hẳn lỗi đang sửa.
    """

    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)

    def factory(session: AsyncSession):
        return build_agent_transaction(session, clock=clock)

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    mine = await booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT)
    theirs = await booker.book(customer_id="customer-2", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT)

    assert mine is not None
    assert theirs is None, "khách khác phải nhận 'khung đã đầy', không nhận mã lịch"


@pytest.mark.asyncio
async def test_cung_khach_khung_khac_thi_van_la_lich_moi(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)

    def factory(session: AsyncSession):
        return build_agent_transaction(session, clock=clock)

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    first = await booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT)
    later = await booker.book(
        customer_id="customer-1",
        vehicle_id=VEHICLE_ID,
        showroom=SHOWROOM,
        scheduled_at=SLOT + timedelta(hours=1),
    )

    assert first is not None and later is not None
    assert later != first


@pytest.mark.asyncio
async def test_cung_khach_bam_dup_trong_cuoc_dua_van_nhan_lai_lich_cu(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """Bấm đúp nhanh tới mức hai request cùng qua `count = 0`.

    Kẻ thua đụng index UNIQUE. Trả `None` lúc đó là nói với CHÍNH người vừa đặt
    rằng "khung giờ này vừa có người đặt mất" — một câu nói dối, và nó đẩy họ đi
    chọn khung khác trong khi lịch của họ đã có.

    Hợp đồng chốt: vi phạm ràng buộc xong thì ĐỌC LẠI. Là lịch của mình thì trả
    lại đúng mã đó; là của người khác thì mới là "khung đã đầy".
    """

    import asyncio

    from src.agents.services.test_drive import BookingUnitOfWorkSlotCounter

    clock = FrozenClock(NOW)
    sessions = async_sessionmaker(migrated_engine, expire_on_commit=False)
    both_counted = asyncio.Barrier(2)

    def factory(session: AsyncSession):
        transaction = build_agent_transaction(session, clock=clock)
        bookings = transaction.bookings
        original = bookings.count_active_at

        async def counting(showroom: str, scheduled_at: datetime) -> int:
            result = await original(showroom, scheduled_at)
            await both_counted.wait()
            return result

        bookings.count_active_at = counting  # type: ignore[method-assign]
        return transaction

    booker = BookingUnitOfWorkSlotCounter(AgentUnitOfWork(session_factory=sessions, transaction_factory=factory))

    results = await asyncio.gather(
        booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        booker.book(customer_id="customer-1", vehicle_id=VEHICLE_ID, showroom=SHOWROOM, scheduled_at=SLOT),
        return_exceptions=True,
    )

    assert not any(isinstance(item, BaseException) for item in results), results
    assert results[0] is not None and results[1] is not None, "cùng khách thì không ai bị báo hết chỗ"
    assert results[0] == results[1]

    async with migrated_engine.connect() as connection:
        live = await connection.execute(
            select(func.count()).select_from(BookingRow).where(BookingRow.status != "CANCELLED")
        )
    assert live.scalar_one() == 1


# ── GET /agent/bookings/me — khách xem lịch lái thử của chính mình ───────────


@pytest.mark.asyncio
async def test_customer_sees_only_own_bookings_via_me(app: FastAPI, migrated_engine: AsyncEngine) -> None:
    # Given — hai khách, mỗi người một lịch
    await _seed_booking_at(migrated_engine, scheduled_at=SLOT, status="CONFIRMED")  # customer-khac
    async with migrated_engine.begin() as connection:
        await connection.execute(
            insert(BookingRow).values(
                booking_id=uuid4(),
                customer_id="customer-1",
                vehicle_id=VEHICLE_ID,
                showroom=SHOWROOM,
                scheduled_at=SLOT + timedelta(hours=1),
                status="REQUESTED",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    app.dependency_overrides[get_current_customer_id] = lambda: "customer-1"

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/agent/bookings/me")

    # Then
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["customer_id"] == "customer-1"


@pytest.mark.asyncio
async def test_me_returns_401_when_anonymous(app: FastAPI) -> None:
    # Given — không override `get_current_customer_id`, seam mặc định trả None
    transport = ASGITransport(app=app)

    # When
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/agent/bookings/me")

    # Then
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staff_only_list_still_403s_a_logged_in_customer(app: FastAPI) -> None:
    # Given — khách đã đăng nhập nhưng gọi endpoint dành cho nhân sự
    from src.auth.domain.authorization import Role

    app.dependency_overrides[current_staff] = lambda: StaffIdentity(staff_id="customer-1", role=Role.CUSTOMER)
    transport = ASGITransport(app=app)

    # When
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get("/agent/bookings")

    # Then
    assert response.status_code == 403
