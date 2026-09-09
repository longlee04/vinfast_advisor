"""Lõi v2 phải đi qua ĐÚNG cổng kiểm duyệt của lõi cũ, ở ĐÚNG chỗ đó.

Món nợ I2 của bước 3: `run_turn` gọi `start_turn` với `persist_message` mặc định
`True` và không có `_input_is_blocked` nào — nội dung độc vào transcript rồi vào
prompt LLM. Cổng nằm ở `chain.py` mà `core/` không được import `chain`, nên bước
3 bỏ trống; đây là bản trả nợ: gọi thẳng `services.moderation.is_blocked` với
`canonical` dựng bằng đúng helper miền.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.agents.contracts import TurnResult
from src.agents.core import run_turn as run_turn_module
from src.agents.core.run_turn import run_turn
from src.agents.core.state import CoreState
from src.agents.core.understand import RawSlots, RawUnderstanding, UnderstandOutcome
from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.conversation_memory import CoreTurnLease
from src.agents.domain.moderation_blocklist import CONTENT_BLOCKED_REASON, MODERATION_BLOCK_MESSAGE
from src.agents.services.registry import AgentServices
from tests.agents.unit.core.memory_fakes import HonestMemory

SESSION = "aaaaaaaa-0000-0000-0000-00000000000b"


@pytest.fixture(autouse=True)
def _clear_directory_cache() -> None:
    run_turn_module.reset_vehicle_directory_cache()


def _lease() -> CoreTurnLease:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=__import__("uuid").UUID(SESSION),
        client_turn_id=__import__("uuid").uuid4(),
        turn_number=1,
        claim_token=__import__("uuid").uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


class FakeConversation:
    async def open_session(self, session_id: str, customer_id: str) -> None:
        return None

    async def load_core_state(self, session_id: str) -> CoreState | None:
        return None

    async def load_handoff_state(self, session_id: str) -> bool:
        return False

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> list[Any]:
        return []


class FakeModeration:
    def __init__(self, verdict: bool | Exception) -> None:
        self._verdict = verdict
        self.seen: list[tuple[str, CanonicalText]] = []

    async def is_blocked(self, *, user_message: str, canonical: CanonicalText) -> bool:
        self.seen.append((user_message, canonical))
        if isinstance(self._verdict, Exception):
            raise self._verdict
        return self._verdict


class FakeUnderstander:
    def __init__(self) -> None:
        self.calls = 0

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        self.calls += 1
        return UnderstandOutcome(
            raw=RawUnderstanding(dialogue_act="REQUEST", intent="ADVISORY", slots=RawSlots(), confidence=0.9)
        )


async def _turn(
    moderation: FakeModeration | None, *, user_message: str = "tư vấn giúp em"
) -> tuple[TurnResult, HonestMemory, FakeUnderstander]:
    memory = HonestMemory()
    understander = FakeUnderstander()
    result = await run_turn(
        None,
        AgentServices(conversation=FakeConversation(), memory=memory, moderation=moderation),
        session_id=SESSION,
        customer_id="c1",
        user_message=user_message,
        client_turn_id=uuid4(),
        understander=understander,
        lease=_lease(),
    )
    return result, memory, understander


@pytest.mark.asyncio
async def test_luot_bi_chan_khong_goi_llm_khong_ghi_state() -> None:
    result, memory, understander = await _turn(FakeModeration(True), user_message="dm thang ngu")

    assert understander.calls == 0, "lượt bị chặn không được tốn một call LLM"
    assert memory.committed == [], "lượt bị chặn không được đổi trạng thái hội thoại"
    assert result.terminal_reason == CONTENT_BLOCKED_REASON
    assert result.answer == MODERATION_BLOCK_MESSAGE


@pytest.mark.asyncio
async def test_luot_bi_chan_khong_de_text_vao_transcript() -> None:
    _, memory, _ = await _turn(FakeModeration(True), user_message="dm thang ngu")

    assert memory.appended == [], "câu bị chặn không bao giờ vào transcript"
    assert memory.committed == [], "lượt bị chặn không được commit"


@pytest.mark.asyncio
async def test_luot_bi_chan_van_dong_luot_da_claim() -> None:
    """Bỏ mở thì lần gửi lại cùng `client_turn_id` gặp `TurnInProgressError`."""

    _, memory, _ = await _turn(FakeModeration(True), user_message="dm thang ngu")

    assert len(memory.finalized) == 1
    assert memory.finalized[0]["result"].terminal_reason == CONTENT_BLOCKED_REASON


@pytest.mark.asyncio
async def test_luot_sach_van_chay_va_text_vao_transcript_sau_kiem_duyet() -> None:
    result, memory, understander = await _turn(FakeModeration(False))

    assert understander.calls == 1
    assert memory.appended == ["tư vấn giúp em"]
    assert len(memory.committed) == 1
    assert result.terminal_reason is None


@pytest.mark.asyncio
async def test_canonical_dung_helper_mien_chu_khong_tu_chuan_hoa() -> None:
    moderation = FakeModeration(False)
    await _turn(moderation, user_message="Bốc CHÁY!! b0c ch4y")

    seen_message, canonical = moderation.seen[0]
    assert seen_message == "Bốc CHÁY!! b0c ch4y"
    assert canonical.original == "bốc cháy b0c ch4y"
    assert canonical.leet_decoded.split() == ["boc", "chay", "boc", "chay"]


@pytest.mark.asyncio
async def test_moderation_hong_thi_luot_van_chay() -> None:
    """Fail-open: một lần timeout không được là công tắc cắt dịch vụ."""

    result, memory, understander = await _turn(FakeModeration(TimeoutError("provider 504")))

    assert understander.calls == 1
    assert len(memory.committed) == 1
    assert result.answer


@pytest.mark.asyncio
async def test_khong_cam_moderation_thi_luot_van_chay() -> None:
    result, _, understander = await _turn(None)

    assert understander.calls == 1
    assert result.answer
