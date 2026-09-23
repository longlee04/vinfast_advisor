"""Móc 2 — ba ngõ cụt của `_recommend` (plan agent-migration Bước 7).

Cờ TẮT: từng ký tự phải giống hệt `_no_better` / `_same_pick` /
`_nearest_by_price` của hôm nay. Cờ BẬT: agent trả lời thì THẺ XE vẫn giữ, và
điểm ngõ cụt đầu tiên (candidates rỗng — chạy TRƯỚC `snapshot` của `_recommend`)
phải tự snapshot, nếu không `verify` từ chối mọi con số.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from src.agents.contracts import CatalogBrowseResult, FilterCriteria, Recommendation, VehiclePitch
from src.agents.core.act import ActResult, act
from src.agents.core.actions import REASON_RETRY, Recommend
from src.agents.core.state import CoreState, Stage
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.values import SlotName as N
from src.agents.ports import AgentLoopOutcome
from src.agents.services.registry import AgentServices

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
RUN_ID = UUID("99999999-9999-9999-9999-999999999999")
ANSWER = "Dạ, hai mẫu đang hiện đều hợp nhu cầu đi trong phố của anh/chị ạ."
CAR_FULL = {N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 1_000_000_000, N.PURPOSE: "đi làm", N.PASSENGER_COUNT: 5}

pytestmark = pytest.mark.asyncio


class _Catalog:
    async def answer(self, *, user_message: str, vehicle_type_hint: str | None = None) -> CatalogBrowseResult:
        return CatalogBrowseResult(
            answer="VF 5, VF 6",
            pitches=(
                VehiclePitch(
                    vehicle_id=UUID(V1),
                    rank=1,
                    display_name="VinFast VF 5",
                    pitch="",
                    starting_price_vnd=Decimal("458000000"),
                ),
                VehiclePitch(
                    vehicle_id=UUID(V2),
                    rank=2,
                    display_name="VinFast VF 6",
                    pitch="",
                    starting_price_vnd=Decimal("675000000"),
                ),
            ),
        )


class _Retrieval:
    """`layer1` trả về danh sách đã hẹn — rỗng là ngõ cụt thứ nhất."""

    def __init__(self, candidates: list[UUID] | None = None) -> None:
        self.candidates = [] if candidates is None else candidates

    async def layer1(self, criteria: FilterCriteria) -> list[UUID]:
        return list(self.candidates)

    async def layer2(self, *, utterance: str, vehicle_type: str, candidate_ids: Any) -> list:
        return []


class _Recommendation:
    def __init__(self, items: list[Recommendation] | None = None) -> None:
        self.items = items if items is not None else []

    async def recommend(self, run_id: UUID, **_: Any) -> list[Recommendation]:
        return list(self.items)


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


class _GateConfig:
    standard_promotions: frozenset[str] = frozenset()


class _Gate:
    config = _GateConfig()


def _services(*, agent: bool, retrieval: _Retrieval, recommendation: _Recommendation, **extra: Any) -> AgentServices:
    base: dict[str, Any] = {
        "catalog_browse": _Catalog(),
        "retrieval": retrieval,
        "recommendation": recommendation,
        "snapshotting": _Snapshotting(),
        "verification": _Verification(),
        "quote_gate": _Gate(),
        "agent_flag": _Flag(agent),
        "agent_loop": _Loop(),
    }
    base.update(extra)
    return AgentServices(**base)


def _state(**kw: Any) -> CoreState:
    base: dict[str, Any] = {"stage": Stage.RECOMMENDED, "slots": CAR_FULL, "recommended_ids": (V1, V2)}
    base.update(kw)
    return CoreState(session_id="s1", **base)


async def _recommend(services: AgentServices, state: CoreState, action: Recommend) -> ActResult:
    return await act(action, state, services, run_id=RUN_ID, customer_id="c1", user_message="rẻ hơn được không")


# ---------------------------------------------------------------- cờ TẮT: chữ cũ


async def test_co_tat_thi_ra_dung_no_better_cu() -> None:
    """Ngõ cụt 1 + `refine`: `_no_better`."""

    action = Recommend(refine="rẻ hơn được không")
    off = await _recommend(_services(agent=False, retrieval=_Retrieval(), recommendation=_Recommendation()), _state(), action)
    assert "chưa có mẫu nào" in off.text or "chưa tìm" in off.text
    assert off.cards.get("recommendations")  # THẺ được giữ


async def test_co_tat_thi_ra_dung_same_pick_cu() -> None:
    """Ngõ cụt 3: cùng bộ xe → `_same_pick(ids=...)`, và `state_patch` giữ nguyên."""

    items = [
        Recommendation(vehicle_id=UUID(V1), rank=1, reasons=["đủ chỗ"], display_name="VinFast VF 5"),
        Recommendation(vehicle_id=UUID(V2), rank=2, reasons=["đi xa"], display_name="VinFast VF 6"),
    ]
    services = _services(
        agent=False, retrieval=_Retrieval([UUID(V1), UUID(V2)]), recommendation=_Recommendation(items)
    )
    result = await _recommend(services, _state(), Recommend())
    assert "VF 5" in result.text
    assert result.state_patch.get("recommended_ids") == (V1, V2)


async def test_co_tat_thi_ra_dung_nearest_by_price_cu() -> None:
    """Ngõ cụt 1, không `refine`, không `retry`: `_nearest_by_price`."""

    state = _state(recommended_ids=(), slots={**CAR_FULL, N.BUDGET_MAX_VND: 500_000_000})
    services = _services(agent=False, retrieval=_Retrieval(), recommendation=_Recommendation())
    result = await _recommend(services, state, Recommend())
    assert "VF 5" in result.text  # hai mẫu gần giá nhất, đọc từ catalog tất định


async def test_retry_ra_dung_same_pick_cu() -> None:
    services = _services(agent=False, retrieval=_Retrieval(), recommendation=_Recommendation())
    result = await _recommend(services, _state(), Recommend(reason=REASON_RETRY))
    assert "VF 5" in result.text


# ---------------------------------------------------------------- cờ BẬT


async def test_diem_1445_tu_snapshot_truoc_khi_verify() -> None:
    """Ngõ cụt ĐẦU chạy TRƯỚC `snapshot` của `_recommend` → handler tự snapshot.

    Thiếu bước này thì `run_evidence` rỗng và `verify` từ chối mọi con số.
    """

    snap = _Snapshotting()
    services = _services(
        agent=True, retrieval=_Retrieval(), recommendation=_Recommendation(), snapshotting=snap
    )
    result = await _recommend(services, _state(), Recommend(refine="rẻ hơn được không"))
    assert snap.calls and set(snap.calls[0]) == {UUID(V1), UUID(V2)}
    assert ANSWER in result.text


async def test_the_xe_van_giu_khi_agent_tra_loi() -> None:
    services = _services(agent=True, retrieval=_Retrieval(), recommendation=_Recommendation())
    result = await _recommend(services, _state(), Recommend(refine="rẻ hơn"))
    assert result.cards.get("recommendations")
    assert result.state_patch == {}


async def test_agent_hong_thi_ve_same_pick() -> None:
    """Loop không ra câu trả lời → ĐÚNG chữ của nhánh cũ, không câu riêng nào."""

    loop = _Loop(AgentLoopOutcome(answer=None, error="max_steps"))
    services_on = _services(
        agent=True, retrieval=_Retrieval(), recommendation=_Recommendation(), agent_loop=loop
    )
    on = await _recommend(services_on, _state(), Recommend(reason=REASON_RETRY))
    off = await _recommend(
        _services(agent=False, retrieval=_Retrieval(), recommendation=_Recommendation()),
        _state(),
        Recommend(reason=REASON_RETRY),
    )
    assert loop.calls == 1
    assert on.text == off.text


async def test_verify_tu_choi_thi_ve_chu_cu() -> None:
    services_on = _services(
        agent=True, retrieval=_Retrieval(), recommendation=_Recommendation(), verification=_Verification(ok=False)
    )
    on = await _recommend(services_on, _state(), Recommend(refine="rẻ hơn"))
    off = await _recommend(
        _services(agent=False, retrieval=_Retrieval(), recommendation=_Recommendation()),
        _state(),
        Recommend(refine="rẻ hơn"),
    )
    assert on.text == off.text


async def test_ngo_cut_3_agent_tra_loi_van_giu_danh_sach_xe() -> None:
    """Agent trả lời ở ngõ cụt "cùng bộ xe": không được xoá `recommended_ids`."""

    items = [
        Recommendation(vehicle_id=UUID(V1), rank=1, reasons=["đủ chỗ"], display_name="VinFast VF 5"),
        Recommendation(vehicle_id=UUID(V2), rank=2, reasons=["đi xa"], display_name="VinFast VF 6"),
    ]
    services = _services(agent=True, retrieval=_Retrieval([UUID(V1), UUID(V2)]), recommendation=_Recommendation(items))
    result = await _recommend(services, _state(), Recommend())
    assert ANSWER in result.text
    assert result.cards.get("recommendations")
    assert result.state_patch == {}  # agent KHÔNG ghi state
