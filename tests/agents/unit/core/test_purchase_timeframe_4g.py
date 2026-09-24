"""Customer 360 4G: câu hỏi lồng thời điểm mua sau báo giá lăn bánh.

Bất biến quan trọng nhất: cờ `agent_ask_purchase_timeframe` TẮT (hoặc chưa cắm
cổng, hoặc đọc hỏng) thì lượt lăn bánh y nguyên như trước 4G.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.agents.core import render
from src.agents.core.act import act
from src.agents.core.actions import TEMPLATE_TIMEFRAME_ACK, OnRoadPrice, Reply
from src.agents.core.policy import decide
from src.agents.core.run_turn import _with_purchase_timeframe
from src.agents.core.state import CoreState, DialogueAct, Intent, Stage, Understanding
from src.agents.domain.agent_flag import AgentFlagState
from src.agents.domain.purchase_timeframe import (
    ASK_KEY,
    FLAG_ASK_PURCHASE_TIMEFRAME,
    ONE_TO_THREE_MONTHS,
    OVER_6_MONTHS,
    QUICK_REPLIES,
    THREE_TO_SIX_MONTHS,
    UNDECIDED,
    WITHIN_1_MONTH,
    parse_purchase_timeframe,
)
from src.agents.domain.values import SlotName as N
from src.agents.services.registry import AgentServices
from tests.agents.unit.core.test_act_on_road import V1, _Catalog, _Tco


class _Flags:
    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled

    async def load(self, name: str) -> AgentFlagState | None:
        assert name == FLAG_ASK_PURCHASE_TIMEFRAME
        return AgentFlagState(name=name, enabled=self._enabled, rollout_percent=100)


class _Known:
    def __init__(self, known: bool = False, *, error: bool = False) -> None:
        self._known = known
        self._error = error
        self.calls: list[str] = []

    async def known(self, customer_id: str) -> bool:
        self.calls.append(customer_id)
        if self._error:
            raise RuntimeError("db down")
        return self._known


def _state(**changes: object) -> CoreState:
    base = CoreState(
        session_id="s1", stage=Stage.CHOSEN, chosen_vehicle_id=V1, slots={N.VEHICLE_TYPE: "CAR"}, turn_count=4
    )
    return base.with_(**changes) if changes else base


def _services(*, flag: bool | None, known: _Known | None) -> AgentServices:
    return AgentServices(
        tco_estimation=_Tco(),
        catalog_browse=_Catalog(),
        agent_flag=_Flags(enabled=flag) if flag is not None else None,
        purchase_timeframe_known=known,
    )


async def _on_road(services: AgentServices, state: CoreState):
    return await act(
        OnRoadPrice(vehicle_id=V1), state, services, run_id=None, customer_id="c1", user_message="vf5 lăn bánh"
    )


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Trong tháng này", WITHIN_1_MONTH),
        ("tuần sau em qua lấy luôn", WITHIN_1_MONTH),
        ("1–3 tháng tới", ONE_TO_THREE_MONTHS),
        ("chắc tháng sau", ONE_TO_THREE_MONTHS),
        ("khoảng 2 tháng nữa", ONE_TO_THREE_MONTHS),
        ("3–6 tháng tới", THREE_TO_SIX_MONTHS),
        ("cuối năm", THREE_TO_SIX_MONTHS),
        ("sang năm mới mua", OVER_6_MONTHS),
        ("Chưa vội", UNDECIDED),
        ("em đang tham khảo thôi", UNDECIDED),
        ("vf5 có mấy màu", None),
        ("", None),
    ],
)
def test_parse_purchase_timeframe(text: str, code: str | None) -> None:
    assert parse_purchase_timeframe(text) == code


def test_moi_nut_tra_loi_nhanh_parse_duoc() -> None:
    assert all(parse_purchase_timeframe(label) for label in QUICK_REPLIES)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "known"),
    [(None, _Known()), (False, _Known()), (True, None), (True, _Known(known=True)), (True, _Known(error=True))],
    ids=["chua-cam-co", "co-tat", "chua-cam-cong", "da-biet", "doc-loi"],
)
async def test_khong_hoi_thi_luot_lan_banh_y_nguyen(flag: bool | None, known: _Known | None) -> None:
    baseline = await _on_road(_services(flag=None, known=None), _state())
    result = await _on_road(_services(flag=flag, known=known), _state())
    assert result.text == baseline.text
    assert "quick_replies" not in result.cards
    assert dict(result.state_patch) == {}


@pytest.mark.asyncio
async def test_co_bat_va_chua_biet_thi_hoi_thay_cau_ket() -> None:
    known = _Known()
    result = await _on_road(_services(flag=True, known=known), _state())

    assert known.calls == ["c1"]
    assert "tco_card" in result.cards
    assert "khi nào" in result.text
    assert "Đặt lái thử" not in result.text  # một lượt một câu hỏi
    assert [item.label for item in result.cards["quick_replies"]] == list(QUICK_REPLIES)
    assert result.state_patch["ask_counts"] == {ASK_KEY: 4}


@pytest.mark.asyncio
async def test_phien_da_hoi_thi_khong_hoi_lai() -> None:
    known = _Known()
    result = await _on_road(_services(flag=True, known=known), _state(ask_counts={ASK_KEY: 2}))
    assert known.calls == []
    assert "quick_replies" not in result.cards


def _understanding(**changes: object) -> Understanding:
    return Understanding(dialogue_act=DialogueAct.UNCLEAR, intent=Intent.NONE, **changes)


def test_run_turn_chi_gan_ma_o_luot_ngay_sau_cau_hoi() -> None:
    asked = _state(ask_counts={ASK_KEY: 4})
    assert _with_purchase_timeframe(_understanding(), asked, "tháng sau").purchase_timeframe == ONE_TO_THREE_MONTHS
    later = asked.with_(turn_count=6)
    assert _with_purchase_timeframe(_understanding(), later, "tháng sau").purchase_timeframe == ""
    assert _with_purchase_timeframe(_understanding(), _state(), "tháng sau").purchase_timeframe == ""
    assert _with_purchase_timeframe(_understanding(), asked, "vf5 mấy màu").purchase_timeframe == ""


def test_policy_ghi_nhan_cau_tra_loi() -> None:
    decision = decide(_state(), _understanding(purchase_timeframe=WITHIN_1_MONTH))
    assert decision.action == Reply(template=TEMPLATE_TIMEFRAME_ACK, args={"timeframe": WITHIN_1_MONTH})


def _is_ack(action: object) -> bool:
    return isinstance(action, Reply) and action.template == TEMPLATE_TIMEFRAME_ACK


def test_policy_cau_co_viec_khac_di_duong_thuong() -> None:
    with_vehicle = replace(_understanding(purchase_timeframe=WITHIN_1_MONTH), vehicle_ids=(V1,))
    assert not _is_ack(decide(_state(), with_vehicle).action)
    request = Understanding(
        dialogue_act=DialogueAct.REQUEST, intent=Intent.TEST_DRIVE, purchase_timeframe=WITHIN_1_MONTH
    )
    assert not _is_ack(decide(_state(), request).action)


def test_render_ghi_nhan_roi_ket_theo_checklist() -> None:
    ack = Reply(template=TEMPLATE_TIMEFRAME_ACK, args={"timeframe": WITHIN_1_MONTH})
    text = render.render_reply(ack, vehicle_name="VF 5", closing="Đặt lái thử VF 5 luôn nhé?")
    assert text == "Dạ em ghi nhận anh/chị dự định nhận xe trong tháng này. Đặt lái thử VF 5 luôn nhé?"
    undecided = Reply(template=TEMPLATE_TIMEFRAME_ACK, args={"timeframe": UNDECIDED})
    assert "thong thả" in render.render_reply(undecided, closing="Đặt lái thử VF 5 luôn nhé?")
