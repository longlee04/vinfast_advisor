"""Payload trace của lõi v2 phải nói được cuối lượt còn treo câu hỏi hay không.

Chỉ số 2 (spec mục 8) đo "lượt ngay sau khi bot vừa hỏi". Lõi v1 đọc
`payload.outcome.has_pending_question`; lõi v2 đọc khoá `pending_after` này.

Suy từ `ask_counts` là SAI: `ask_counts` chỉ tăng, còn pending bị xoá ngay khi
khách trả lời — hai đại lượng khác nhau, nên phải có khoá tường minh.
"""

from __future__ import annotations

from src.agents.core.run_turn import trace_payload
from src.agents.core.state import CoreState, Pending, PendingKind, Stage


def test_pending_after_none_khi_khong_treo() -> None:
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, pending=None)
    payload = trace_payload(state_before=Stage.COLLECTING, state_after=state, action_name="Recommend")
    assert payload["core"] == "v2"
    assert payload["pending_after"] is None


def test_pending_after_co_kind_key_va_luot_hoi() -> None:
    pending = Pending(kind=PendingKind.SLOT, key="purpose", options=("đi làm",), asked_at_turn=3)
    state = CoreState(session_id="s1", stage=Stage.COLLECTING, pending=pending, turn_count=3)
    payload = trace_payload(state_before=Stage.COLLECTING, state_after=state, action_name="Ask")
    assert payload["pending_after"] == {"kind": "SLOT", "key": "purpose", "asked_at_turn": 3}


def test_pending_after_khong_chep_options() -> None:
    pending = Pending(
        kind=PendingKind.CHOICE,
        key="vehicle",
        options=("2b0d0c9e-0000-0000-0000-000000000001",),
        asked_at_turn=5,
    )
    state = CoreState(session_id="s1", stage=Stage.RECOMMENDED, pending=pending, turn_count=5)
    payload = trace_payload(state_before=Stage.RECOMMENDED, state_after=state, action_name="Ask")
    assert "options" not in payload["pending_after"]


def test_extra_di_thang_vao_payload() -> None:
    """`build_core_trace` bơm `understanding`/`resume_pending`/… qua đúng cửa này."""

    state = CoreState(session_id="s1", stage=Stage.COLLECTING)
    payload = trace_payload(
        state_before=Stage.GREETING, state_after=state, action_name="Ask", resume_pending=True, understand_error=None
    )
    assert payload["resume_pending"] is True
    assert payload["understand_error"] is None
    assert payload["stage_before"] == "GREETING"
    assert payload["stage_after"] == "COLLECTING"
