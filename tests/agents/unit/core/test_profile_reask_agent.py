"""Móc 3 — agent trả lời khi câu hỏi hồ sơ bị LẶP (mở rộng plan §1.3, GĐ-9).

Plan cố ý chừa chặng `COLLECTING`/`GREETING` ra khỏi móc 1. Đo trên máy thật
2026-09-23 cho thấy đó chính là chỗ lượt hỏng dồn về: khách hỏi ba câu liên
tiếp, cả ba nhận đúng một câu hồ sơ, và lượt thứ tư chạm `MAX_ASKS` rồi bị đẩy
sang tư vấn viên.

Bất biến giữ nguyên như hai móc kia: cờ TẮT → chữ tất định y như trước, agent
hỏng → cũng vậy, và câu hỏi treo KHÔNG được mất.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, VehiclePitch
from src.agents.core.act import act, is_profile_reask
from src.agents.core.actions import PENDING_PROFILE, Ask
from src.agents.core.state import CoreState, PendingKind, Stage
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.ports import AgentLoopOutcome
from src.agents.prompts.question_variants import PROFILE_VARIANTS
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
ANSWER = "Dạ xe điện đi trong phố tiết kiệm hơn xe xăng vì tiền điện rẻ hơn tiền xăng ạ."

pytestmark = pytest.mark.asyncio


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="VF 5, VF 6",
            pitches=(
                VehiclePitch(vehicle_id=UUID(V1), rank=1, display_name="VinFast VF 5", pitch=""),
                VehiclePitch(vehicle_id=UUID(V2), rank=2, display_name="VinFast VF 6", pitch=""),
            ),
        )


class _Flag:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    async def load(self, name: str) -> AgentFlagState:
        return AgentFlagState(name=name, enabled=self.enabled, rollout_percent=100)


class _Loop:
    def __init__(self, outcome: AgentLoopOutcome | None = None) -> None:
        self.outcome = outcome or AgentLoopOutcome(answer=ANSWER, llm_calls=2)
        self.calls = 0

    async def run(self, **kwargs: Any) -> AgentLoopOutcome:
        self.calls += 1
        return self.outcome


class _Snapshotting:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, ...]] = []

    async def snapshot(self, *, run_id: UUID, candidate_ids: Any, assertions: Any) -> None:
        self.calls.append(tuple(candidate_ids))


class _Verification:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def verify(self, *, run_id: UUID, draft_answer: str) -> bool:
        return self.ok


class _GateConfig:
    standard_promotions: frozenset[str] = frozenset()


class _Gate:
    config = _GateConfig()


def _services(*, agent: bool, **extra: Any) -> AgentServices:
    base: dict[str, Any] = {
        "catalog_browse": _Catalog(),
        "snapshotting": _Snapshotting(),
        "verification": _Verification(),
        "quote_gate": _Gate(),
        "agent_flag": _Flag(agent),
        "agent_loop": _Loop(),
    }
    base.update(extra)
    return AgentServices(**base)


def _state(asked: int) -> CoreState:
    return CoreState(session_id="phien-1", stage=Stage.COLLECTING, ask_counts={PENDING_PROFILE: asked})


async def _ask(services: AgentServices, asked: int, message: str = "so với xe xăng thì sao") -> Any:
    return await act(
        Ask(key=PENDING_PROFILE, kind=PendingKind.SLOT),
        _state(asked),
        services,
        run_id=RUN_ID,
        customer_id="c1",
        user_message=message,
    )


# ---------------------------------------------------------------- cổng vào


async def test_lan_hoi_dau_khong_goi_agent() -> None:
    """Lượt đầu chưa phải ngõ cụt — không tốn một call LLM nào."""

    loop = _Loop()
    await _ask(_services(agent=True, agent_loop=loop), asked=1)
    assert loop.calls == 0


async def test_lan_hoi_dau_khong_can_run() -> None:
    assert is_profile_reask(Ask(key=PENDING_PROFILE, kind=PendingKind.SLOT), _state(1)) is False
    assert is_profile_reask(Ask(key=PENDING_PROFILE, kind=PendingKind.SLOT), _state(2)) is True
    assert is_profile_reask(Ask(key="registration_province", kind=PendingKind.SLOT), _state(2)) is False


async def test_co_tat_thi_khong_goi_llm_va_ra_dung_chu_cu() -> None:
    loop = _Loop()
    off = await _ask(_services(agent=False, agent_loop=loop), asked=2)
    assert loop.calls == 0
    assert any(variant in off.text for variant in PROFILE_VARIANTS)
    assert ANSWER not in off.text


# ---------------------------------------------------------------- đường agent


async def test_agent_tra_loi_roi_van_hoi_tiep_cau_ho_so() -> None:
    result = await _ask(_services(agent=True), asked=2)
    assert result.text.startswith("Dạ xe điện đi trong phố")
    assert any(variant in result.text for variant in PROFILE_VARIANTS), "câu hỏi treo KHÔNG được mất"


async def test_pending_van_treo_nguyen() -> None:
    """Đổi chữ không được đổi việc: lượt sau khách đáp vẫn là SLOT_ANSWER."""

    result = await _ask(_services(agent=True), asked=2)
    pending = result.state_patch["pending"]
    assert pending.key == PENDING_PROFILE and pending.kind is PendingKind.SLOT


async def test_snapshot_lay_xe_tu_catalog_khi_chua_de_xuat_gi() -> None:
    """Chặng thu thập chưa có `recommended_ids` — evidence lấy từ cửa catalog."""

    snap = _Snapshotting()
    await _ask(_services(agent=True, snapshotting=snap), asked=2)
    assert snap.calls and set(snap.calls[0]) == {UUID(V1), UUID(V2)}


async def test_agent_hong_thi_ra_dung_chu_cu() -> None:
    loop = _Loop(AgentLoopOutcome(answer=None, error="max_steps"))
    on = await _ask(_services(agent=True, agent_loop=loop), asked=2)
    off = await _ask(_services(agent=False), asked=2)
    assert loop.calls == 1
    assert on.text == off.text


async def test_verify_tu_choi_thi_ra_dung_chu_cu() -> None:
    on = await _ask(_services(agent=True, verification=_Verification(ok=False)), asked=2)
    off = await _ask(_services(agent=False), asked=2)
    assert on.text == off.text


async def test_quote_gate_chan_thi_ra_dung_chu_cu() -> None:
    loop = _Loop(AgentLoopOutcome(answer="Dạ em giảm thêm cho anh/chị một chút ạ."))
    on = await _ask(_services(agent=True, agent_loop=loop), asked=2)
    off = await _ask(_services(agent=False), asked=2)
    assert on.text == off.text
