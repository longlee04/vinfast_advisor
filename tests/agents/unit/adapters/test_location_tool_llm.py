"""Adapter tool-calling địa điểm: ép gọi `tim_diem_dich_vu`, hỏng trả None."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from src.agents.adapters.location_tool_llm import (
    OpenAILocationArgResolver,
    build_location_tool,
)
from src.agents.domain.location_tool import LOCATION_TOOL_NAME, LocationToolArgs
from src.agents.domain.nearby_location import LocationKind

ResultT = TypeVar("ResultT")

GOOD_ARGS = {"kinds": ["CHARGING_STATION_CAR"], "area": "Thủ Đức"}


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]
    usage_metadata: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 120, "output_tokens": 20, "total_tokens": 140}
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


def _resolver(response: _Response | Exception, *, timeout: object | None = None) -> tuple[OpenAILocationArgResolver, _Client]:
    client = _Client(response)
    resolver = OpenAILocationArgResolver(
        model_name="gpt-test", api_key="test-key", client=client, timeout=timeout or _Timeout()
    )
    return resolver, client


async def _resolve(resolver: OpenAILocationArgResolver) -> LocationToolArgs | None:
    return await resolver.resolve(
        user_message="chỗ nào cắm điện được gần Thủ Đức không",
        known_kinds=(),
        known_area=None,
    )


@pytest.mark.asyncio
async def test_goi_tool_thanh_cong_tra_tham_so() -> None:
    resolver, client = _resolver(_Response(tool_calls=({"name": LOCATION_TOOL_NAME, "args": GOOD_ARGS},)))
    result = await _resolve(resolver)
    assert result == LocationToolArgs(kinds=("CHARGING_STATION_CAR",), area="Thủ Đức")
    assert client.tool_choice == LOCATION_TOOL_NAME
    assert client.tools == [build_location_tool()]


def test_schema_enum_sinh_tu_location_kind() -> None:
    schema = build_location_tool()
    enum = schema["function"]["parameters"]["properties"]["kinds"]["items"]["enum"]
    assert set(enum) == {kind.value for kind in LocationKind}


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
    resolver, _ = _resolver(_Response(tool_calls=({"name": LOCATION_TOOL_NAME, "args": {"kinds": "tram sac"}},)))
    assert await _resolve(resolver) is None


@pytest.mark.asyncio
async def test_thieu_api_key_tra_none_khong_goi_mang() -> None:
    resolver = OpenAILocationArgResolver(model_name="gpt-test", api_key="")
    assert await _resolve(resolver) is None
