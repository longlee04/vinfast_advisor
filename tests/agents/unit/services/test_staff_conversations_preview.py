"""Đợt 9: màn TVV với phiên lõi v2 phải thấy tin cuối + slot đã hiểu (trước đây rỗng)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.agents.core.state import CoreState
from src.agents.domain.values import SlotName
from src.agents.services.conversation import PREVIEW_MAX_CHARS, ConversationServiceImpl

SESSION = uuid4()


def _row(session_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        session_id=session_id,
        customer_id="c1",
        status="ACTIVE",
        assigned_advisor_id=None,
        last_activity_at=datetime(2026, 8, 31, tzinfo=UTC),
        ownership="AI",
    )


class FakeSessions:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    async def list_staff_sessions(self, *, requester_id: str, role: str, customer_id: str | None = None):
        return self.rows

    async def get_session(self, session_id: UUID):
        return next((row for row in self.rows if row.session_id == session_id), None)


class FakeMessages:
    def __init__(self, latest: str | None) -> None:
        self.latest = latest

    async def latest_content(self, session_id: UUID) -> str | None:
        return self.latest

    async def list_for_session(self, session_id: UUID, limit: int = 100):
        return [(uuid4(), "USER", self.latest or "", None, datetime(2026, 8, 31, tzinfo=UTC))]


class FakeCoreState:
    def __init__(self, state: CoreState | None) -> None:
        self.state = state

    async def load(self, session_id: str) -> CoreState | None:
        return self.state


class FakeUnitOfWork:
    def __init__(self, **repos):
        self.repos = repos

    @asynccontextmanager
    async def transaction(self):
        yield SimpleNamespace(**self.repos)


def _service(latest: str | None, state: CoreState | None) -> ConversationServiceImpl:
    return ConversationServiceImpl(
        FakeUnitOfWork(
            sessions=FakeSessions([_row(SESSION)]), messages=FakeMessages(latest), core_state=FakeCoreState(state)
        )
    )


@pytest.mark.asyncio
async def test_danh_sach_tvv_co_tin_cuoi_va_slot_lo_i_v2() -> None:
    state = CoreState(
        session_id=str(SESSION), slots={SlotName.BUDGET_MAX_VND: 500_000_000, SlotName.VEHICLE_TYPE: "CAR"}
    )
    items = await _service("Anh muốn xem VF 5", state).list_staff_conversations(requester_id="a1", role="admin")
    assert items[0].last_message_preview == "Anh muốn xem VF 5"
    assert items[0].slots == {"budget_max_vnd": 500_000_000, "vehicle_type": "CAR"}


@pytest.mark.asyncio
async def test_chi_tiet_tvv_cung_co_tin_cuoi_va_slot() -> None:
    state = CoreState(session_id=str(SESSION), slots={SlotName.PURPOSE: "đi làm"})
    result = await _service("Dạ em nghe", state).staff_conversation_detail(
        str(SESSION), requester_id="a1", role="admin"
    )
    assert result is not None
    summary, _messages = result
    assert summary.last_message_preview == "Dạ em nghe" and summary.slots == {"purpose": "đi làm"}


@pytest.mark.asyncio
async def test_tin_cuoi_cat_ngan_va_thieu_cua_thi_rong_khong_chet() -> None:
    long_text = "x" * 500
    items = await _service(long_text, None).list_staff_conversations(requester_id="a1", role="admin")
    assert len(items[0].last_message_preview) == PREVIEW_MAX_CHARS and items[0].last_message_preview.endswith("…")
    assert items[0].slots == {}
    # Transaction giả KHÔNG có `messages`/`core_state` (fake cũ) → vẫn ra danh sách.
    bare = ConversationServiceImpl(FakeUnitOfWork(sessions=FakeSessions([_row(SESSION)])))
    items = await bare.list_staff_conversations(requester_id="a1", role="admin")
    assert items[0].last_message_preview == "" and items[0].slots == {}
