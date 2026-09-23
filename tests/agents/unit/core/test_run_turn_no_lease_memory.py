"""Route KHÔNG lease (`/agent/turn`) vẫn phải ghi trí nhớ lõi v2.

Bug thật đo trên máy 2026-09-23: `finalize_turn` (nhánh không lease) chỉ ghi tin
nhắn + slot + outcome, nên `conversation_core_state` và `turn_traces` trống rỗng
(0 hàng sau 32 tin nhắn). Mỗi lượt lõi nạp lại `CoreState()` trắng: `ask_counts`
reset nên trần `MAX_ASKS` không bao giờ chạm, `recommended_ids` reset nên "xe
vừa nãy" không tra ra được, và bot hỏi lại đúng một câu hồ sơ vô hạn lần.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.core.run_turn import run_turn
from src.agents.core.state import CoreState, Stage
from src.agents.core.understand import RawSlots, RawUnderstanding, UnderstandOutcome
from src.agents.domain.turn_trace import TurnTrace
from src.agents.services.registry import AgentServices

SESSION = "aaaaaaaa-0000-0000-0000-000000000001"


class _Conversation:
    """Cửa `conversation` ghi lại mọi lần lõi nhờ ghi state / vệt."""

    def __init__(self, *, state: CoreState | None = None, boom: Exception | None = None) -> None:
        self.state = state
        self.boom = boom
        self.saved: list[CoreState] = []
        self.traces: list[TurnTrace] = []

    async def open_session(self, session_id: str, customer_id: str) -> None:
        return None

    async def load_core_state(self, session_id: str) -> CoreState | None:
        return self.state

    async def load_handoff_state(self, session_id: str) -> bool:
        return False

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> list[Any]:
        return []

    async def save_core_state(self, state: CoreState) -> None:
        if self.boom is not None:
            raise self.boom
        self.saved.append(state)

    async def record_turn_trace(self, trace: TurnTrace) -> None:
        if self.boom is not None:
            raise self.boom
        self.traces.append(trace)


class _Memory:
    """`finalize_turn` (nhánh KHÔNG lease) — chỉ chốt lượt, không ghi state."""

    def __init__(self) -> None:
        self.finalized: list[dict[str, Any]] = []

    async def start_turn(self, **kwargs: Any) -> Any:
        from src.agents.services.conversation_memory import StartedMemoryTurn

        return StartedMemoryTurn(context="")

    async def append_user_message(self, **kwargs: Any) -> None:
        return None

    async def finalize_turn(self, **kwargs: Any) -> TurnResult:
        self.finalized.append(kwargs)
        return kwargs["result"]


class _Understander:
    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        return UnderstandOutcome(
            raw=RawUnderstanding(dialogue_act="UNCLEAR", intent="NONE", slots=RawSlots(), confidence=0.9)
        )


async def _turn(conversation: _Conversation, memory: _Memory) -> TurnResult:
    return await run_turn(
        None,
        AgentServices(conversation=conversation, memory=memory),
        session_id=SESSION,
        customer_id="c1",
        user_message="ờ thế à",
        client_turn_id=uuid4(),
        understander=_Understander(),
        lease=None,  # đúng cách `/agent/turn` gọi (api/routes.py)
    )


@pytest.mark.asyncio
async def test_khong_lease_van_ghi_core_state_va_trace() -> None:
    conversation = _Conversation(state=CoreState(session_id=SESSION, stage=Stage.RECOMMENDED))
    memory = _Memory()
    await _turn(conversation, memory)
    assert memory.finalized, "lượt vẫn phải chốt như cũ"
    assert len(conversation.saved) == 1
    assert len(conversation.traces) == 1
    assert conversation.traces[0].session_id == SESSION


@pytest.mark.asyncio
async def test_ask_counts_duoc_ghi_lai_de_tran_hoi_lai_co_hieu_luc() -> None:
    """`ask_counts` là thứ khiến `MAX_ASKS` hoạt động — phải nằm trong state đã ghi."""

    conversation = _Conversation(state=CoreState(session_id=SESSION, stage=Stage.COLLECTING))
    await _turn(conversation, _Memory())
    saved = conversation.saved[0]
    assert saved.ask_counts, "lượt hỏi lại phải tăng bộ đếm và bộ đếm phải được ghi"
    assert saved.turn_count >= 1


@pytest.mark.asyncio
async def test_ghi_state_hong_khong_giet_luot() -> None:
    """Hai bảng này phục vụ trí nhớ/quan sát — hỏng thì lượt vẫn phải trả lời."""

    conversation = _Conversation(state=CoreState(session_id=SESSION), boom=RuntimeError("db down"))
    memory = _Memory()
    result = await _turn(conversation, memory)
    assert result is not None
    assert memory.finalized
    assert conversation.saved == [] and conversation.traces == []
