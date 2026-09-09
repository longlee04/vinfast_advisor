"""Adapter tool `tra_thong_so`: ép gọi tool, hỏng trả None, enum sinh từ SPEC_GROUPS."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from src.agents.adapters.spec_tool_llm import OpenAISpecArgResolver, build_spec_tool
from src.agents.domain.spec_tool import SPEC_GROUPS, SPEC_TOOL_NAME, SpecToolArgs

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]
    usage_metadata: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 80, "output_tokens": 10, "total_tokens": 90}
    )


class _Bound:
    def __init__(self, response: _Response | Exception) -> None:
        self._response = response

    async def ainvoke(self, messages: list[object]) -> _Response:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _Client:
    def __init__(self, response: _Response | Exception) -> None:
        self.tools: list[dict[str, object]] = []
        self.tool_choice: object | None = None
        self.bound = _Bound(response)

    def bind_tools(self, tools: list[dict[str, object]], *, tool_choice: object) -> _Bound:
        self.tools = tools
        self.tool_choice = tool_choice
        return self.bound


class _Timeout:
    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        return await operation()


class _TimedOut:
    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        operation().close()
        raise TimeoutError


def _resolver(response: _Response | Exception, *, timeout: object | None = None) -> tuple[OpenAISpecArgResolver, _Client]:
    client = _Client(response)
    return OpenAISpecArgResolver(model_name="gpt-test", api_key="k", client=client, timeout=timeout or _Timeout()), client


async def _resolve(resolver: OpenAISpecArgResolver) -> SpecToolArgs | None:
    return await resolver.resolve(question="cốp nó nuốt nổi hai vali không", vehicle_name="VF 6 Plus")


@pytest.mark.asyncio
async def test_goi_tool_thanh_cong() -> None:
    resolver, client = _resolver(_Response(tool_calls=({"name": SPEC_TOOL_NAME, "args": {"group": "cop"}},)))
    assert await _resolve(resolver) == SpecToolArgs(group="cop")
    assert client.tool_choice == SPEC_TOOL_NAME
    assert client.tools == [build_spec_tool()]


def test_schema_enum_sinh_tu_spec_groups() -> None:
    enum = build_spec_tool()["function"]["parameters"]["properties"]["group"]["enum"]
    assert set(k for k in enum if k is not None) == set(SPEC_GROUPS)


@pytest.mark.asyncio
async def test_khong_tool_call_tra_none() -> None:
    resolver, _ = _resolver(_Response(tool_calls=()))
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_timeout_tra_none() -> None:
    resolver, _ = _resolver(_Response(tool_calls=()), timeout=_TimedOut())
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_thieu_api_key_tra_none() -> None:
    assert await _resolve(OpenAISpecArgResolver(model_name="gpt-test", api_key="")) is None
