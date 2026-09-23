"""Năm khoá `agent_*` trong `turn_traces.payload` (plan agent-migration Bước 8).

Hai bất biến: (a) 5 cột VÔ HƯỚNG của `turn_traces` không đổi — mọi SQL cũ chạy
nguyên; (b) vệt agent KHÔNG chứa chữ khách, chỉ tên khoá của args.
"""

from __future__ import annotations

from src.agents.core.run_turn import build_core_trace
from src.agents.core.state import UNCLEAR_UNDERSTANDING, CoreState, Stage

STATE = CoreState(session_id="11111111-1111-1111-1111-111111111111", stage=Stage.RECOMMENDED)
AGENT_STEPS = (
    {"tool": "tinh_chi_phi_xe", "args_keys": ["province", "vehicle_name"], "ok": True, "error": "", "ms": 820},
    {"tool": "tra_loi_khach", "args_keys": [], "ok": True, "error": "", "ms": 640},
    {"tool": "", "args_keys": [], "ok": True, "error": "", "ms": 1600},
)


def _trace(action_name: str, tool_calls: tuple[dict, ...] = ()):
    return build_core_trace(
        session_id=STATE.session_id,
        client_turn_id=None,
        user_message="anh muốn xe nào hợp nhất",
        state_before=STATE,
        state_after=STATE,
        understanding=UNCLEAR_UNDERSTANDING,
        action_name=action_name,
        resume_pending=False,
        understand_error=None,
        tool_calls=tool_calls,
    )


def test_trace_co_agent_fields() -> None:
    payload = _trace("OpenQuestion", AGENT_STEPS).payload
    assert payload["agent_used"] is True
    assert payload["agent_error"] == ""
    assert payload["agent_llm_calls"] == 2
    assert payload["agent_ms"] == 1600
    assert [step["tool"] for step in payload["agent_steps"]] == ["tinh_chi_phi_xe", "tra_loi_khach"]


def test_trace_ghi_ly_do_fallback() -> None:
    steps = ({"tool": "so_sanh_xe", "args_keys": ["vehicle_names"], "ok": False, "error": "unknown_vehicle", "ms": 12},
             {"tool": "", "args_keys": [], "ok": True, "error": "max_steps", "ms": 900})
    payload = _trace("OpenQuestion", steps).payload
    assert payload["agent_error"] == "max_steps"


def test_luot_khong_phai_agent_thi_khong_co_khoa_agent() -> None:
    payload = _trace("Recommend").payload
    assert not any(key.startswith("agent_") for key in payload)


def test_trace_khong_co_chu_khach_trong_agent_steps() -> None:
    payload = _trace("OpenQuestion", AGENT_STEPS).payload
    dumped = str(payload["agent_steps"])
    assert "anh muốn xe nào hợp nhất" not in dumped
    for step in payload["agent_steps"]:
        assert set(step) <= {"tool", "args_keys", "ok", "error", "ms", "extra_calls_dropped"}
        assert all(isinstance(key, str) for key in step["args_keys"])


def test_5_cot_vo_huong_khong_doi() -> None:
    """`scripts/core_v2_metrics.py` lọc theo đúng 5 cột này — không được đổi."""

    trace = _trace("OpenQuestion", AGENT_STEPS)
    assert trace.intent_hint == UNCLEAR_UNDERSTANDING.intent.value
    assert trace.confidence == UNCLEAR_UNDERSTANDING.confidence
    assert trace.tier == "core_v2"
    assert trace.scope_label == "IN_SCOPE"
    assert trace.terminal_reason is None
