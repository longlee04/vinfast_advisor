"""Vòng ReAct của agent trên OpenAI — có trần, có đồng hồ, KHÔNG bao giờ ném.

Chép hình `adapters/understanding_llm.py` (bind tool, pydantic validate, mọi
lỗi biết trước thành kết quả an toàn), khác ở chỗ LLM được TỰ CHỌN tool thay
vì bị ép gọi một tool cố định — đây là mảnh agentic duy nhất của hệ thống.

Bốn lớp chống lặp vô hạn, độc lập nhau (§2.2 plan agent-migration):

1. `max_steps` cứng, đếm MỌI bước kể cả bước lỗi.
2. `total_timeout_seconds` đo bằng `time.monotonic()` TRƯỚC mỗi bước — route
   `/agent/turn` không có timeout ngoài nên loop phải tự cầm.
3. Ngân sách `CallKind.AGENT` (slot riêng, không đụng REQUIRED/OPTIONAL).
4. Chặn `repeat_call`: cùng tool cùng args gọi lần hai → trả lỗi ngay, KHÔNG
   chạy tool, nhưng vẫn đếm một bước.

Chỉ xử lý `tool_calls[0]`: parallel tool call làm số bước không dự đoán được
và làm vỡ trần ngân sách. Các call còn lại bị bỏ và ghi vào vệt.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, Protocol

from openai import APIError
from pydantic import ValidationError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.agents.adapters.understanding_llm import model_kwargs
from src.agents.domain.agent_tools import (
    AGENT_TOOL_TRA_LOI,
    ERROR_BAD_ARGS,
    AgentToolCall,
    AgentToolResult,
    TraLoiArgs,
)
from src.agents.logging import get_agent_logger
from src.agents.ports import AgentLoopOutcome
from src.agents.services.call_budget import CallKind, current_call_budget
from src.config import get_settings

logger = get_agent_logger("agent.adapters.agent_loop")

#: [GIẢ ĐỊNH] Bốn tham số này phải hiệu chỉnh sau Bước 9 theo ngưỡng A5/A9.
DEFAULT_MAX_STEPS: Final = 3
DEFAULT_STEP_TIMEOUT_SECONDS: Final = 4.0
DEFAULT_TOTAL_TIMEOUT_SECONDS: Final = 10.0

#: Model của loop. [GIẢ ĐỊNH] `gpt-4o` — cùng lựa chọn với ba arg resolver đang
#: chạy (`composition.py`: "4o gọi tool ổn định"). KHÔNG dùng `settings.model_name`
#: (`gpt-4o-mini`): loop nhiều bước cần tool-calling ổn định hơn.
AGENT_LOOP_MODEL: Final = "gpt-4o"

ERROR_NO_TOOL_CALL: Final = "no_tool_call"
ERROR_MAX_STEPS: Final = "max_steps"
ERROR_TOTAL_TIMEOUT: Final = "total_timeout"
ERROR_STEP_TIMEOUT: Final = "step_timeout"
ERROR_BUDGET: Final = "budget_exhausted"
ERROR_NO_API_KEY: Final = "no_api_key"
ERROR_EXTRA_CALLS: Final = "extra_calls_dropped"

#: Trần chữ của một payload tool nhét vào transcript. Kết quả tool là dữ liệu
#: tất định (thẻ chi phí, bảng so sánh) — quá dài thì prompt phình mà thông tin
#: thêm gần như bằng không.
MAX_TOOL_PAYLOAD_CHARS: Final = 2000


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[Any]) -> Any: ...


class AgentLoopClient(Protocol):
    def bind_tools(self, tools: list[dict[str, Any]]) -> _BoundClient: ...


def _args_keys(args: Mapping[str, Any] | None) -> list[str]:
    """CHỈ tên khoá — giá trị args là chữ khách, không được vào log/trace."""

    return sorted(str(key) for key in (args or {}))


def _step(tool: str, *, ok: bool, error: str, elapsed: float, extra: bool = False) -> dict[str, Any]:
    """Một dòng vệt. `args_keys` do nơi gọi điền — mặc định RỖNG, không bao giờ giá trị."""

    return {
        "tool": tool,
        "args_keys": [],
        "ok": ok,
        "error": error,
        "ms": max(0, int(elapsed * 1000)),
        **({"extra_calls_dropped": True} if extra else {}),
    }


class OpenAIAgentLoop:
    """`AgentLoopPort` trên OpenAI. Mọi đường ra đều là `AgentLoopOutcome`."""

    def __init__(
        self,
        model_name: str = AGENT_LOOP_MODEL,
        api_key: str | None = None,
        *,
        client: AgentLoopClient | None = None,
        timeout: TimeoutRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()
        self._clock = clock

    async def run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        execute: Callable[[AgentToolCall], Awaitable[AgentToolResult]],
        max_steps: int = DEFAULT_MAX_STEPS,
        step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
        total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
    ) -> AgentLoopOutcome:
        try:
            return await self._run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=tools,
                execute=execute,
                max_steps=max_steps,
                step_timeout_seconds=step_timeout_seconds,
                total_timeout_seconds=total_timeout_seconds,
            )
        except Exception as error:  # lưới CUỐI: loop là đường phụ, không được giết lượt
            logger.warning("agent.loop loi la %s", type(error).__name__, exc_info=True)
            return AgentLoopOutcome(answer=None, error=type(error).__name__)

    async def _run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        execute: Callable[[AgentToolCall], Awaitable[AgentToolResult]],
        max_steps: int,
        step_timeout_seconds: float,
        total_timeout_seconds: float,
    ) -> AgentLoopOutcome:
        if not self._api_key and self._client is None:
            return AgentLoopOutcome(answer=None, error=ERROR_NO_API_KEY)
        begin = self._clock()
        steps: list[Mapping[str, Any]] = []
        llm_calls = 0
        called: set[tuple[str, str]] = set()
        history: list[Any] = self._messages(system_prompt, user_prompt)
        bound = (self._client or self._build_client()).bind_tools(tools)

        for _ in range(max(0, max_steps)):
            if self._clock() - begin >= total_timeout_seconds:
                return self._done(None, steps, ERROR_TOTAL_TIMEOUT, llm_calls)
            budget = current_call_budget()
            if budget is not None and not budget.take(CallKind.AGENT):
                return self._done(None, steps, ERROR_BUDGET, llm_calls)

            started = self._clock()
            try:
                response = await self._timeout.run(step_timeout_seconds, lambda: bound.ainvoke(history))
            except TimeoutError:
                # Bước quá hạn VẪN đếm một bước: nếu không, một provider chậm
                # sẽ kéo loop chạy tới hết `total_timeout`.
                steps.append(_step("", ok=False, error=ERROR_STEP_TIMEOUT, elapsed=self._clock() - started))
                llm_calls += 1
                continue
            except (APIError, ImportError, KeyError, OSError, TypeError, ValueError) as error:
                steps.append(_step("", ok=False, error=type(error).__name__, elapsed=self._clock() - started))
                return self._done(None, steps, type(error).__name__, llm_calls + 1)
            llm_calls += 1

            tool_calls = list(getattr(response, "tool_calls", None) or [])
            if not tool_calls:
                # Model đáp bằng CHỮ THƯỜNG thay vì gọi `tra_loi_khach` — quan sát
                # trên máy 2026-09-23 ở đúng lớp câu hội thoại (khách hỏi meta,
                # không hỏi số liệu). Chữ đó vẫn phải qua đủ ba cửa `verify` →
                # `quote_gate` → `assert_clean` ở `core/act`, nên nhận nó an
                # toàn y như nhận qua tool, và giữ được lượt thay vì vứt đi.
                spoken = _plain_text(response)
                error = "" if spoken else ERROR_NO_TOOL_CALL
                steps.append(_step("", ok=bool(spoken), error=error or ERROR_NO_TOOL_CALL, elapsed=self._clock() - started))
                return self._done(spoken or None, steps, error, llm_calls)
            extra = len(tool_calls) > 1
            name, raw_args = _read_call(tool_calls[0])

            if name == AGENT_TOOL_TRA_LOI:
                try:
                    payload = TraLoiArgs.model_validate(dict(raw_args))
                except ValidationError:
                    steps.append(_step(name, ok=False, error=ERROR_BAD_ARGS, elapsed=self._clock() - started, extra=extra))
                    history.extend(
                        [response, self._tool_message(AgentToolResult(name, ok=False, error=ERROR_BAD_ARGS), tool_calls[0])]
                    )
                    continue
                steps.append(_step(name, ok=True, error="", elapsed=self._clock() - started, extra=extra))
                return self._done(payload.answer, steps, "", llm_calls)

            key = (name, _args_key(raw_args))
            if key in called:
                result = AgentToolResult(name=name, ok=False, error="repeat_call")
            else:
                called.add(key)
                result = await execute(AgentToolCall(name=name, args=dict(raw_args)))
            step = _step(name, ok=result.ok, error=result.error, elapsed=self._clock() - started, extra=extra)
            step["args_keys"] = _args_keys(raw_args)
            steps.append(step)
            history.extend([response, self._tool_message(result, tool_calls[0])])

        return self._done(None, steps, ERROR_MAX_STEPS, llm_calls)

    @staticmethod
    def _done(
        answer: str | None, steps: list[Mapping[str, Any]], error: str, llm_calls: int
    ) -> AgentLoopOutcome:
        if answer is None:
            logger.info("agent.loop khong ra cau tra loi error=%s buoc=%d calls=%d", error, len(steps), llm_calls)
        return AgentLoopOutcome(answer=answer, steps=tuple(steps), error=error, llm_calls=llm_calls)

    def _build_client(self) -> AgentLoopClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=DEFAULT_STEP_TIMEOUT_SECONDS,
            **model_kwargs(self._model_name),
        )

    @staticmethod
    def _messages(system_prompt: str, user_prompt: str) -> list[Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    @staticmethod
    def _tool_message(result: AgentToolResult, call: Any) -> Any:
        from langchain_core.messages import ToolMessage

        body = json.dumps(
            {"ok": result.ok, "error": result.error, "payload": dict(result.payload)},
            ensure_ascii=False,
            default=str,
        )[:MAX_TOOL_PAYLOAD_CHARS]
        return ToolMessage(content=body, tool_call_id=_call_id(call))


def _plain_text(response: Any) -> str:
    """Chữ model tự viết khi nó không gọi tool. Rỗng nghĩa là không có gì để nhận.

    `content` của LangChain có thể là chuỗi hoặc danh sách block (model đa phương
    thức) — lấy đúng phần chữ, bỏ mọi block khác.
    """

    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(block.get("text", "")) if isinstance(block, Mapping) else str(block)
            for block in content
            if not isinstance(block, Mapping) or block.get("type") in {None, "text"}
        ]
        return " ".join(part for part in parts if part).strip()
    return ""


def _read_call(call: Any) -> tuple[str, Mapping[str, Any]]:
    """Một tool call của LangChain (dict hoặc object) → (tên, args)."""

    if isinstance(call, Mapping):
        return str(call.get("name") or ""), dict(call.get("args") or {})
    return str(getattr(call, "name", "") or ""), dict(getattr(call, "args", None) or {})


def _call_id(call: Any) -> str:
    if isinstance(call, Mapping):
        return str(call.get("id") or "call")
    return str(getattr(call, "id", "") or "call")


def _args_key(args: Mapping[str, Any]) -> str:
    """Khoá so trùng của một lần gọi — ổn định, không phụ thuộc thứ tự khoá."""

    return json.dumps(dict(args), sort_keys=True, ensure_ascii=False, default=str)


__all__ = [
    "AGENT_LOOP_MODEL",
    "DEFAULT_MAX_STEPS",
    "DEFAULT_STEP_TIMEOUT_SECONDS",
    "DEFAULT_TOTAL_TIMEOUT_SECONDS",
    "ERROR_BUDGET",
    "ERROR_MAX_STEPS",
    "ERROR_NO_API_KEY",
    "ERROR_NO_TOOL_CALL",
    "ERROR_STEP_TIMEOUT",
    "ERROR_TOTAL_TIMEOUT",
    "AgentLoopClient",
    "OpenAIAgentLoop",
]
