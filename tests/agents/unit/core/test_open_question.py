"""Móc 1 + handler `_open_question` (plan agent-migration Bước 6).

Bất biến lớn nhất: cờ TẮT thì KHÔNG một call LLM nào được phát và chữ ra khách
GIỐNG HỆT `Reply(TEMPLATE_CLARIFY)` của hôm nay. Cờ BẬT mà bất kỳ cửa nào trượt
thì cũng rơi về đúng chữ đó — agent không có "câu an toàn riêng".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, VehiclePitch
from src.agents.core import render
from src.agents.core.act import ActResult, act
from src.agents.core.actions import OPEN_REASON_UNCLEAR, TEMPLATE_CLARIFY, OpenQuestion, Reply
from src.agents.core.state import CoreState, Pending, PendingKind, Stage
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.agent_tools import AGENT_TOOL_DANH_MUC, AgentToolCall
from src.agents.ports import AgentLoopOutcome
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
CUSTOMER = "c1"
ANSWER = "Dạ, VF 5 hợp với nhu cầu đi trong phố của anh/chị vì xe nhỏ gọn ạ."

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
    def __init__(self, enabled: bool = True) -> None:
        self.state = AgentFlagState(name="agent_fallback", enabled=enabled, rollout_percent=100)
        self.calls = 0

    async def load(self, name: str) -> AgentFlagState:
        self.calls += 1
        return self.state


class _Loop:
    """Agent loop giả — đếm số lần bị gọi, trả sẵn một outcome."""

    def __init__(self, outcome: AgentLoopOutcome | None = None, *, boom: Exception | None = None) -> None:
        self.outcome = outcome or AgentLoopOutcome(answer=ANSWER, steps=({"tool": "x", "ok": True},), llm_calls=2)
        self.calls = 0
        self.boom = boom
        self.executed: list[AgentToolCall] = []

    async def run(self, **kwargs: Any) -> AgentLoopOutcome:
        self.calls += 1
        if self.boom is not None:
            raise self.boom
        self._execute = kwargs["execute"]
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


class _QuoteGate:
    config = _GateConfig()


def _services(**overrides: Any) -> AgentServices:
    base: dict[str, Any] = {
        "catalog_browse": _Catalog(),
        "agent_flag": _Flag(),
        "agent_loop": _Loop(),
        "snapshotting": _Snapshotting(),
        "verification": _Verification(),
        "quote_gate": _QuoteGate(),
    }
    base.update(overrides)
    return AgentServices(**base)


def _state(**kw: Any) -> CoreState:
    base: dict[str, Any] = {"stage": Stage.RECOMMENDED, "recommended_ids": (V1, V2)}
    base.update(kw)
    return CoreState(session_id="s1", **base)


async def _run(services: AgentServices, state: CoreState | None = None, **kw: Any) -> ActResult:
    action = OpenQuestion(question="tính năng nào phù hợp với anh nhất", reason=OPEN_REASON_UNCLEAR)
    return await act(
        action,
        state or _state(),
        services,
        run_id=kw.pop("run_id", RUN_ID),
        customer_id=kw.pop("customer_id", CUSTOMER),
        user_message="tính năng nào phù hợp với anh nhất",
    )


async def _clarify_text(state: CoreState, services: AgentServices) -> str:
    result = await act(
        Reply(template=TEMPLATE_CLARIFY, args={"stage": state.stage.value}),
        state,
        services,
        run_id=None,
        customer_id=CUSTOMER,
        user_message="x",
    )
    return result.text


# ---------------------------------------------------------------- cờ TẮT


async def test_co_tat_thi_khong_goi_llm() -> None:
    loop = _Loop()
    services = _services(agent_flag=_Flag(enabled=False), agent_loop=loop)
    await _run(services)
    assert loop.calls == 0


async def test_khong_cam_agent_flag_thi_khong_goi_llm() -> None:
    loop = _Loop()
    await _run(_services(agent_flag=None, agent_loop=loop))
    assert loop.calls == 0


async def test_co_tat_thi_ra_dung_chu_cu() -> None:
    state = _state()
    services = _services(agent_flag=_Flag(enabled=False))
    result = await _run(services, state)
    assert result.text == await _clarify_text(state, services)
    assert result.cards == {} and result.state_patch == {}


# ---------------------------------------------------------------- cổng cứng


async def test_handed_off_khong_goi_agent() -> None:
    loop = _Loop()
    services = _services(agent_loop=loop)
    await _run(services, _state(stage=Stage.HANDED_OFF))
    assert loop.calls == 0


async def test_pending_confirm_khong_goi_agent() -> None:
    loop = _Loop()
    services = _services(agent_loop=loop)
    pending = Pending(kind=PendingKind.CONFIRM, key="book", options=("14h",))
    await _run(services, _state(pending=pending))
    assert loop.calls == 0


async def test_agent_loop_none_thi_fallback() -> None:
    state = _state()
    services = _services(agent_loop=None)
    assert (await _run(services, state)).text == await _clarify_text(state, services)


async def test_snapshot_rong_thi_fallback() -> None:
    """Không có xe nào để snapshot → `verify` chắc chắn từ chối, đừng tốn call."""

    loop = _Loop()
    snap = _Snapshotting()
    services = _services(agent_loop=loop, snapshotting=snap)
    await _run(services, _state(recommended_ids=(), chosen_vehicle_id=None))
    assert loop.calls == 0 and snap.calls == []


async def test_run_id_none_thi_fallback() -> None:
    loop = _Loop()
    await _run(_services(agent_loop=loop), run_id=None)
    assert loop.calls == 0


# ---------------------------------------------------------------- ba cửa


async def test_verify_tu_choi_thi_fallback() -> None:
    state = _state()
    services = _services(verification=_Verification(ok=False))
    assert (await _run(services, state)).text == await _clarify_text(state, services)


async def test_quote_gate_chan_thi_fallback() -> None:
    state = _state()
    loop = _Loop(AgentLoopOutcome(answer="Dạ em giảm cho anh/chị thêm một chút ạ."))
    services = _services(agent_loop=loop)
    assert (await _run(services, state)).text == await _clarify_text(state, services)
    assert loop.calls == 1  # đã chạy, nhưng chữ bị chặn


async def test_render_error_thi_fallback() -> None:
    state = _state()
    loop = _Loop(AgentLoopOutcome(answer="Dạ mẫu này có LFP_BATTERY rất bền ạ."))
    services = _services(agent_loop=loop)
    text = (await _run(services, state)).text
    assert "LFP_BATTERY" not in text
    assert text == await _clarify_text(state, services)


async def test_exception_la_thi_fallback_khong_thoat_len_act() -> None:
    state = _state()
    services = _services(agent_loop=_Loop(boom=RuntimeError("provider chet")))
    assert (await _run(services, state)).text == await _clarify_text(state, services)


# ---------------------------------------------------------------- đường thành công


async def test_agent_tra_loi_thi_dung_chu_cua_agent() -> None:
    result = await _run(_services())
    assert ANSWER in result.text
    assert render.assert_clean(result.text) == result.text


async def test_state_patch_rong() -> None:
    result = await _run(_services())
    assert result.state_patch == {}


async def test_khong_dat_hitl_request() -> None:
    assert (await _run(_services())).hitl_request is None


async def test_tool_calls_duoc_ghi_vao_actresult() -> None:
    result = await _run(_services())
    assert result.tool_calls  # vệt bước agent đi vào trace
    assert all(isinstance(step, dict) for step in result.tool_calls)


async def test_snapshot_dung_bo_xe_dang_xet() -> None:
    snap = _Snapshotting()
    await _run(_services(snapshotting=snap), _state(chosen_vehicle_id=V1))
    assert snap.calls and set(snap.calls[0]) == {UUID(V1), UUID(V2)}


async def test_the_xe_van_giu_khi_agent_tra_loi() -> None:
    result = await _run(_services())
    assert result.cards.get("recommendations")


async def test_executor_chi_chay_tool_chi_doc() -> None:
    """Bộ chạy tool từ chối mọi tên ngoài registry — không có đường tới `Book`."""

    loop = _Loop()
    await _run(_services(agent_loop=loop))
    execute = loop._execute
    for forbidden in ("dat_lich_lai_thu", "handoff", "showroom_options"):
        assert (await execute(AgentToolCall(name=forbidden, args={}))).error == "unknown_tool"
    ok = await execute(AgentToolCall(name=AGENT_TOOL_DANH_MUC, args={"vehicle_type": "CAR"}))
    assert ok.ok is True and "VinFast VF 5" in ok.payload["vehicles"]
