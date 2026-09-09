"""Kiểu trạng thái lõi v2 và cạnh chặng hợp lệ (spec mục 4)."""

from __future__ import annotations

import pytest

from src.agents.core.state import (
    UNCLEAR_UNDERSTANDING,
    CoreState,
    DialogueAct,
    Intent,
    Pending,
    PendingKind,
    Stage,
    can_transition,
)
from src.agents.domain.values import SlotName


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (Stage.GREETING, Stage.COLLECTING),
        (Stage.GREETING, Stage.RECOMMENDED),  # khách nhắn một câu đủ slot ngay lúc chào
        (Stage.COLLECTING, Stage.RECOMMENDED),
        (Stage.RECOMMENDED, Stage.CHOSEN),
        (Stage.CHOSEN, Stage.RECOMMENDED),
        (Stage.CHOSEN, Stage.COSTING),
        (Stage.CHOSEN, Stage.SCHEDULING),
        (Stage.CHOSEN, Stage.OFFER_REVIEW),
        (Stage.COSTING, Stage.CHOSEN),
        (Stage.SCHEDULING, Stage.CHOSEN),
        (Stage.OFFER_REVIEW, Stage.CHOSEN),
        (Stage.OFFER_REVIEW, Stage.HANDED_OFF),
        (Stage.GREETING, Stage.HANDED_OFF),
        (Stage.COSTING, Stage.HANDED_OFF),
        (Stage.HANDED_OFF, Stage.CHOSEN),
        (Stage.RECOMMENDED, Stage.COLLECTING),  # RESTART
        (Stage.SCHEDULING, Stage.COLLECTING),  # RESTART
    ],
)
def test_canh_hop_le(src: Stage, dst: Stage) -> None:
    assert can_transition(src, dst)


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (Stage.COLLECTING, Stage.CHOSEN),
        (Stage.RECOMMENDED, Stage.COSTING),
        # (COSTING, SCHEDULING) đã thành cạnh HỢP LỆ 2026-08-31: xem chi phí xong đặt lịch là hành trình thường.
        (Stage.HANDED_OFF, Stage.RECOMMENDED),
    ],
)
def test_canh_cam(src: Stage, dst: Stage) -> None:
    assert not can_transition(src, dst)


def test_o_nguyen_chang_luon_hop_le() -> None:
    for stage in Stage:
        assert can_transition(stage, stage)


def test_core_state_mac_dinh_va_with() -> None:
    state = CoreState(session_id="s1")
    assert state.stage is Stage.GREETING
    assert state.intent is Intent.NONE
    assert state.slots == {}
    assert state.pending is None
    changed = state.with_(stage=Stage.COLLECTING, slots={SlotName.VEHICLE_TYPE: "CAR"})
    assert changed.stage is Stage.COLLECTING
    assert changed.slots[SlotName.VEHICLE_TYPE] == "CAR"
    assert state.stage is Stage.GREETING  # bất biến


def test_pending_va_unclear() -> None:
    pending = Pending(kind=PendingKind.SLOT, key="purpose", options=("đi làm", "giao hàng"))
    assert pending.options == ("đi làm", "giao hàng")
    assert UNCLEAR_UNDERSTANDING.dialogue_act is DialogueAct.UNCLEAR
    assert UNCLEAR_UNDERSTANDING.confidence == 0.0
