"""Lượt chuyển người của lõi v2 phải GHI ownership, không chỉ đổi cột `stage`.

Món nợ I1 của bước 3: `Handoff` và `EnqueueHitl` chỉ đặt `stage=HANDED_OFF`
trong `conversation_core_state`, mà `HANDED_OFF` lại là CHIẾU của
`conversation_sessions.ownership` (spec mục 4). Ownership vẫn `AI` nghĩa là
`_project_ownership` kéo chặng về `CHOSEN` ngay lượt sau — lượt chuyển người TỰ
XOÁ, và mục duyệt của `EnqueueHitl` không dừng được bot.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agents.contracts import PENDING_HANDOFF_REASON, TurnResult
from src.agents.core import act as act_module
from src.agents.core import run_turn as run_turn_module
from src.agents.core.run_turn import run_turn
from src.agents.core.state import CoreState, Stage
from src.agents.core.understand import RawSlots, RawUnderstanding, UnderstandOutcome
from src.agents.domain.conversation_memory import CoreTurnLease, TurnOutcomeStatus
from src.agents.services.registry import AgentServices
from tests.agents.unit.core.memory_fakes import HonestMemory

SESSION = "aaaaaaaa-0000-0000-0000-000000000009"
V1 = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clear_directory_cache() -> None:
    run_turn_module.reset_vehicle_directory_cache()


def _lease() -> CoreTurnLease:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 9, 1, tzinfo=UTC)
    return CoreTurnLease(
        session_id=UUID(SESSION),
        client_turn_id=uuid4(),
        turn_number=1,
        claim_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=25),
    )


class FakeConversation:
    def __init__(self, state: CoreState | None = None, handed_off: bool = False) -> None:
        self.state = state
        self.handed_off = handed_off
        self.handoff_calls: list[str] = []
        self.transcript_calls = 0

    async def open_session(self, session_id: str, customer_id: str) -> None:
        return None

    async def load_core_state(self, session_id: str) -> CoreState | None:
        return self.state

    async def load_handoff_state(self, session_id: str) -> bool:
        return self.handed_off

    async def read_transcript(self, session_id: str, customer_id: str, limit: int = 50) -> list[Any]:
        self.transcript_calls += 1
        return []

    async def create_run(self, session_id: str, slots: Any = None) -> UUID:
        return uuid4()

    async def set_handoff_pending(self, session_id: str) -> bool:
        self.handoff_calls.append(session_id)
        return True


class FakeUnderstander:
    def __init__(self, outcome: UnderstandOutcome) -> None:
        self._outcome = outcome
        self.calls = 0

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        self.calls += 1
        return self._outcome


def _outcome(*, dialogue_act: str = "REQUEST", intent: str = "ADVISORY") -> UnderstandOutcome:
    return UnderstandOutcome(
        raw=RawUnderstanding(dialogue_act=dialogue_act, intent=intent, slots=RawSlots(), confidence=0.9)
    )


async def _turn(
    outcome: UnderstandOutcome,
    *,
    state: CoreState | None = None,
    handed_off: bool = False,
    user_message: str = "ừ",
) -> tuple[TurnResult, HonestMemory, FakeConversation, FakeUnderstander]:
    conversation = FakeConversation(state=state, handed_off=handed_off)
    memory = HonestMemory()
    understander = FakeUnderstander(outcome)
    result = await run_turn(
        None,
        AgentServices(conversation=conversation, memory=memory),
        session_id=SESSION,
        customer_id="c1",
        user_message=user_message,
        client_turn_id=uuid4(),
        understander=understander,
        lease=_lease(),
    )
    return result, memory, conversation, understander


@pytest.mark.asyncio
async def test_handoff_ghi_ownership_dung_mot_lan() -> None:
    """Quá trần `UNCLEAR` → `Handoff` → ownership PENDING_HANDOFF."""

    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, ask_counts={"__unclear__": 2})
    result, memory, conversation, _ = await _turn(_outcome(dialogue_act="UNCLEAR", intent="NONE"), state=state)

    assert conversation.handoff_calls == [SESSION]
    assert memory.committed[0]["core_state"].stage is Stage.HANDED_OFF
    assert result.answer == act_module.HANDOFF_TEXT


@pytest.mark.asyncio
async def test_handoff_khong_dung_chu_cua_offer_review() -> None:
    """Câu cũ hứa "tư vấn viên đang xem ƯU ĐÃI" — không ưu đãi nào đang được xem."""

    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, ask_counts={"__unclear__": 2})
    result, _, _, _ = await _turn(_outcome(dialogue_act="UNCLEAR", intent="NONE"), state=state)

    assert result.answer is not None
    assert "ưu đãi" not in result.answer
    assert "tư vấn viên" in result.answer


@pytest.mark.asyncio
async def test_enqueue_hitl_cung_ghi_ownership() -> None:
    """Mục duyệt mà không đặt ownership thì bot nói chồng lên bản đang chờ duyệt."""

    state = CoreState(
        session_id=SESSION,
        stage=Stage.CHOSEN,
        chosen_vehicle_id=V1,
        slots={},  # OFFER ở CHOSEN không cần slot nào khác
    )
    _, memory, conversation, _ = await _turn(_outcome(intent="OFFER"), state=state, user_message="có ưu đãi gì không")

    assert conversation.handoff_calls == [SESSION]
    assert memory.committed[0]["core_state"].stage is Stage.OFFER_REVIEW


@pytest.mark.asyncio
async def test_luot_thuong_khong_cham_ownership() -> None:
    _, _, conversation, _ = await _turn(_outcome())

    assert conversation.handoff_calls == []


@pytest.mark.asyncio
async def test_ownership_hong_van_tra_loi_duoc_khach() -> None:
    """Cùng chiều an toàn `chain._mark_handoff_pending`: cờ thiếu < mất câu trả lời."""

    class Exploding(FakeConversation):
        async def set_handoff_pending(self, session_id: str) -> bool:
            raise RuntimeError("db sap")

    conversation = Exploding(
        state=CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, ask_counts={"__unclear__": 2})
    )
    memory = HonestMemory()
    result = await run_turn(
        None,
        AgentServices(conversation=conversation, memory=memory),
        session_id=SESSION,
        customer_id="c1",
        user_message="ừ",
        client_turn_id=uuid4(),
        understander=FakeUnderstander(_outcome(dialogue_act="UNCLEAR", intent="NONE")),
        lease=_lease(),
    )

    assert result.answer == act_module.HANDOFF_TEXT
    assert len(memory.committed) == 1


# --------------------------------------------------- I6: TVV cầm phiên thì bỏ hiểu ý


@pytest.mark.asyncio
async def test_tvv_cam_phien_thi_khong_goi_llm_hieu_y() -> None:
    """`policy.decide` đã chốt `Silent` ngay luật 1 — hiểu ý xong cũng không lái gì."""

    _, _, conversation, understander = await _turn(_outcome(), handed_off=True)

    assert understander.calls == 0, "một lượt bot im lặng không được tốn call LLM"
    assert conversation.transcript_calls == 0, "không hiểu ý thì cũng không cần nạp transcript"


@pytest.mark.asyncio
async def test_tvv_cam_phien_van_ghi_vet_kem_ly_do_bo_qua() -> None:
    """Bỏ vệt thì bộ đo bước 4 đọc phiên HITL ra một lịch sử có lỗ."""

    _, memory, _, _ = await _turn(_outcome(), handed_off=True)

    assert len(memory.committed) == 1
    payload = memory.committed[0]["trace"].payload
    assert payload["understand_skipped"] == "handed_off"
    assert payload["action"] == "Silent"
    assert payload["stage_after"] == Stage.HANDED_OFF.value


@pytest.mark.asyncio
async def test_luot_thuong_ghi_understand_skipped_rong() -> None:
    """Phân biệt được "hiểu ra UNCLEAR" với "không hỏi câu nào" mới đo được."""

    _, memory, conversation, understander = await _turn(_outcome())

    assert understander.calls == 1
    assert conversation.transcript_calls == 1
    assert memory.committed[0]["trace"].payload["understand_skipped"] is None


# ------------------------------------ I1 xen kẽ: cờ đặt xong mà lượt ghi hỏng


class CommitCrashError(RuntimeError):
    """`commit_core_turn` chết SAU khi `set_handoff_pending` đã ghi xong cờ."""


class CrashingMemory(HonestMemory):
    async def commit_core_turn(self, **kwargs: Any) -> TurnResult:
        self.committed.append(kwargs)
        raise CommitCrashError("ghi luot hong")


class OwnershipConversation(FakeConversation):
    """`set_handoff_pending` ghi THẬT: lượt sau `load_handoff_state` thấy cờ.

    Đúng hình dạng thật của hai đường ghi: cờ ownership nằm trên unit-of-work của
    `ConversationService`, còn `conversation_core_state` nằm trên unit-of-work của
    `ConversationMemoryService` — hai transaction khác nhau, hỏng lệch nhau được.
    """

    async def set_handoff_pending(self, session_id: str) -> bool:
        self.handoff_calls.append(session_id)
        self.handed_off = True
        return True


@pytest.mark.asyncio
async def test_commit_hong_sau_khi_dat_co_thi_luot_chet_va_state_khong_ghi() -> None:
    """Lỗi `_commit` KHÔNG được nuốt (docstring `run_turn`): không có gì được ghi
    mà trả `result` như thể xong là hứa với khách một việc chưa xảy ra."""

    stale = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, ask_counts={"__unclear__": 2})
    conversation = OwnershipConversation(state=stale)
    memory = CrashingMemory()

    with pytest.raises(CommitCrashError):
        await run_turn(
            None,
            AgentServices(conversation=conversation, memory=memory),
            session_id=SESSION,
            customer_id="c1",
            user_message="ừ",
            client_turn_id=uuid4(),
            understander=FakeUnderstander(_outcome(dialogue_act="UNCLEAR", intent="NONE")),
            lease=_lease(),
        )

    assert conversation.handoff_calls == [SESSION], "cờ ownership đã ghi xong TRƯỚC khi lượt chết"
    assert conversation.handed_off is True
    assert conversation.state is stale, "hàng core_state KHÔNG được ghi — vẫn là bản cũ, chặng CHOSEN"


@pytest.mark.asyncio
async def test_luot_sau_van_dung_bot_du_hang_core_state_da_cu() -> None:
    """Đây là lý do `_mark_handoff_pending` đặt cờ TRƯỚC `commit_core_turn`.

    Docstring `_mark_handoff_pending` (`run_turn.py:566-577` ở bản review) chốt:
    "hai chiều hỏng không đối xứng: cờ đặt xong mà lượt hỏng → bot im, người vào
    tiếp (an toàn)". Test này khoá đúng vế đó — hàng `conversation_core_state`
    còn CŨ (chặng `CHOSEN`), nhưng `HANDED_OFF` là CHIẾU của ownership chứ không
    phải cột `stage`, nên lượt sau bot vẫn im.
    """

    stale = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, ask_counts={"__unclear__": 2})
    conversation = OwnershipConversation(state=stale)

    with pytest.raises(CommitCrashError):
        await run_turn(
            None,
            AgentServices(conversation=conversation, memory=CrashingMemory()),
            session_id=SESSION,
            customer_id="c1",
            user_message="ừ",
            client_turn_id=uuid4(),
            understander=FakeUnderstander(_outcome(dialogue_act="UNCLEAR", intent="NONE")),
            lease=_lease(),
        )

    # ---- lượt SAU, cùng phiên: memory lành, state đọc lên vẫn là bản cũ
    memory = HonestMemory()
    understander = FakeUnderstander(_outcome())
    result = await run_turn(
        None,
        AgentServices(conversation=conversation, memory=memory),
        session_id=SESSION,
        customer_id="c1",
        user_message="thế xe kia thì sao",
        client_turn_id=uuid4(),
        understander=understander,
        lease=_lease(),
    )

    assert conversation.state.stage is Stage.CHOSEN, "tiền đề: hàng đã ghi vẫn cũ"
    assert understander.calls == 0, "TVV đang cầm phiên thì không hiểu ý (I6)"
    assert result.answer == "", "bot im — cùng hình dạng lõi cũ trả ở nhánh `_handoff_active`"
    assert result.terminal_reason == PENDING_HANDOFF_REASON
    payload = memory.committed[0]["trace"].payload
    assert payload["stage_after"] == Stage.HANDED_OFF.value
    assert payload["action"] == "Silent"
    assert payload["understand_skipped"] == "handed_off"


@pytest.mark.asyncio
async def test_luot_tvv_cam_phien_ghi_duoc_qua_fake_trung_thuc() -> None:
    """Bản bước 3 KHÔNG ghi nổi lượt này — `TurnOutcome.__post_init__` ném ValueError.

    `Silent` trả `answer=None, terminal_reason=None, status=COMPLETED`, mà một
    outcome COMPLETED phải có gì đó trả khách. Tức mọi lượt trong phiên HITL đều
    chết ở bước ghi, và 5000 test đơn vị vẫn xanh vì các fake `commit_core_turn`
    không dựng `TurnOutcome` thật. `HonestMemory` dựng — nên test này chỉ xanh khi
    lượt `Silent` soi gương đúng lõi cũ (`answer=""`, `PENDING_HANDOFF`).
    """

    result, memory, _, understander = await _turn(_outcome(), handed_off=True)

    assert len(memory.outcomes) == 1, "outcome dựng được nghĩa là `__post_init__` đã cho qua"
    outcome = memory.outcomes[0]
    assert outcome.status is TurnOutcomeStatus.COMPLETED
    assert outcome.terminal_reason == PENDING_HANDOFF_REASON
    assert outcome.answer == ""
    assert result.terminal_reason == PENDING_HANDOFF_REASON
    assert understander.calls == 0
    payload = memory.committed[0]["trace"].payload
    assert payload["understand_skipped"] == "handed_off"
    assert payload["action"] == "Silent"


@pytest.mark.asyncio
async def test_dang_cho_duyet_uu_dai_khach_hoi_tiep_bot_van_tra_loi() -> None:
    """Probe H-7 (2026-08-30): sau "Có ưu đãi gì không?" gợi ý "Hỏi thêm về xe" mà bot câm."""

    state = CoreState(session_id=SESSION, stage=Stage.OFFER_REVIEW, chosen_vehicle_id=V1, slots={})
    result, _, _, _ = await _turn(
        _outcome(intent="VEHICLE_QA"), state=state, handed_off=True, user_message="VF 5 sạc bao lâu"
    )

    assert result.answer


@pytest.mark.asyncio
async def test_enqueue_hitl_ghi_muc_hang_duyet() -> None:
    """Prod 2026-08-30: `EnqueueHitl` không nằm trong NEEDS_RUN → run_id None → 0 dòng review_queue."""

    state = CoreState(session_id=SESSION, stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={})
    result, memory, _, _ = await _turn(_outcome(intent="OFFER"), state=state, user_message="có ưu đãi gì không")

    assert result.awaiting_review is True
    assert memory.committed[0].get("advisor_review") is not None
