"""[A0-5] Implement `UnitOfWorkPort` (mục 6.4) — nơi DUY NHẤT trong `unit_of_work.py`
biết SQLAlchemy cho ranh giới transaction; repository cụ thể (Khối 4,
`adapters/repositories.py`) không tự mở session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.contracts import QuoteAuditRecord
from src.agents.domain.values import ScopeLabel
from src.agents.models import AgentRateLimitCounterRow, OutOfScopeLogRow, QuoteAuditLogRow
from src.agents.ports import ClockPort

TransactionT = TypeVar("TransactionT")


class AgentUnitOfWork(Generic[TransactionT]):
    """Mở một transaction mỗi lần gọi `transaction()`, không bọc cả lượt hội thoại (mục 6.4).

    `transaction_factory` dựng `AgentTransaction` (bó 4 repository) từ
    `AsyncSession` — tách khỏi lớp này để A0-5 không phải chờ
    `adapters/repositories.py` (sở hữu bởi Khối 4) tồn tại trước; mỗi khối
    nối factory thật của mình qua `composition.py` khi repository đã sẵn.

    Tham số hoá theo kiểu transaction (`AgentUnitOfWork[AgentTransaction]` là
    ca thường) để một use case cần bó repository hẹp hơn — ví dụ A7-2 chỉ dùng
    `review_queue` — vẫn giữ được kiểu thật thay vì rơi về `Any`.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        transaction_factory: Callable[[AsyncSession], TransactionT],
    ) -> None:
        self._session_factory = session_factory
        self._transaction_factory = transaction_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionT]:
        """Commit khi thoát bình thường, rollback toàn bộ khi có lỗi bên trong."""
        async with self._session_factory() as session, session.begin():
            yield self._transaction_factory(session)


class SqlAlchemyScopeLogUnitOfWork:
    """Persist one A6-2 audit row through the centralized transaction boundary."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        clock: ClockPort,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_factory = id_factory

    async def log(
        self,
        *,
        session_id: UUID,
        utterance: str,
        classification: ScopeLabel,
        reason: str | None,
    ) -> None:
        """Insert and commit an audit row, rolling back automatically on failure."""

        async with self._session_factory() as session, session.begin():
            session.add(
                OutOfScopeLogRow(
                    id=self._id_factory(),
                    session_id=session_id,
                    utterance=utterance,
                    classification=classification.value,
                    reason=reason,
                    created_at=self._clock.now(),
                )
            )


class SqlAlchemyRateLimitUnitOfWork:
    """[T7a] Đếm một lượt trong transaction RIÊNG của bộ giới hạn.

    Cùng khuôn và cùng lý do với hai lớp audit dưới đây: phép đếm KHÔNG được
    chia sẻ số phận với transaction nghiệp vụ. Một lượt bị rollback vì lỗi ở
    bước sau mà kéo theo bộ đếm về 0 thì kẻ spam chỉ cần làm lượt của mình hỏng
    là có quota vô hạn.

    Câu lệnh là một `INSERT ... ON CONFLICT DO UPDATE` — đọc-rồi-ghi sẽ đếm
    thiếu dưới tải đồng thời, đúng cái tình huống mà một bộ giới hạn sinh ra để
    xử lý.
    """

    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def count_attempt(self, key: str, *, window_start: datetime, expires_at: datetime) -> int:
        """Cộng một lượt vào cửa sổ và trả về tổng mới."""

        statement = (
            pg_insert(AgentRateLimitCounterRow)
            .values(key=key, window_start=window_start, attempts=1, expires_at=expires_at)
            .on_conflict_do_update(
                index_elements=[AgentRateLimitCounterRow.key, AgentRateLimitCounterRow.window_start],
                set_={"attempts": AgentRateLimitCounterRow.attempts + 1},
            )
            .returning(AgentRateLimitCounterRow.attempts)
        )
        async with self._session_factory() as session, session.begin():
            return int((await session.execute(statement)).scalar_one())


class SqlAlchemyQuoteAuditUnitOfWork:
    """[A7-4] Persist one quote-risk gate decision through its own transaction.

    Cùng khuôn và cùng lý do với `SqlAlchemyScopeLogUnitOfWork` ngay trên: audit
    KHÔNG được chia sẻ số phận với transaction nghiệp vụ. Một lượt bị rollback
    vẫn phải để lại dấu vết đã quyết định gì, và ghi audit hỏng không được kéo
    lượt của khách theo.

    Nằm trong `unit_of_work.py` chứ không phải một adapter riêng vì đây là nơi
    DUY NHẤT trong `adapters/` được mở transaction (mục 6.4, luật A0-5).
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        clock: ClockPort,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_factory = id_factory

    async def record(self, entry: QuoteAuditRecord) -> None:
        """Chèn một dòng `quote_audit_log` và commit ngay."""

        async with self._session_factory() as session, session.begin():
            session.add(
                QuoteAuditLogRow(
                    audit_id=self._id_factory(),
                    session_id=UUID(str(entry.session_id)),
                    run_id=entry.run_id,
                    tier=entry.tier,
                    requires_hitl=entry.requires_hitl,
                    legacy_requires_hitl=entry.legacy_requires_hitl,
                    shadow_mode=entry.shadow_mode,
                    sampled_for_review=entry.sampled_for_review,
                    near_threshold=entry.near_threshold,
                    user_message=entry.user_message,
                    output_content=entry.output_content,
                    evaluation=dict(entry.evaluation),
                    reasons=list(entry.reasons),
                    created_at=self._clock.now(),
                )
            )
