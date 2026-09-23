"""`OpenAIAgentLoop`: trần bước, đồng hồ, ngân sách, chống lặp (plan Bước 5).

Client GIẢ hoàn toàn — không gọi OpenAI thật (AGENTS.md: "Tests must not call
real SendGrid, OpenAI, or other paid external services").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from src.agents.adapters.agent_loop_llm import (
    ERROR_BUDGET,
    ERROR_MAX_STEPS,
    ERROR_NO_TOOL_CALL,
    ERROR_STEP_TIMEOUT,
    ERROR_TOTAL_TIMEOUT,
    OpenAIAgentLoop,
)
from src.agents.domain.agent_tools import (
    AGENT_TOOL_DANH_MUC,
    AGENT_TOOL_TINH_CHI_PHI,
    AGENT_TOOL_TRA_LOI,
    ERROR_BAD_ARGS,
    ERROR_EMPTY,
    ERROR_TOOL_FAILED,
    AgentToolCall,
    AgentToolResult,
    build_agent_tools,
)
from src.agents.services.call_budget import TurnCallBudget, use_call_budget

pytestmark = pytest.mark.asyncio

TOOLS = build_agent_tools()


class _Response:
    def __init__(self, tool_calls: list[dict[str, Any]], content: Any = "") -> None:
        self.tool_calls = tool_calls
        self.content = content


def _call(name: str, args: dict[str, Any] | None = None, *, call_id: str = "c1") -> dict[str, Any]:
    return {"name": name, "args": args or {}, "id": call_id}


class _FakeClient:
    """Trả lần lượt các phản hồi đã dựng sẵn; hết thì lặp lại cái cuối."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses
        self.invocations = 0
        self.bound_tools: list[dict[str, Any]] = []
        self.last_history: list[Any] = []

    def bind_tools(self, tools: list[dict[str, Any]]) -> _FakeClient:
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list[Any]) -> Any:
        self.last_history = list(messages)
        index = min(self.invocations, len(self._responses) - 1)
        self.invocations += 1
        item = self._responses[index]
        if isinstance(item, Exception):
            raise item
        return item


class _Timeout:
    """`TimeoutRunner` giả: chạy thẳng, hoặc ném `TimeoutError` ở lượt đã hẹn."""

    def __init__(self, timeout_at: set[int] | None = None) -> None:
        self.calls = 0
        self._timeout_at = timeout_at or set()

    async def run(self, seconds: float, operation: Callable[[], Awaitable[Any]]) -> Any:
        self.calls += 1
        if self.calls in self._timeout_at:
            raise TimeoutError
        return await operation()


class _Clock:
    """Đồng hồ giả: mỗi lần đọc nhảy `step` giây."""

    def __init__(self, step: float = 0.0) -> None:
        self.now = 0.0
        self._step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self._step
        return value


class _Spy:
    """`execute` giả — ghi lại mọi lần bị gọi."""

    def __init__(self, result: AgentToolResult | Exception | None = None) -> None:
        self.calls: list[AgentToolCall] = []
        self._result = result

    async def __call__(self, call: AgentToolCall) -> AgentToolResult:
        self.calls.append(call)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result or AgentToolResult(name=call.name, ok=True, payload={"data": "x"})


def _loop(client: _FakeClient, *, timeout: _Timeout | None = None, clock: _Clock | None = None) -> OpenAIAgentLoop:
    return OpenAIAgentLoop(client=client, timeout=timeout or _Timeout(), clock=clock or _Clock(), api_key="")


async def _run(loop: OpenAIAgentLoop, execute: _Spy, **kw: Any):
    return await loop.run(
        system_prompt="hệ thống",
        user_prompt="khách hỏi gì đó",
        tools=TOOLS,
        execute=execute,
        **{"max_steps": 3, "step_timeout_seconds": 4.0, "total_timeout_seconds": 10.0, **kw},
    )


async def test_goi_tra_loi_khach_thi_dung() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_TRA_LOI, {"answer": "Dạ VF 3 giá 240 triệu ạ."})])])
    spy = _Spy()
    outcome = await _run(_loop(client), spy)
    assert outcome.answer == "Dạ VF 3 giá 240 triệu ạ."
    assert outcome.error == "" and outcome.llm_calls == 1
    assert spy.calls == []  # tool kết thúc KHÔNG đi qua `execute`
    assert client.bound_tools == TOOLS


async def test_het_max_steps_tra_none() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": None})])])
    spy = _Spy()
    outcome = await _run(_loop(client), spy, max_steps=3)
    assert outcome.answer is None and outcome.error == ERROR_MAX_STEPS
    assert outcome.llm_calls == 3 and len(outcome.steps) == 3
    # Bước 2 và 3 là `repeat_call` (cùng tool cùng args) nên tool chỉ chạy 1 lần.
    assert len(spy.calls) == 1


async def test_tool_khong_ton_tai_dem_1_buoc_va_di_tiep() -> None:
    client = _FakeClient(
        [
            _Response([_call("dat_lich_lai_thu", {"vehicle_name": "VF 3"})]),
            _Response([_call(AGENT_TOOL_TRA_LOI, {"answer": "Dạ em trả lời ạ."})]),
        ]
    )
    spy = _Spy(AgentToolResult(name="dat_lich_lai_thu", ok=False, error="unknown_tool"))
    outcome = await _run(_loop(client), spy)
    assert outcome.answer == "Dạ em trả lời ạ."
    assert [step["error"] for step in outcome.steps] == ["unknown_tool", ""]
    assert outcome.llm_calls == 2


async def test_args_sai_schema_tra_bad_args() -> None:
    """`tra_loi_khach` thiếu `answer` → `bad_args`, đếm 1 bước, loop đi tiếp."""

    client = _FakeClient(
        [
            _Response([_call(AGENT_TOOL_TRA_LOI, {"vehicle_ids_used": ["v1"]})]),
            _Response([_call(AGENT_TOOL_TRA_LOI, {"answer": "Dạ em xin lỗi ạ."})]),
        ]
    )
    outcome = await _run(_loop(client), _Spy())
    assert outcome.steps[0]["error"] == ERROR_BAD_ARGS
    assert outcome.answer == "Dạ em xin lỗi ạ."


async def test_tool_nem_loi_khong_lam_vo_loop() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3"})])])
    outcome = await _run(_loop(client), _Spy(RuntimeError("db down")), max_steps=2)
    assert outcome.answer is None
    assert outcome.error == "RuntimeError"  # lưới cuối bắt, không ném lên nơi gọi


async def test_tool_tra_rong_khac_tool_hong() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"})])])
    trong = await _run(_loop(client), _Spy(AgentToolResult(AGENT_TOOL_DANH_MUC, ok=True, error=ERROR_EMPTY)), max_steps=1)
    client2 = _FakeClient([_Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"})])])
    hong = await _run(
        _loop(client2), _Spy(AgentToolResult(AGENT_TOOL_DANH_MUC, ok=False, error=ERROR_TOOL_FAILED)), max_steps=1
    )
    assert trong.steps[0]["ok"] is True and trong.steps[0]["error"] == ERROR_EMPTY
    assert hong.steps[0]["ok"] is False and hong.steps[0]["error"] == ERROR_TOOL_FAILED


async def test_goi_lai_y_het_bi_chan_repeat_call() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3", "daily_km": 30})])])
    spy = _Spy()
    outcome = await _run(_loop(client), spy, max_steps=3)
    assert len(spy.calls) == 1  # tool KHÔNG chạy lần hai
    assert [step["error"] for step in outcome.steps] == ["", "repeat_call", "repeat_call"]


async def test_goi_lai_khac_args_van_chay() -> None:
    client = _FakeClient(
        [
            _Response([_call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3"})]),
            _Response([_call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 5"})]),
        ]
    )
    spy = _Spy()
    await _run(_loop(client), spy, max_steps=2)
    assert [call.args["vehicle_name"] for call in spy.calls] == ["VF 3", "VF 5"]


async def test_total_timeout_cat_giua_chung() -> None:
    """Đồng hồ nhảy 6s mỗi lần đọc: bước hai vượt trần 10s → dừng ngay."""

    client = _FakeClient([_Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"})])])
    outcome = await _run(_loop(client, clock=_Clock(step=6.0)), _Spy(), max_steps=3, total_timeout_seconds=10.0)
    assert outcome.answer is None and outcome.error == ERROR_TOTAL_TIMEOUT
    assert outcome.llm_calls < 3


async def test_step_timeout_tinh_la_1_buoc() -> None:
    client = _FakeClient(
        [
            _Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"})]),
            _Response([_call(AGENT_TOOL_TRA_LOI, {"answer": "Dạ có VF 3 và VF 5 ạ."})]),
        ]
    )
    outcome = await _run(_loop(client, timeout=_Timeout(timeout_at={1})), _Spy(), max_steps=3)
    assert outcome.steps[0]["error"] == ERROR_STEP_TIMEOUT
    assert outcome.answer is not None  # bước sau vẫn chạy
    # Bước quá hạn VẪN tính một call (nếu không, provider chậm sẽ kéo hết trần).
    assert outcome.llm_calls == 3 and len(outcome.steps) == 3


async def test_khong_co_tool_call_va_khong_co_chu_thi_tra_none() -> None:
    client = _FakeClient([_Response([])])
    outcome = await _run(_loop(client), _Spy())
    assert outcome.answer is None and outcome.error == ERROR_NO_TOOL_CALL


async def test_model_dap_bang_chu_thuong_thi_van_nhan() -> None:
    """Quan sát 2026-09-23: ở lớp câu hội thoại, model đáp thẳng bằng chữ.

    Chữ đó vẫn qua đủ ba cửa ở `core/act`, nên nhận nó an toàn y như nhận qua
    tool — và giữ được lượt thay vì vứt đi.
    """

    client = _FakeClient([_Response([], content="Dạ anh/chị vừa hỏi về mẫu xe đang hiển thị ạ.")])
    outcome = await _run(_loop(client), _Spy())
    assert outcome.answer == "Dạ anh/chị vừa hỏi về mẫu xe đang hiển thị ạ."
    assert outcome.error == ""


async def test_chu_thuong_dang_block_cung_doc_duoc() -> None:
    client = _FakeClient([_Response([], content=[{"type": "text", "text": "Dạ em nghe ạ."}])])
    outcome = await _run(_loop(client), _Spy())
    assert outcome.answer == "Dạ em nghe ạ."


async def test_parallel_tool_calls_chi_lay_cai_dau() -> None:
    client = _FakeClient(
        [
            _Response(
                [
                    _call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3"}, call_id="a"),
                    _call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"}, call_id="b"),
                ]
            ),
            _Response([_call(AGENT_TOOL_TRA_LOI, {"answer": "Dạ ạ."})]),
        ]
    )
    spy = _Spy()
    outcome = await _run(_loop(client), spy)
    assert [call.name for call in spy.calls] == [AGENT_TOOL_TINH_CHI_PHI]
    assert outcome.steps[0]["extra_calls_dropped"] is True


async def test_budget_can_thi_dung() -> None:
    client = _FakeClient([_Response([_call(AGENT_TOOL_DANH_MUC, {"vehicle_type": "CAR"})])])
    with use_call_budget(TurnCallBudget(agent=1)):
        outcome = await _run(_loop(client), _Spy(), max_steps=3)
    assert outcome.error == ERROR_BUDGET
    assert outcome.llm_calls == 1  # đúng một call trước khi cạn


async def test_khong_bao_gio_raise() -> None:
    class _Boom:
        def bind_tools(self, tools: list[dict[str, Any]]) -> Any:
            raise RuntimeError("client hong")

    outcome = await _run(OpenAIAgentLoop(client=_Boom(), api_key=""), _Spy())  # type: ignore[arg-type]
    assert outcome.answer is None and outcome.error == "RuntimeError"

    client = _FakeClient([ValueError("provider 500")])
    outcome = await _run(_loop(client), _Spy())
    assert outcome.answer is None and outcome.error == "ValueError"


async def test_steps_khong_chua_gia_tri_args() -> None:
    client = _FakeClient(
        [_Response([_call(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3", "province": "Hà Nội"})])]
    )
    outcome = await _run(_loop(client), _Spy(), max_steps=1)
    step = outcome.steps[0]
    assert step["args_keys"] == ["province", "vehicle_name"]
    assert "VF 3" not in str(step) and "Hà Nội" not in str(step)
