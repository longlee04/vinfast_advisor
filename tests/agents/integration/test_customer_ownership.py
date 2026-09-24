"""Tư vấn viên tự nhận khách trên Postgres thật: nhận nguyên tử, tiếp quản tự gán, trả khách, hàng chờ, tự nhả."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.customer_ownership_repository import SqlAlchemyCustomerOwnershipRepository
from src.agents.domain.customer_ownership import ClaimOutcome
from src.agents.models import ConversationSessionRow, CustomerProfileRow
from src.agents.services.operations.customer_ownership import CustomerOwnershipOperations

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


async def _session(factory, customer_id: str, *, ownership: str = "AI", at: datetime = NOW) -> str:  # noqa: ANN001
    session_id = uuid4()
    async with factory() as session:
        session.add(
            ConversationSessionRow(
                session_id=session_id,
                customer_id=customer_id,
                status="ACTIVE",
                ownership=ownership,
                started_at=at,
                last_activity_at=at,
                created_at=at,
                updated_at=at,
            )
        )
        await session.commit()
    return str(session_id)


async def _owner(factory, customer_id: str) -> list[str]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.execute(
            text("SELECT advisor_id FROM customer_advisor_assignments WHERE customer_id = :c AND status = 'ACTIVE'"),
            {"c": customer_id},
        )
        return [row[0] for row in rows]


@pytest.mark.asyncio
async def test_nhan_khach_nguyen_tu_tiep_quan_tu_gan_va_tra_khach(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    operations = CustomerOwnershipOperations(SqlAlchemyCustomerOwnershipRepository(factory), lambda: NOW)
    await _session(factory, "cust-a", ownership="PENDING_HANDOFF")
    await _session(factory, "cust-b")
    await _session(factory, "anon-1")
    async with factory() as session:
        # Khách vừa đăng nhập, chưa chat lượt nào — hồ sơ tạo từ tài khoản (plan §20).
        session.add(
            CustomerProfileRow(customer_id="cust-z", email="zz.nguyen@gmail.com", created_at=NOW, updated_at=NOW)
        )
        session.add(
            CustomerProfileRow(
                customer_id="cust-a", display_name="Khách A", phone="0912345678", created_at=NOW, updated_at=NOW
            )
        )
        await session.commit()

    # Hàng chờ: khách đang chờ người lên trước, SĐT che, bỏ khách ẩn danh.
    pool = await operations.pool()
    assert [row["customer_id"] for row in pool][:1] == ["cust-a"]
    assert {row["customer_id"] for row in pool} == {"cust-a", "cust-b", "cust-z"}
    assert pool[0]["waiting"] and pool[0]["phone"] == "0912***678"

    # Hai người bấm cùng lúc: đúng một người thắng.
    first, second = await asyncio.gather(
        operations.claim("cust-a", advisor_id="adv-1", requester_ids=("adv-1",)),
        operations.claim("cust-a", advisor_id="adv-2", requester_ids=("adv-2",)),
    )
    assert sorted([first.outcome, second.outcome]) == sorted([ClaimOutcome.CLAIMED, ClaimOutcome.TAKEN])
    assert len(await _owner(factory, "cust-a")) == 1
    winner = (await _owner(factory, "cust-a"))[0]
    again = await operations.claim("cust-a", advisor_id=winner, requester_ids=(winner,))
    assert again.outcome is ClaimOutcome.ALREADY_MINE
    assert {row["customer_id"] for row in await operations.pool()} == {"cust-b", "cust-z"}
    fresh = next(row for row in await operations.pool() if row["customer_id"] == "cust-z")
    assert fresh["sessions_count"] == 0 and fresh["email"] == "zz***@gmail.com"

    # Tiếp quản: khách chưa ai phụ trách → của người tiếp quản; đã có người → giữ nguyên; ẩn danh → bỏ qua.
    session_b = await _session(factory, "cust-b")
    assert (await operations.claim_on_takeover(session_b, advisor_id="adv-3")).outcome is ClaimOutcome.CLAIMED
    session_a = await _session(factory, "cust-a")
    assert (await operations.claim_on_takeover(session_a, advisor_id="adv-3")).outcome is ClaimOutcome.TAKEN
    assert await _owner(factory, "cust-a") == [winner]
    assert await operations.claim_on_takeover(await _session(factory, "anon-1"), advisor_id="adv-3") is None

    # Chỉ người phụ trách mới trả được khách.
    assert await operations.release("cust-b", requester_ids=("adv-1",)) is False
    assert await operations.release("cust-b", requester_ids=("adv-3",)) is True
    assert await _owner(factory, "cust-b") == []


@pytest.mark.asyncio
async def test_tu_nha_khach_khong_co_hoat_dong_tu_van_vien_7_ngay(
    migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    old = NOW - timedelta(days=10)
    past = CustomerOwnershipOperations(SqlAlchemyCustomerOwnershipRepository(factory), lambda: old)
    for customer in ("stale", "chatted", "live"):
        await _session(factory, customer, at=old)
        await past.claim(customer, advisor_id="adv-1", requester_ids=("adv-1",))
    chatted = await _session(factory, "chatted", at=NOW - timedelta(days=1))
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO conversation_messages (message_id, session_id, role, content, turn_index, created_at) "
                "VALUES (:id, :s, 'ADVISOR', 'chào anh', 1, :at)"
            ),
            {"id": uuid4(), "s": chatted, "at": NOW - timedelta(days=1)},
        )
        await session.commit()
    await _session(factory, "live", ownership="HUMAN")

    now = CustomerOwnershipOperations(SqlAlchemyCustomerOwnershipRepository(factory), lambda: NOW)
    assert await now.release_stale() == ["stale"]
    assert await _owner(factory, "stale") == []
    assert await _owner(factory, "chatted") == ["adv-1"]
    assert await _owner(factory, "live") == ["adv-1"]
