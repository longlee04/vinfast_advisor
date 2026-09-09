"""Adapter tool-calling TCO: ép gọi `tinh_chi_phi`, hỏng kiểu gì cũng trả None.

Fake client theo đúng pattern `test_understanding_llm.py`: không mạng, không key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from src.agents.adapters.tco_tool_llm import (
    TCO_TOOL_NAME,
    OpenAITcoArgResolver,
    build_tco_tool,
)
from src.agents.domain.tco_tool import TcoToolArgs

ResultT = TypeVar("ResultT")

GOOD_ARGS = {"daily_km": 60, "province": "Đà Nẵng"}


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]
    usage_metadata: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 120, "output_tokens": 20, "total_tokens": 140}
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


def _resolver(response: _Response | Exception, *, timeout: object | None = None) -> tuple[OpenAITcoArgResolver, _Client]:
    client = _Client(response)
    resolver = OpenAITcoArgResolver(model_name="gpt-test", api_key="test-key", client=client, timeout=timeout or _Timeout())
    return resolver, client


async def _resolve(resolver: OpenAITcoArgResolver) -> TcoToolArgs | None:
    return await resolver.resolve(
        user_message="mỗi ngày tôi chạy tầm sáu chục cây ở Đà Nẵng",
        vehicle_name="VF 6 Plus",
        known_daily_km=None,
        known_province=None,
    )


@pytest.mark.asyncio
async def test_goi_tool_thanh_cong_tra_tham_so() -> None:
    resolver, client = _resolver(_Response(tool_calls=({"name": TCO_TOOL_NAME, "args": GOOD_ARGS},)))
    result = await _resolve(resolver)
    assert result == TcoToolArgs(daily_km=60, province="Đà Nẵng")
    # Ép đúng tool `tinh_chi_phi` — không cho model tự do trả text.
    assert client.tool_choice == TCO_TOOL_NAME
    assert client.tools == [build_tco_tool()]


@pytest.mark.asyncio
async def test_khong_co_tool_call_tra_none() -> None:
    resolver, _ = _resolver(_Response(tool_calls=()))
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_timeout_tra_none() -> None:
    resolver, _ = _resolver(_Response(tool_calls=()), timeout=_TimedOut())
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_payload_hong_tra_none() -> None:
    resolver, _ = _resolver(_Response(tool_calls=({"name": TCO_TOOL_NAME, "args": {"daily_km": "sáu chục"}},)))
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_thieu_api_key_tra_none_khong_goi_mang() -> None:
    resolver = OpenAITcoArgResolver(model_name="gpt-test", api_key="")
    assert await _resolve(resolver) is None
