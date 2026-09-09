"""Adapter một-cửa-LLM lõi v2: forced tool call, hỏng thì trả outcome rỗng.

Theo đúng pattern fake client của `test_bottleneck_llm.py`: không mạng, không key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from src.agents.adapters.understanding_llm import (
    UNDERSTAND_TIMEOUT_SECONDS,
    OpenAIUnderstander,
    build_understanding_tool,
    model_kwargs,
)
from src.agents.core.state import DialogueAct, Intent
from src.agents.core.understand import UNDERSTAND_TOOL_NAME

ResultT = TypeVar("ResultT")

GOOD_ARGS = {
    "dialogue_act": "SLOT_ANSWER",
    "intent": "ADVISORY",
    "slots": {"vehicle_type": "CAR", "budget_text": "tầm 700 triệu", "features": ["ADAS"], "vehicle_names": ["VF 5 Plus"]},
    "choice_ref": "1",
    "confidence": 0.87,
    "features_all": False,
    "question": "",
}


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]
    usage_metadata: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 300, "output_tokens": 40, "total_tokens": 340}
    )


class _Bound:
    def __init__(self, response: _Response | Exception) -> None:
        self._response = response
        self.messages: list[object] = []

    async def ainvoke(self, messages: list[object]) -> _Response:
        self.messages = messages
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _Client:
    def __init__(self, response: _Response | Exception) -> None:
        self.response = response
        self.tools: list[dict[str, object]] = []
        self.tool_choice: object | None = None
        self.bound = _Bound(response)

    def bind_tools(self, tools: list[dict[str, object]], *, tool_choice: object) -> _Bound:
        self.tools = tools
        self.tool_choice = tool_choice
        return self.bound


class _Timeout:
    def __init__(self) -> None:
        self.seconds: float | None = None

    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        self.seconds = seconds
        return await operation()


class _TimedOut:
    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        operation().close()
        raise TimeoutError


def _adapter(response: _Response | Exception, *, timeout: object | None = None) -> tuple[OpenAIUnderstander, _Client]:
    client = _Client(response)
    adapter = OpenAIUnderstander(model_name="gpt-test", api_key="test-key", client=client, timeout=timeout or _Timeout())
    return adapter, client


@pytest.mark.asyncio
async def test_tool_call_dung_thi_ra_raw_understanding() -> None:
    adapter, client = _adapter(_Response(({"args": GOOD_ARGS},)))

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.error is None
    assert outcome.raw is not None
    assert outcome.raw.dialogue_act == "SLOT_ANSWER"
    assert outcome.raw.intent == "ADVISORY"
    assert outcome.raw.slots.budget_text == "tầm 700 triệu"
    assert outcome.raw.slots.features == ("ADAS",)
    assert outcome.raw.slots.vehicle_names == ("VF 5 Plus",)
    assert outcome.raw.choice_ref == "1"
    assert outcome.raw.confidence == 0.87
    assert client.tool_choice == UNDERSTAND_TOOL_NAME


@pytest.mark.asyncio
async def test_thieu_truong_khong_bat_buoc_van_doc_duoc() -> None:
    adapter, _ = _adapter(_Response(({"args": {"dialogue_act": "SOCIAL"}},)))

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is not None
    assert outcome.raw.intent == "NONE"
    assert outcome.raw.slots.vehicle_names == ()
    assert outcome.raw.confidence == 0.0


@pytest.mark.asyncio
async def test_khong_goi_tool_thi_bao_loi() -> None:
    adapter, _ = _adapter(_Response(()))

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is None
    assert outcome.error == "no_tool_call"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {"slots": {"vehicle_type": "CAR"}},  # thiếu dialogue_act
        {"dialogue_act": "SLOT_ANSWER", "slots": "khong phai object"},
        {"dialogue_act": "SLOT_ANSWER", "confidence": "rất chắc"},
        {"dialogue_act": "SLOT_ANSWER", "slots": {"seats": "năm"}},
    ],
)
async def test_rac_thi_bao_invalid_payload(args: dict[str, object]) -> None:
    adapter, _ = _adapter(_Response(({"args": args},)))

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is None
    assert outcome.error == "invalid_payload"


@pytest.mark.asyncio
async def test_timeout_thi_bao_timeout_khong_raise() -> None:
    adapter, _ = _adapter(_Response(({"args": GOOD_ARGS},)), timeout=_TimedOut())

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is None
    assert outcome.error == "TimeoutError"


@pytest.mark.asyncio
async def test_provider_no_thi_bao_ten_loi() -> None:
    adapter, _ = _adapter(OSError("connection reset"))

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is None
    assert outcome.error == "OSError"


@pytest.mark.asyncio
async def test_khong_co_api_key_thi_khong_goi_mang() -> None:
    client = _Client(_Response(({"args": GOOD_ARGS},)))
    adapter = OpenAIUnderstander(model_name="gpt-test", api_key="", client=client, timeout=_Timeout())

    outcome = await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert outcome.raw is None
    assert outcome.error == "no_api_key"
    assert client.tool_choice is None


@pytest.mark.asyncio
async def test_ngan_sach_thoi_gian_dung_hang_so() -> None:
    timeout = _Timeout()
    adapter, _ = _adapter(_Response(({"args": GOOD_ARGS},)), timeout=timeout)

    await adapter.understand(system_prompt="SYS", user_prompt="USER")

    assert timeout.seconds == UNDERSTAND_TIMEOUT_SECONDS


def test_tool_schema_liet_ke_du_enum() -> None:
    schema = build_understanding_tool()
    params = schema["function"]["parameters"]

    assert schema["function"]["name"] == UNDERSTAND_TOOL_NAME
    assert params["properties"]["dialogue_act"]["enum"] == [item.value for item in DialogueAct]
    assert params["properties"]["intent"]["enum"] == [item.value for item in Intent]
    assert params["required"] == ["dialogue_act", "intent", "confidence"]
    slots = params["properties"]["slots"]["properties"]
    assert set(slots) == {"vehicle_type", "budget_text", "purpose", "seats", "daily_km", "features", "region", "vehicle_names"}
    assert "features_all" in params["properties"] and "question" in params["properties"]


@pytest.mark.parametrize(
    ("model", "expect"),
    [
        ("gpt-4o-mini", {"temperature": 0.0}),
        ("gpt-4o", {"temperature": 0.0}),
        ("gpt-5.6", {"reasoning_effort": "none"}),
        ("gpt-5-mini", {"reasoning_effort": "none"}),
    ],
)
def test_gpt5_phai_tat_reasoning_moi_goi_duoc_tool(model: str, expect: dict[str, object]) -> None:
    assert model_kwargs(model) == expect
