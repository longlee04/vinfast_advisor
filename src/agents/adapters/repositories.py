"""[Khối 4] Repository cụ thể chạy trên SQLAlchemy, bó lại thành `AgentTransaction`.

`adapters/` là nơi DUY NHẤT biết SQLAlchemy (mục 6.5b). Repository ở đây KHÔNG
tự gọi `session.begin()` — ranh giới transaction do `AgentUnitOfWork` mở
(luật A0-5); mỗi repository chỉ nhận `AsyncSession` đã nằm trong transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID, uuid4

from sqlalchemy import desc, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.agents.adapters.assignment_repository import (
    SqlAlchemyCustomerAssignmentRepository,
)
from src.agents.adapters.bottleneck_signal_repository import (
    SqlAlchemyBottleneckSignalRepository,
)
from src.agents.adapters.conversation_memory_repository import (
    SqlAlchemyConversationMemoryRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyTurnOutcomeRepository,
)
from src.agents.adapters.conversation_repository import (
    SqlAlchemyPendingFeatureMentionRepository,
    SqlAlchemySessionRepository,
)
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.adapters.session_offer_repository import SqlAlchemySessionOfferRepository
from src.agents.core.repository import CoreStateRepository
from src.agents.domain.turn_trace import TurnTrace
from src.agents.models import (
    AgentRunRow,
    ConversationSessionRow,
    InternalNoticeRow,
    NoticeReadRow,
    ReviewQueueRow,
    TestDriveBookingRow,
    TurnTraceRow,
)
from src.agents.services.operations.analytics import FunnelRow
from src.agents.services.operations.booking import SLOT_CAPACITY, BookableRun, BookingDto
from src.agents.services.operations.history import (
    CustomerAccountSummaryDto,
    CustomerActivityDto,
    SessionHistoryItem,
)
from src.agents.services.operations.notices import NoticeSummary
from src.agents.services.operations.review import (
    QueueEntry,
    ReviewClaimForbiddenError,
    ReviewItem,
    ReviewLeaseExpiredError,
    ReviewNotApprovedError,
    ReviewNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.agents.ports import (
        ClockPort,
        ConversationMemoryRepository,
        ConversationRepository,
        PendingFeatureMentionPort,
        RunRepository,
        SessionRepository,
        TurnOutcomeRepository,
    )


def _age_minutes(created_at: datetime | None, now: datetime) -> int | None:
    """Tuổi một mục hàng đợi, tính tròn phút — nguồn cho cột "Tuổi" màn duyệt.

    Cột `created_at` khai báo `timezone=True` nhưng dữ liệu cũ có thể còn naive;
    coi mốc naive là UTC thay vì để phép trừ nổ giữa đường đọc của tư vấn viên.
    Âm (đồng hồ lệch) thì kẹp về 0: "mục sinh ra ở tương lai" không phải thông
    tin dùng được, còn 0 thì đọc đúng là "vừa vào hàng đợi".
    """
    if created_at is None:
        return None
    reference = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=UTC)
    moment = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return max(int((moment - reference).total_seconds() // 60), 0)


def _snapshot_payload(snapshot: object | None) -> dict | None:
    """Serialise ProfileSnapshot (hoặc object có model_dump) sang dict cho JSONB."""
    if snapshot is None:
        return None
    dumper = getattr(snapshot, "model_dump", None)
    if callable(dumper):
        return dumper(mode="json")
    return dict(snapshot)


#: [T7b] Trần mục PENDING mỗi phiên. Rate limit (T7a) chặn theo THỜI GIAN; trần
#: này chặn theo TỒN KHO — kẻ gửi đều đặn dưới hạn mức suốt buổi vẫn làm ngập
#: hàng duyệt, chỉ là ngập chậm hơn. Ba là chỗ đủ rộng cho một cuộc tư vấn thật
#: (một báo giá, một thắc mắc chính sách, một yêu cầu gặp người) mà vẫn chặn.
MAX_PENDING_REVIEWS_PER_SESSION: Final[int] = 3


class SqlAlchemyReviewQueueRepository:
    """Implement `ReviewQueueRepository` (A7-1/2/3).

    `claim` là compare-and-set: một câu `UPDATE` có điều kiện, thắng/thua quyết
    định bằng số hàng bị ảnh hưởng — không đọc trước rồi mới ghi, vì đọc-rồi-ghi
    để lọt cửa sổ hai người cùng thấy hàng chưa ai giữ.
    """

    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def enqueue(
        self,
        run_id: UUID,
        session_id: UUID,
        content: str,
        snapshot: object | None = None,
    ) -> UUID:
        """Đẩy một bản nháp vào hàng đợi ở trạng thái `PENDING` (A7-1, PRD 5.6).

        Nội dung rỗng bị chặn ngay: một mục rỗng vẫn chiếm chỗ trong hàng đợi và
        tư vấn viên không có gì để duyệt, nhưng phễu lại đếm nó là "đã có đề xuất".

        [T7b] Một phiên giữ tối đa `MAX_PENDING_REVIEWS_PER_SESSION` mục PENDING.
        Vượt trần thì lần đẩy này KHÔNG tạo mục mới: nó cộng vào bộ đếm gộp của
        mục PENDING mới nhất và trả về chính `review_id` đó, nên lượt của khách
        vẫn trỏ đúng vào mục mà tư vấn viên sẽ xử lý.
        """

        if not content.strip():
            raise ValueError("review queue content must not be empty")
        now = self._clock.now()
        merged_into = await self._merge_when_capped(session_id, run_id, now)
        if merged_into is not None:
            return merged_into
        review_id = uuid4()
        self._session.add(
            ReviewQueueRow(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=content,
                status="PENDING",
                version=1,
                created_at=now,
                updated_at=now,
                profile_snapshot=_snapshot_payload(snapshot),
            )
        )
        await self._session.flush()
        return review_id

    async def _merge_when_capped(self, session_id: UUID, run_id: UUID, now: datetime) -> UUID | None:
        """Gộp vào mục PENDING mới nhất khi phiên đã chạm trần; `None` nếu còn chỗ.

        Gộp là ĐẾM, không nối nội dung. Nối bản nháp lại biến một mục duyệt thành
        bức tường chữ mà tư vấn viên duyệt cả cụm bằng một cú bấm — đúng thứ cổng
        duyệt sinh ra để ngăn. Quyết định vẫn ra trên nội dung mục mới nhất.

        Chỉ đếm mục PENDING: mục đã duyệt xong không chiếm chỗ, nếu không một
        phiên tư vấn dài sẽ tự khoá hàng đợi của chính nó.
        """

        pending = list(
            (
                await self._session.scalars(
                    select(ReviewQueueRow)
                    .where(ReviewQueueRow.session_id == session_id, ReviewQueueRow.status == "PENDING")
                    .order_by(ReviewQueueRow.created_at.desc())
                    .with_for_update()
                )
            ).all()
        )
        if len(pending) < MAX_PENDING_REVIEWS_PER_SESSION:
            return None
        newest = pending[0]
        newest.merged_count = (newest.merged_count or 0) + 1
        # Gán một list MỚI: SQLAlchemy không theo dõi mutate tại chỗ trên JSONB,
        # nên `.append()` sẽ mất lặng lẽ khi flush.
        newest.merged_run_ids = [*(newest.merged_run_ids or []), str(run_id)]
        newest.updated_at = now
        await self._session.flush()
        return newest.review_id

    async def claim(self, queue_id: UUID, advisor_id: str, lease_minutes: int) -> bool:
        """`True` khi giành được mục; `False` khi người khác đang giữ lease còn hạn."""
        now = self._clock.now()
        statement = (
            update(ReviewQueueRow)
            .where(
                ReviewQueueRow.review_id == queue_id,
                ReviewQueueRow.status == "PENDING",
                (ReviewQueueRow.claimed_by.is_(None)) | (ReviewQueueRow.lease_expires_at <= now),
            )
            .values(
                claimed_by=advisor_id,
                claimed_at=now,
                lease_expires_at=now + timedelta(minutes=lease_minutes),
                version=ReviewQueueRow.version + 1,
                updated_at=now,
            )
        )
        result = cast("CursorResult[Any]", await self._session.execute(statement))
        return result.rowcount == 1

    async def exists(self, queue_id: UUID) -> bool:
        """Phân biệt "đã có người nhận" với "không có mục nào" khi claim trượt."""
        found = await self._session.scalar(select(ReviewQueueRow.review_id).where(ReviewQueueRow.review_id == queue_id))
        return found is not None

    async def find(self, queue_id: UUID) -> ReviewItem | None:
        row = (
            await self._session.execute(
                select(
                    ReviewQueueRow.review_id,
                    ReviewQueueRow.session_id,
                    ReviewQueueRow.run_id,
                    ReviewQueueRow.status,
                    ReviewQueueRow.content,
                    ReviewQueueRow.edited_content,
                    ReviewQueueRow.claimed_by,
                    ReviewQueueRow.lease_expires_at,
                    ReviewQueueRow.profile_snapshot,
                    ReviewQueueRow.handoff_requested,
                    ReviewQueueRow.offer_suggestion_ignored,
                ).where(ReviewQueueRow.review_id == queue_id)
            )
        ).first()
        if row is None:
            return None
        return ReviewItem(
            review_id=row.review_id,
            session_id=row.session_id,
            run_id=row.run_id,
            status=row.status,
            content=row.content,
            edited_content=row.edited_content,
            claimed_by=row.claimed_by,
            lease_expires_at=row.lease_expires_at,
            profile_snapshot=row.profile_snapshot,
            handoff_requested=row.handoff_requested,
            offer_suggestion_ignored=row.offer_suggestion_ignored,
        )

    async def resolve(
        self,
        queue_id: UUID,
        advisor_id: str,
        status: str,
        edited_content: str | None,
        *,
        is_admin: bool = False,
        handoff_requested: bool = False,
        offer_suggestion_ignored: bool = False,
    ) -> None:
        """Ghi kết quả xử lý; đảm bảo đúng claimer và lease còn hiệu lực trừ khi là admin."""
        now = self._clock.now()
        statement = update(ReviewQueueRow).where(
            ReviewQueueRow.review_id == queue_id,
            ReviewQueueRow.status == "PENDING",
        )
        if not is_admin:
            statement = statement.where(
                (ReviewQueueRow.claimed_by.is_(None)) | (ReviewQueueRow.claimed_by == advisor_id),
                (ReviewQueueRow.lease_expires_at.is_(None)) | (ReviewQueueRow.lease_expires_at > now),
            )
        statement = statement.values(
            status=status,
            advisor_id=advisor_id,
            processed_at=now,
            edited_content=edited_content,
            handoff_requested=handoff_requested,
            offer_suggestion_ignored=offer_suggestion_ignored,
            version=ReviewQueueRow.version + 1,
            updated_at=now,
        )
        result = cast("CursorResult[Any]", await self._session.execute(statement))
        if result.rowcount == 0:
            row = (
                await self._session.execute(
                    select(
                        ReviewQueueRow.status,
                        ReviewQueueRow.claimed_by,
                        ReviewQueueRow.lease_expires_at,
                    ).where(ReviewQueueRow.review_id == queue_id)
                )
            ).first()
            if row is None:
                raise ReviewNotFoundError(str(queue_id))
            if row.status != "PENDING":
                raise ReviewNotApprovedError(f"review {queue_id} is already in state {row.status}")
            if not is_admin:
                if row.claimed_by is not None and row.claimed_by != advisor_id:
                    raise ReviewClaimForbiddenError(f"review {queue_id} claimed by {row.claimed_by}, not {advisor_id}")
                if row.lease_expires_at is not None and row.lease_expires_at <= now:
                    raise ReviewLeaseExpiredError(f"lease for review {queue_id} expired")

    async def mark_first_viewed(self, queue_id: UUID) -> None:
        """Đóng dấu lần đầu tư vấn viên mở mục — chỉ ghi khi cột còn trống.

        Điều kiện `IS NULL` nằm ngay trong câu `UPDATE` nên mở lại lần hai không
        đè mất mốc đầu tiên, kể cả khi hai tab cùng mở một mục.
        """
        await self._session.execute(
            update(ReviewQueueRow)
            .where(
                ReviewQueueRow.review_id == queue_id,
                ReviewQueueRow.first_viewed_at.is_(None),
            )
            .values(first_viewed_at=self._clock.now())
        )

    async def customer_owns_session(self, session_id: UUID, customer_id: str) -> bool:
        """Check session ownership before reading any review content."""
        owner = await self._session.scalar(
            select(ConversationSessionRow.customer_id).where(ConversationSessionRow.session_id == session_id)
        )
        if owner is None:
            return False
        return owner == customer_id or owner == f"anon-{session_id}"

    async def list_for_session(self, session_id: UUID) -> list[ReviewItem]:
        """List review items for one owned session without deciding deliverability."""
        rows = (
            await self._session.execute(
                select(
                    ReviewQueueRow.review_id,
                    ReviewQueueRow.session_id,
                    ReviewQueueRow.run_id,
                    ReviewQueueRow.status,
                    ReviewQueueRow.content,
                    ReviewQueueRow.edited_content,
                    ReviewQueueRow.profile_snapshot,
                    ReviewQueueRow.handoff_requested,
                    ReviewQueueRow.offer_suggestion_ignored,
                )
                .where(ReviewQueueRow.session_id == session_id)
                .order_by(ReviewQueueRow.created_at, ReviewQueueRow.review_id)
            )
        ).all()
        return [
            ReviewItem(
                review_id=row.review_id,
                session_id=row.session_id,
                run_id=row.run_id,
                status=row.status,
                content=row.content,
                edited_content=row.edited_content,
                profile_snapshot=row.profile_snapshot,
                handoff_requested=row.handoff_requested,
                offer_suggestion_ignored=row.offer_suggestion_ignored,
            )
            for row in rows
        ]

    async def list_by_status(self, statuses: Sequence[str], *, limit: int, offset: int) -> list[QueueEntry]:
        """Liệt kê hàng đợi theo nhóm trạng thái, cũ trước mới sau, có phân trang.

        Tách khỏi `list_pending` để đường đọc mặc định của A7 giữ nguyên chữ ký;
        màn hàng đợi mới cần lọc trạng thái và phân trang thì đi cửa này.
        """
        now = self._clock.now()
        rows = (
            await self._session.execute(
                select(
                    ReviewQueueRow.review_id,
                    ReviewQueueRow.session_id,
                    ReviewQueueRow.run_id,
                    ReviewQueueRow.status,
                    ReviewQueueRow.content,
                    ReviewQueueRow.claimed_by,
                    ReviewQueueRow.lease_expires_at,
                    ReviewQueueRow.created_at,
                    ReviewQueueRow.profile_snapshot,
                    ReviewQueueRow.handoff_requested,
                    ReviewQueueRow.offer_suggestion_ignored,
                    ReviewQueueRow.merged_count,
                )
                .where(ReviewQueueRow.status.in_(list(statuses)))
                .order_by(ReviewQueueRow.created_at, ReviewQueueRow.review_id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [
            QueueEntry(
                review_id=row.review_id,
                session_id=row.session_id,
                run_id=row.run_id,
                status=row.status,
                content=row.content,
                claimed_by=row.claimed_by,
                lease_expires_at=row.lease_expires_at,
                created_at=row.created_at,
                profile_snapshot=row.profile_snapshot,
                handoff_requested=row.handoff_requested,
                offer_suggestion_ignored=row.offer_suggestion_ignored,
                age_minutes=_age_minutes(row.created_at, now),
                merged_count=row.merged_count or 0,
            )
            for row in rows
        ]

    async def list_pending(self) -> list[QueueEntry]:
        """Liệt kê mục chưa xử lý cho màn hàng đợi, cũ trước mới sau."""
        now = self._clock.now()
        rows = (
            await self._session.execute(
                select(
                    ReviewQueueRow.review_id,
                    ReviewQueueRow.session_id,
                    ReviewQueueRow.run_id,
                    ReviewQueueRow.status,
                    ReviewQueueRow.content,
                    ReviewQueueRow.claimed_by,
                    ReviewQueueRow.lease_expires_at,
                    ReviewQueueRow.created_at,
                    ReviewQueueRow.profile_snapshot,
                    ReviewQueueRow.handoff_requested,
                    ReviewQueueRow.offer_suggestion_ignored,
                    ReviewQueueRow.merged_count,
                )
                .where(ReviewQueueRow.status == "PENDING")
                .order_by(ReviewQueueRow.created_at, ReviewQueueRow.review_id)
            )
        ).all()
        return [
            QueueEntry(
                review_id=row.review_id,
                session_id=row.session_id,
                run_id=row.run_id,
                status=row.status,
                content=row.content,
                claimed_by=row.claimed_by,
                lease_expires_at=row.lease_expires_at,
                created_at=row.created_at,
                profile_snapshot=row.profile_snapshot,
                handoff_requested=row.handoff_requested,
                offer_suggestion_ignored=row.offer_suggestion_ignored,
                age_minutes=_age_minutes(row.created_at, now),
                merged_count=row.merged_count or 0,
            )
            for row in rows
        ]

    async def queue_stats(self) -> dict[str, int]:
        """Đếm số lượng thực tế theo trạng thái từ bảng review_queue."""
        pending_count = (
            await self._session.scalar(
                select(func.count()).select_from(ReviewQueueRow).where(ReviewQueueRow.status == "PENDING")
            )
        ) or 0

        claimed_count = (
            await self._session.scalar(
                select(func.count())
                .select_from(ReviewQueueRow)
                .where(
                    ReviewQueueRow.status == "PENDING",
                    ReviewQueueRow.claimed_by.is_not(None),
                )
            )
        ) or 0

        approved_count = (
            await self._session.scalar(
                select(func.count())
                .select_from(ReviewQueueRow)
                .where(ReviewQueueRow.status.in_(["APPROVED", "EDITED"]))
            )
        ) or 0

        rejected_count = (
            await self._session.scalar(
                select(func.count()).select_from(ReviewQueueRow).where(ReviewQueueRow.status == "REJECTED")
            )
        ) or 0

        return {
            "pending": int(pending_count),
            "claimed": int(claimed_count),
            "approved": int(approved_count),
            "rejected": int(rejected_count),
        }


class SqlAlchemyNoticeRepository:
    """Implement `NoticeRepository` (A8-4).

    Trạng thái đã đọc là một hàng riêng cho mỗi `(notice_id, advisor_id)` — khoá
    chính ghép của `notice_reads` lo phần chống trùng, nên đánh dấu lại lần hai
    không sinh hàng mới thay vì phải kiểm tra trước rồi mới ghi.
    """

    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def create_notice(self, title: str, content: str, priority: str, created_by: str) -> UUID:
        now = self._clock.now()
        notice_id = uuid4()
        await self._session.execute(
            insert(InternalNoticeRow).values(
                notice_id=notice_id,
                title=title,
                content=content,
                priority=priority,
                created_by=created_by,
                created_at=now,
            )
        )
        return notice_id

    async def mark_read(self, notice_id: UUID, advisor_id: str) -> None:
        statement = (
            pg_insert(NoticeReadRow)
            .values(notice_id=notice_id, advisor_id=advisor_id, read_at=self._clock.now())
            .on_conflict_do_nothing(index_elements=["notice_id", "advisor_id"])
        )
        await self._session.execute(statement)

    async def exists(self, notice_id: UUID) -> bool:
        found = await self._session.scalar(
            select(InternalNoticeRow.notice_id).where(InternalNoticeRow.notice_id == notice_id)
        )
        return found is not None

    async def list_for(self, advisor_id: str) -> list[NoticeSummary]:
        """Notice mới nhất trước, kèm cờ đã đọc của riêng `advisor_id`."""
        read_at = select(NoticeReadRow.notice_id).where(NoticeReadRow.advisor_id == advisor_id).subquery()
        rows = await self._session.execute(
            select(
                InternalNoticeRow.notice_id,
                InternalNoticeRow.title,
                InternalNoticeRow.content,
                InternalNoticeRow.priority,
                InternalNoticeRow.created_at,
                read_at.c.notice_id.isnot(None).label("read"),
            )
            .outerjoin(read_at, read_at.c.notice_id == InternalNoticeRow.notice_id)
            .order_by(InternalNoticeRow.created_at.desc())
        )
        return [
            NoticeSummary(
                notice_id=row.notice_id,
                title=row.title,
                content=row.content,
                priority=row.priority,
                created_at=row.created_at,
                read=row.read,
            )
            for row in rows
        ]


class SqlAlchemyHistoryRepository:
    """[A8-3] Đọc lịch sử tư vấn và quan hệ phụ trách.

    Quan hệ "khách của tư vấn viên nào" suy từ `review_queue.advisor_id`: ai đã
    xử lý một mục trong hàng đợi của phiên khách đó thì phụ trách khách đó. Chưa
    có bảng phân công riêng, và bảng mới nằm ngoài phạm vi 10 task của Khối 4.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_handled_by(self, customer_id: str, advisor_id: str) -> bool:
        found = await self._session.scalar(
            select(ReviewQueueRow.review_id)
            .join(
                ConversationSessionRow,
                ConversationSessionRow.session_id == ReviewQueueRow.session_id,
            )
            .where(
                ConversationSessionRow.customer_id == customer_id,
                ReviewQueueRow.advisor_id == advisor_id,
            )
        )
        return found is not None

    async def list_sessions(self, customer_id: str) -> list[SessionHistoryItem]:
        """Phiên gần nhất trước — mô tả A8-3: sắp theo thời gian gần nhất."""
        rows = await self._session.execute(
            select(
                ConversationSessionRow.session_id,
                ConversationSessionRow.started_at,
                func.count(AgentRunRow.run_id.distinct()).label("run_count"),
                func.max(ReviewQueueRow.status).label("last_review_status"),
            )
            .outerjoin(AgentRunRow, AgentRunRow.session_id == ConversationSessionRow.session_id)
            .outerjoin(ReviewQueueRow, ReviewQueueRow.session_id == ConversationSessionRow.session_id)
            .where(ConversationSessionRow.customer_id == customer_id)
            .group_by(ConversationSessionRow.session_id, ConversationSessionRow.started_at)
            .order_by(ConversationSessionRow.started_at.desc())
        )
        return [
            SessionHistoryItem(
                session_id=str(row.session_id),
                started_at=row.started_at,
                run_count=row.run_count,
                last_review_status=row.last_review_status,
            )
            for row in rows
        ]

    async def get_customer_summary(self, customer_id: str) -> CustomerAccountSummaryDto:
        # 1. Count sessions
        session_count = (
            await self._session.scalar(
                select(func.count(ConversationSessionRow.session_id)).where(
                    ConversationSessionRow.customer_id == customer_id
                )
            )
        ) or 0

        # 2. Count bookings
        booking_count = (
            await self._session.scalar(
                select(func.count(TestDriveBookingRow.booking_id)).where(TestDriveBookingRow.customer_id == customer_id)
            )
        ) or 0

        # 3. Count comparisons/active sessions
        comparison_count = (
            await self._session.scalar(
                select(func.count(ConversationSessionRow.session_id.distinct()))
                .select_from(ConversationSessionRow)
                .join(AgentRunRow, AgentRunRow.session_id == ConversationSessionRow.session_id)
                .where(ConversationSessionRow.customer_id == customer_id)
            )
        ) or 0

        # 4. Count approved recommendations
        approved_count = (
            await self._session.scalar(
                select(func.count(ReviewQueueRow.review_id))
                .join(
                    ConversationSessionRow,
                    ConversationSessionRow.session_id == ReviewQueueRow.session_id,
                )
                .where(
                    ConversationSessionRow.customer_id == customer_id,
                    ReviewQueueRow.status.in_(["APPROVED", "EDITED"]),
                )
            )
        ) or 0

        activities: list[tuple[datetime, CustomerActivityDto]] = []

        # 5. Fetch recent sessions
        session_rows = (
            await self._session.execute(
                select(
                    ConversationSessionRow.session_id,
                    ConversationSessionRow.started_at,
                    ConversationSessionRow.vehicle_type_hint,
                    func.count(AgentRunRow.run_id.distinct()).label("run_count"),
                    func.max(ReviewQueueRow.status).label("last_review_status"),
                )
                .outerjoin(AgentRunRow, AgentRunRow.session_id == ConversationSessionRow.session_id)
                .outerjoin(ReviewQueueRow, ReviewQueueRow.session_id == ConversationSessionRow.session_id)
                .where(ConversationSessionRow.customer_id == customer_id)
                .group_by(
                    ConversationSessionRow.session_id,
                    ConversationSessionRow.started_at,
                    ConversationSessionRow.vehicle_type_hint,
                )
                .order_by(ConversationSessionRow.started_at.desc())
                .limit(5)
            )
        ).fetchall()

        for s_row in session_rows:
            vehicle_label = (
                "xe máy điện"
                if s_row.vehicle_type_hint == "ELECTRIC_MOTORBIKE"
                else ("ô tô điện" if s_row.vehicle_type_hint == "CAR" else "xe điện")
            )
            title = f"Phiên tư vấn chọn {vehicle_label}"
            desc = (
                f"Đã thực hiện {s_row.run_count} lượt hội thoại với Trợ lý AI."
                if s_row.run_count > 0
                else "Phiên tư vấn trực tuyến cùng Trợ lý AI VinFast."
            )
            if s_row.last_review_status == "PENDING":
                st = "Đang chờ duyệt"
                tone = "warning"
            elif s_row.last_review_status in ("APPROVED", "EDITED"):
                st = "Đã hoàn thành"
                tone = "success"
            else:
                st = "Đã hoàn thành"
                tone = "success"

            act = CustomerActivityDto(
                id=str(s_row.session_id),
                kind="session",
                date=s_row.started_at.strftime("%d/%m/%Y · %H:%M"),
                title=title,
                description=desc,
                status=st,
                tone=tone,
                icon="message",
            )
            activities.append((s_row.started_at, act))

        # 6. Fetch recent bookings
        booking_rows = (
            (
                await self._session.execute(
                    select(TestDriveBookingRow)
                    .where(TestDriveBookingRow.customer_id == customer_id)
                    .order_by(TestDriveBookingRow.created_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        for b_row in booking_rows:
            # Query vehicle name
            v_name = "VinFast EV"
            v_info = (
                await self._session.execute(
                    text("SELECT model_name, variant_name FROM vehicles WHERE vehicle_id = :vid"),
                    {"vid": str(b_row.vehicle_id)},
                )
            ).fetchone()
            if v_info:
                v_name = f"VinFast {v_info[0]} {v_info[1] or ''}".strip()

            title = f"Đăng ký lái thử {v_name}"
            sched_str = b_row.scheduled_at.strftime("%d/%m/%Y lúc %H:%M")
            desc = f"{b_row.showroom} · Lịch hẹn: {sched_str}"

            if b_row.status == "REQUESTED":
                st = "Chờ xác nhận"
                tone = "warning"
            elif b_row.status == "CONFIRMED":
                st = "Đã xác nhận"
                tone = "success"
            elif b_row.status == "CANCELLED":
                st = "Đã hủy"
                tone = "danger"
            else:
                st = b_row.status
                tone = "neutral"

            act = CustomerActivityDto(
                id=str(b_row.booking_id),
                kind="booking",
                date=b_row.created_at.strftime("%d/%m/%Y · %H:%M"),
                title=title,
                description=desc,
                status=st,
                tone=tone,
                icon="calendar",
            )
            activities.append((b_row.created_at, act))

        # Sort all activities by timestamp descending
        activities.sort(key=lambda x: x[0], reverse=True)
        recent_activities = [act for _, act in activities[:8]]

        return CustomerAccountSummaryDto(
            session_count=int(session_count),
            booking_count=int(booking_count),
            comparison_count=int(comparison_count),
            approved_recommendations_count=int(approved_count),
            activities=recent_activities,
        )


class SqlAlchemyBookingRepository:
    """[A8-2] Đọc điều kiện đặt lịch và ghi `test_drive_bookings`.

    Lượt đã huỷ không giữ chỗ: đếm sức chứa bỏ qua `CANCELLED`, khớp với điều
    kiện của index `ix_test_drive_bookings_showroom_time`.
    """

    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def find_run(self, run_id: UUID) -> BookableRun | None:
        row = (
            await self._session.execute(
                select(
                    AgentRunRow.run_id,
                    ConversationSessionRow.customer_id,
                    ReviewQueueRow.status,
                )
                .join(
                    ConversationSessionRow,
                    ConversationSessionRow.session_id == AgentRunRow.session_id,
                )
                .outerjoin(ReviewQueueRow, ReviewQueueRow.run_id == AgentRunRow.run_id)
                .where(AgentRunRow.run_id == run_id)
            )
        ).first()
        if row is None:
            return None
        return BookableRun(
            run_id=row.run_id,
            customer_id=row.customer_id,
            review_status=row.status or "",
        )

    async def count_active_at(self, showroom: str, scheduled_at: datetime) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(TestDriveBookingRow)
            .where(
                TestDriveBookingRow.showroom == showroom,
                TestDriveBookingRow.scheduled_at == scheduled_at,
                TestDriveBookingRow.status != "CANCELLED",
            )
        )
        return int(total or 0)

    async def booking_of(self, *, customer_id: str, showroom: str, scheduled_at: datetime) -> UUID | None:
        """Mã lịch CÒN SỐNG của chính khách này ở đúng khung, hoặc `None`.

        Khoá gồm `customer_id` là bắt buộc, không phải cho gọn: chỉ khoá theo
        `showroom + scheduled_at` thì khách B bấm trùng giờ sẽ nhận mã lịch của
        khách A — rò dữ liệu người khác, tệ hơn hẳn lỗi đang sửa.
        """

        return await self._session.scalar(
            select(TestDriveBookingRow.booking_id).where(
                TestDriveBookingRow.customer_id == customer_id,
                TestDriveBookingRow.showroom == showroom,
                TestDriveBookingRow.scheduled_at == scheduled_at,
                TestDriveBookingRow.status != "CANCELLED",
            )
        )

    async def busy_slots_between(self, *, showroom: str, start: datetime, end: datetime) -> list[datetime]:
        """Các mốc giờ ĐÃ ĐẦY của một showroom trong khoảng, gom về MỘT truy vấn.

        Lưới chọn lịch trải ba ngày cho ba showroom, tức tới 81 khung. Hỏi từng
        khung một là 81 lượt đi database trong một lượt chat.

        Trả mốc giờ, không trả số đếm: nơi gọi chỉ cần biết ô nào phải mờ đi.
        """

        rows = await self._session.execute(
            select(TestDriveBookingRow.scheduled_at)
            .where(
                TestDriveBookingRow.showroom == showroom,
                TestDriveBookingRow.scheduled_at >= start,
                TestDriveBookingRow.scheduled_at <= end,
                TestDriveBookingRow.status != "CANCELLED",
            )
            .group_by(TestDriveBookingRow.scheduled_at)
            .having(func.count() >= SLOT_CAPACITY)
        )
        return [row[0] for row in rows.all()]

    async def create_booking(
        self,
        *,
        run_id: UUID | None = None,
        customer_id: str,
        vehicle_id: UUID,
        advisor_id: str | None = None,
        showroom: str,
        scheduled_at: datetime,
    ) -> UUID:
        now = self._clock.now()
        booking_id = uuid4()
        await self._session.execute(
            insert(TestDriveBookingRow).values(
                booking_id=booking_id,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                advisor_id=advisor_id,
                run_id=run_id,
                showroom=showroom,
                scheduled_at=scheduled_at,
                status="REQUESTED",
                created_at=now,
                updated_at=now,
            )
        )
        return booking_id

    async def list_bookings(self, status: str | None = None, advisor_id: str | None = None) -> list[BookingDto]:
        stmt = select(TestDriveBookingRow).order_by(desc(TestDriveBookingRow.scheduled_at))
        if status:
            stmt = stmt.where(TestDriveBookingRow.status == status)
        if advisor_id:
            stmt = stmt.where(TestDriveBookingRow.advisor_id == advisor_id)

        rows = list((await self._session.execute(stmt)).scalars().all())
        return await self._hydrate_bookings(rows)

    async def list_for_customer(self, customer_id: str) -> list[BookingDto]:
        """Lịch lái thử của MỘT khách, mới nhất trước — cho trang tài khoản khách (`/me`).

        Cùng cách sắp xếp và cùng cách làm giàu tên xe/tên khách với
        `list_bookings`, chỉ khác điều kiện lọc: theo `customer_id` thay vì
        `advisor_id`/`status` dành cho Advisor và Admin.
        """
        stmt = (
            select(TestDriveBookingRow)
            .where(TestDriveBookingRow.customer_id == customer_id)
            .order_by(desc(TestDriveBookingRow.scheduled_at))
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return await self._hydrate_bookings(rows)

    async def _hydrate_bookings(self, rows: list[TestDriveBookingRow]) -> list[BookingDto]:
        results: list[BookingDto] = []
        for r in rows:
            # Query vehicle name
            v_name = "VinFast EV"
            v_row = (
                await self._session.execute(
                    text("SELECT model_name, variant_name FROM vehicles WHERE vehicle_id = :vid"),
                    {"vid": str(r.vehicle_id)},
                )
            ).fetchone()
            if v_row:
                v_name = f"VinFast {v_row[0]} {v_row[1] or ''}".strip()

            # Query customer name/phone
            c_name = r.customer_id
            c_phone = None
            c_prof = (
                await self._session.execute(
                    text("SELECT display_name, phone FROM customer_profiles WHERE customer_id = :cid"),
                    {"cid": r.customer_id},
                )
            ).fetchone()
            if c_prof:
                c_name = c_prof[0] or r.customer_id
                c_phone = c_prof[1]

            results.append(
                BookingDto(
                    booking_id=r.booking_id,
                    customer_id=r.customer_id,
                    customer_name=c_name,
                    phone=c_phone,
                    vehicle_id=r.vehicle_id,
                    vehicle_name=v_name,
                    advisor_id=r.advisor_id,
                    showroom=r.showroom,
                    scheduled_at=r.scheduled_at,
                    status=r.status,
                    created_at=r.created_at,
                )
            )
        return results

    async def confirm_booking(self, booking_id: UUID, advisor_id: str) -> bool:
        now = self._clock.now()
        res = await self._session.execute(
            update(TestDriveBookingRow)
            .where(TestDriveBookingRow.booking_id == booking_id)
            .values(status="CONFIRMED", advisor_id=advisor_id, updated_at=now)
        )
        return (res.rowcount or 0) > 0

    async def cancel_booking(self, booking_id: UUID) -> bool:
        now = self._clock.now()
        res = await self._session.execute(
            update(TestDriveBookingRow)
            .where(TestDriveBookingRow.booking_id == booking_id)
            .values(status="CANCELLED", updated_at=now)
        )
        return (res.rowcount or 0) > 0

    async def get_options(self) -> dict:
        v_rows = (
            await self._session.execute(
                text(
                    "SELECT vehicle_id, model_name, variant_name, vehicle_type, image_url "
                    "FROM vehicles WHERE vehicle_type = 'CAR' ORDER BY model_name"
                )
            )
        ).fetchall()
        vehicles = [
            {
                "id": str(r[0]),
                "name": f"VinFast {r[1]} {r[2] or ''}".strip(),
                "model": r[1],
                "variant": r[2] or "",
                "vehicle_type": r[3],
                "image_url": r[4],
            }
            for r in v_rows
        ]

        s_rows = (
            await self._session.execute(
                text(
                    # KHÔNG LIMIT (bug Sếp 2026-08-31 "showroom gần nhất sai"):
                    # bảng có ~1081 showroom, LIMIT 100 + ORDER BY city cắt sạch
                    # từ vần H — khách Hà Nội chỉ thấy toàn Hải Phòng cách 57km.
                    "SELECT location_id, name, address, city, latitude, longitude "
                    "FROM locations WHERE location_type IN ('showroom_car', 'showroom_escooter') "
                    "ORDER BY city, name"
                )
            )
        ).fetchall()
        # lat/lng cho bản đồ + sắp theo khoảng cách của form /test-drive (Sếp
        # 2026-08-31). Numeric → float ngay tại cửa: JSON hoá Decimal là chuỗi.
        showrooms = [
            {
                "id": str(r[0]),
                "name": r[1],
                "address": r[2],
                "city": r[3],
                "lat": float(r[4]) if r[4] is not None else None,
                "lng": float(r[5]) if r[5] is not None else None,
            }
            for r in s_rows
        ]

        return {"vehicles": vehicles, "showrooms": showrooms}


class SqlAlchemyAnalyticsRepository:
    """[A9-1] Đọc view `funnel_metrics` theo khoảng ngày.

    Chỉ đọc view, không dựng lại phép đếm bằng SQL riêng — số trên dashboard và
    số trong view luôn là một.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_funnel(self, date_from: date, date_to: date) -> list[FunnelRow]:
        rows = await self._session.execute(
            text(
                "SELECT day, sessions_started, sessions_with_profile, "
                "sessions_with_recommendation, sessions_approved, sessions_booked "
                "FROM funnel_metrics WHERE day >= :date_from AND day < :date_to_exclusive "
                "ORDER BY day"
            ),
            {"date_from": date_from, "date_to_exclusive": date_to + timedelta(days=1)},
        )
        return [
            FunnelRow(
                day=row.day.date() if isinstance(row.day, datetime) else row.day,
                sessions_started=row.sessions_started,
                sessions_with_profile=row.sessions_with_profile,
                sessions_with_recommendation=row.sessions_with_recommendation,
                sessions_approved=row.sessions_approved,
                sessions_booked=row.sessions_booked,
            )
            for row in rows
        ]


@dataclass(frozen=True, slots=True)
class SqlAlchemyTurnTraceRepository:
    """Vệt quyết định của một lượt (Sếp 2026-08-26).

    `record` là đường DUY NHẤT được gọi trong luồng chạy một lượt; hai hàm đọc
    chỉ phục vụ màn admin. Không lượt nào được phép chậm đi hay đổi hành vi vì
    bảng này — nó là bảng quan sát.
    """

    session: AsyncSession
    clock: ClockPort

    async def record(self, trace: TurnTrace) -> None:
        """Ghi một dòng. `trace_id` sinh tại đây — không có khoá khử trùng lặp."""

        self.session.add(
            TurnTraceRow(
                trace_id=uuid4(),
                session_id=UUID(trace.session_id),
                client_turn_id=UUID(trace.client_turn_id) if trace.client_turn_id else None,
                created_at=self.clock.now(),
                user_message=trace.user_message,
                intent_hint=trace.intent_hint,
                confidence=trace.confidence,
                tier=trace.tier,
                scope_label=trace.scope_label,
                terminal_reason=trace.terminal_reason,
                routing_enabled=trace.routing_enabled,
                payload=trace.payload,
            )
        )

    async def recent(self, *, since: datetime, limit: int, tier: str | None = None) -> list[dict]:
        """Các lượt gần nhất trong khung thời gian, mới trước."""

        statement = select(TurnTraceRow).where(TurnTraceRow.created_at >= since)
        if tier:
            statement = statement.where(TurnTraceRow.tier == tier)
        rows = (await self.session.scalars(statement.order_by(TurnTraceRow.created_at.desc()).limit(limit))).all()
        return [_turn_trace_dict(row) for row in rows]

    async def since(self, moment: datetime) -> list[dict]:
        """Mọi lượt từ `moment` — dùng để TỔNG HỢP, nên chỉ lấy cột vô hướng.

        Không kéo `payload` về: nó là JSON lớn nhất bảng và phép tổng hợp không
        đụng tới nó. Kéo về chỉ để rồi vứt là cách làm màn admin chậm dần theo
        lưu lượng.
        """

        rows = (
            await self.session.execute(
                select(TurnTraceRow.intent_hint, TurnTraceRow.confidence, TurnTraceRow.tier).where(
                    TurnTraceRow.created_at >= moment
                )
            )
        ).all()
        return [{"intent_hint": row[0], "confidence": row[1], "tier": row[2]} for row in rows]


def _turn_trace_dict(row: TurnTraceRow) -> dict:
    """Một dòng vệt cho màn admin. `payload` trả nguyên vẹn — nó chính là phần
    giải thích "vì sao", cắt bớt ở đây là bỏ đúng thứ Sếp cần xem."""

    return {
        "trace_id": str(row.trace_id),
        "session_id": str(row.session_id),
        "created_at": row.created_at,
        "user_message": row.user_message,
        "intent_hint": row.intent_hint,
        "confidence": row.confidence,
        "tier": row.tier,
        "scope_label": row.scope_label,
        "terminal_reason": row.terminal_reason,
        "routing_enabled": row.routing_enabled,
        "payload": row.payload,
    }


@dataclass(frozen=True)
class SqlAlchemyAgentTransaction:
    """Bó repository trong phạm vi một transaction.

    Bốn field đầu là `ports.AgentTransaction` đã đóng băng; `history` là phần
    riêng của Khối 4 (A8-3), không nằm trong port nên không đụng contract chung.
    """

    sessions: SessionRepository
    pending_mentions: PendingFeatureMentionPort
    memory: ConversationMemoryRepository
    conversations: ConversationRepository
    outcomes: TurnOutcomeRepository
    runs: RunRepository
    review_queue: SqlAlchemyReviewQueueRepository
    bottleneck_signals: SqlAlchemyBottleneckSignalRepository
    session_offers: SqlAlchemySessionOfferRepository
    notices: SqlAlchemyNoticeRepository
    history: SqlAlchemyHistoryRepository
    bookings: SqlAlchemyBookingRepository
    analytics: SqlAlchemyAnalyticsRepository
    assignments: SqlAlchemyCustomerAssignmentRepository
    turn_traces: SqlAlchemyTurnTraceRepository
    core_state: CoreStateRepository


def build_agent_transaction(session: AsyncSession, *, clock: ClockPort) -> SqlAlchemyAgentTransaction:
    """Dựng bó repository từ một `AsyncSession` đã nằm trong transaction."""
    return SqlAlchemyAgentTransaction(
        sessions=SqlAlchemySessionRepository(session, clock),
        pending_mentions=SqlAlchemyPendingFeatureMentionRepository(session, clock),
        memory=SqlAlchemyConversationMemoryRepository(session, clock),
        conversations=SqlAlchemyConversationRepository(session, clock),
        outcomes=SqlAlchemyTurnOutcomeRepository(session, clock),
        runs=SqlAlchemyRunRepository(session, clock),
        review_queue=SqlAlchemyReviewQueueRepository(session, clock),
        bottleneck_signals=SqlAlchemyBottleneckSignalRepository(session, clock),
        session_offers=SqlAlchemySessionOfferRepository(session, clock),
        notices=SqlAlchemyNoticeRepository(session, clock),
        history=SqlAlchemyHistoryRepository(session),
        bookings=SqlAlchemyBookingRepository(session, clock),
        analytics=SqlAlchemyAnalyticsRepository(session),
        assignments=SqlAlchemyCustomerAssignmentRepository(session, clock),
        turn_traces=SqlAlchemyTurnTraceRepository(session, clock),
        core_state=CoreStateRepository(session),
    )
