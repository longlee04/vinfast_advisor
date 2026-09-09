"""Bảng conversation_core_state: migration agent_0032 + round-trip (spec mục 4)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.core.repository import CoreStateRepository, from_row, to_row_values
from src.agents.core.state import CoreState, Intent, Pending, PendingKind, Stage
from src.agents.domain.values import SlotName
from src.agents.models import ConversationCoreStateRow


async def _read_updated_at(session: AsyncSession, session_id: str) -> datetime:
    # Chọn thẳng cột (không qua `session.get`) để KHÔNG trúng identity map của
    # ORM — nếu không, đọc lại có thể trả về đối tượng đã cache từ lần trước
    # thay vì hàng thật đã được `save()` cập nhật.
    stmt = select(ConversationCoreStateRow.updated_at).where(ConversationCoreStateRow.session_id == UUID(session_id))
    return (await session.execute(stmt)).scalar_one()


def _state(session_id: str) -> CoreState:
    return CoreState(
        session_id=session_id,
        stage=Stage.RECOMMENDED,
        intent=Intent.ADVISORY,
        slots={SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 900_000_000, SlotName.HABIT_NEED_TAGS: ["ADAS"]},
        pending=Pending(kind=PendingKind.SLOT, key="habit_need_tags", options=("ADAS", "BLUETOOTH"), labels=("hỗ trợ lái", "bluetooth"), asked_at_turn=3),
        chosen_vehicle_id=None,
        recommended_ids=(str(uuid.uuid4()), str(uuid.uuid4())),
        ask_counts={"vehicle_type": 1, "habit_need_tags": 1},
        turn_count=3,
    )


def test_to_row_va_from_row_thuan() -> None:
    sid = str(uuid.uuid4())
    state = _state(sid)
    values = to_row_values(state)
    assert values["stage"] == "RECOMMENDED"
    assert values["slots"] == {"vehicle_type": "CAR", "budget_max_vnd": 900_000_000, "habit_need_tags": ["ADAS"]}
    assert values["pending"] == {"kind": "SLOT", "key": "habit_need_tags", "options": ["ADAS", "BLUETOOTH"], "labels": ["hỗ trợ lái", "bluetooth"], "asked_at_turn": 3, "job": ""}
    row = ConversationCoreStateRow(**values)
    back = from_row(row)
    assert back == state


def test_from_row_khoa_slot_la_enum() -> None:
    row = ConversationCoreStateRow(**to_row_values(_state(str(uuid.uuid4()))))
    back = from_row(row)
    assert all(isinstance(k, SlotName) for k in back.slots)


def test_from_row_bo_khoa_slot_la() -> None:
    values = to_row_values(_state(str(uuid.uuid4())))
    values["slots"]["khoa_la"] = 1
    back = from_row(ConversationCoreStateRow(**values))
    assert SlotName.VEHICLE_TYPE in back.slots and len(back.slots) == 3


@pytest.mark.asyncio
async def test_round_trip_db(agent_session) -> None:
    repo = CoreStateRepository(agent_session)
    sid = str(uuid.uuid4())
    assert await repo.exists(sid) is False
    assert await repo.load(sid) is None
    # `_state` sinh `recommended_ids` ngẫu nhiên mỗi lần gọi (uuid.uuid4() không
    # neo theo session_id) — giữ một instance để so sánh round-trip cho đúng ý
    # nghĩa "lưu gì đọc lại nấy", thay vì so với một lần gọi `_state(sid)` khác.
    state = _state(sid)
    await repo.save(state)
    assert await repo.exists(sid) is True
    loaded = await repo.load(sid)
    assert loaded == state
    first_updated_at = await _read_updated_at(agent_session, sid)
    # upsert: ghi đè, không nhân đôi
    await repo.save(state.with_(stage=Stage.CHOSEN, turn_count=4))
    again = await repo.load(sid)
    assert again is not None and again.stage is Stage.CHOSEN and again.turn_count == 4
    second_updated_at = await _read_updated_at(agent_session, sid)
    assert second_updated_at > first_updated_at


def test_pending_job_survives_round_trip() -> None:
    """Tên việc treo phải sống qua vòng ghi–đọc.

    `Pending.job` là thứ làm câu hỏi treo nói đúng khung việc sau một lượt chen
    ngang ("đặt lái thử" thay vì câu luồng thông số). Rơi mất ở tầng lưu là lượt
    sau hỏi lại sai việc — mà không có lỗi nào bật lên.
    """

    sid = str(uuid.uuid4())
    state = _state(sid)
    state = replace(
        state,
        pending=replace(state.pending, job="đặt lái thử"),
    )

    values = to_row_values(state)
    assert values["pending"]["job"] == "đặt lái thử"

    back = from_row(ConversationCoreStateRow(**values))
    assert back.pending is not None
    assert back.pending.job == "đặt lái thử"
    assert back == state


def test_pending_without_job_reads_back_empty() -> None:
    """Hàng cũ lưu trước khi có `job` đọc lên vẫn hợp lệ, `job` rỗng."""

    sid = str(uuid.uuid4())
    values = to_row_values(_state(sid))
    values["pending"] = {k: v for k, v in values["pending"].items() if k != "job"}

    back = from_row(ConversationCoreStateRow(**values))
    assert back.pending is not None
    assert back.pending.job == ""
