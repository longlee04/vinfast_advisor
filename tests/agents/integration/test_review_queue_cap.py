"""[T7b] Trần mục PENDING mỗi phiên — tư vấn viên thấy "spam ×N", không thấy N mục.

Rate limit (T7a) chặn ở cửa theo THỜI GIAN; trần này chặn theo TỒN KHO. Hai chốt
bắt hai hình dạng lạm dụng khác nhau: gửi nhanh, và gửi đều đặn dưới hạn mức
suốt cả buổi. Thiếu chốt thứ hai thì hàng duyệt vẫn đầy, chỉ là đầy chậm hơn.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.adapters.repositories import MAX_PENDING_REVIEWS_PER_SESSION, SqlAlchemyReviewQueueRepository
from src.agents.adapters.run_repository import SqlAlchemyRunRepository
from src.agents.models import ReviewQueueRow


async def _seed(agent_session) -> tuple[str, UUID, SqlAlchemyReviewQueueRepository]:
    clock = SystemClock()
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await SqlAlchemySessionRepository(agent_session, clock).ensure_session(session_id, customer_id, None)
    run_id = await SqlAlchemyRunRepository(agent_session, clock).create_run(session_id)
    return session_id, run_id, SqlAlchemyReviewQueueRepository(agent_session, clock)


async def _pending(agent_session, session_id: str) -> list[ReviewQueueRow]:
    rows = await agent_session.scalars(
        select(ReviewQueueRow)
        .where(ReviewQueueRow.session_id == UUID(session_id), ReviewQueueRow.status == "PENDING")
        .order_by(ReviewQueueRow.created_at)
    )
    return list(rows)


@pytest.mark.asyncio
async def test_the_fourth_pending_item_merges_into_the_newest(agent_session):
    """Năm lần đẩy → ba mục, mục mới nhất mang số lần đã gộp."""

    session_id, run_id, repository = await _seed(agent_session)

    ids = [await repository.enqueue(run_id, UUID(session_id), f"Ban nhap {index}") for index in range(5)]

    pending = await _pending(agent_session, session_id)
    assert len(pending) == MAX_PENDING_REVIEWS_PER_SESSION == 3
    newest = pending[-1]
    assert newest.merged_count == 2, "hai lan day vuot tran phai gop vao day"
    assert ids[3] == ids[4] == newest.review_id, "day vuot tran tra ve chinh muc se duoc duyet"


@pytest.mark.asyncio
async def test_a_merged_push_records_where_it_came_from(agent_session):
    """Gộp mà không để lại vết thì không tune được ngưỡng, cũng không điều tra được."""

    session_id, run_id, repository = await _seed(agent_session)
    for index in range(MAX_PENDING_REVIEWS_PER_SESSION):
        await repository.enqueue(run_id, UUID(session_id), f"Ban nhap {index}")

    extra_run = await SqlAlchemyRunRepository(agent_session, SystemClock()).create_run(session_id)
    await repository.enqueue(extra_run, UUID(session_id), "Ban nhap bi gop")

    newest = (await _pending(agent_session, session_id))[-1]
    assert str(extra_run) in newest.merged_run_ids


@pytest.mark.asyncio
async def test_the_merged_item_keeps_its_own_content(agent_session):
    """Gộp là ĐẾM, không phải nối nội dung.

    Nối bản nháp lại với nhau biến một mục duyệt thành một bức tường chữ, và tư
    vấn viên duyệt cả cụm bằng một cú bấm — đúng thứ mà cổng duyệt sinh ra để
    ngăn. Quyết định vẫn nằm trên nội dung của mục mới nhất.
    """

    session_id, run_id, repository = await _seed(agent_session)
    for index in range(MAX_PENDING_REVIEWS_PER_SESSION):
        await repository.enqueue(run_id, UUID(session_id), f"Ban nhap {index}")

    await repository.enqueue(run_id, UUID(session_id), "NOI DUNG BI GOP")

    newest = (await _pending(agent_session, session_id))[-1]
    assert newest.content == "Ban nhap 2"
    assert "NOI DUNG BI GOP" not in newest.content


@pytest.mark.asyncio
async def test_the_cap_counts_only_pending_items(agent_session):
    """Mục đã duyệt xong không chiếm chỗ — nếu không, phiên dài tự khoá chính nó."""

    session_id, run_id, repository = await _seed(agent_session)
    first = await repository.enqueue(run_id, UUID(session_id), "Ban nhap 0")
    for index in (1, 2):
        await repository.enqueue(run_id, UUID(session_id), f"Ban nhap {index}")

    row = await agent_session.scalar(select(ReviewQueueRow).where(ReviewQueueRow.review_id == first))
    row.status = "APPROVED"
    await agent_session.flush()

    fresh = await repository.enqueue(run_id, UUID(session_id), "Ban nhap moi")

    pending = await _pending(agent_session, session_id)
    assert len(pending) == 3
    assert fresh in {item.review_id for item in pending}
    assert all(item.merged_count == 0 for item in pending)


@pytest.mark.asyncio
async def test_the_cap_is_scoped_per_session(agent_session):
    """Một phiên spam không được làm câm hàng duyệt của phiên khác."""

    first_session, first_run, repository = await _seed(agent_session)
    for index in range(MAX_PENDING_REVIEWS_PER_SESSION + 1):
        await repository.enqueue(first_run, UUID(first_session), f"Ban nhap {index}")

    second_session, second_run, _ = await _seed(agent_session)
    await repository.enqueue(second_run, UUID(second_session), "Phien khac")

    assert len(await _pending(agent_session, second_session)) == 1
