"""J3 OpenAI vague-answer judge adapter fail-open behavior."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from src.agents.adapters.vague_answer_judge import OpenAIVagueAnswerJudge
from src.agents.domain.slot_salvage import VagueFallbackReason, VagueJudgePrediction
from src.agents.prompts.vague_answer_judge import VAGUE_JUDGE_TOOL_NAME
from src.agents.services.call_budget import TurnCallBudget, use_call_budget


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]


class _Bound:
    def __init__(self, response: _Response | Exception) -> None:
        self._response = response

    async def ainvoke(self, messages: list[object]) -> _Response:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _Client:
    def __init__(self, response: _Response | Exception) -> None:
        self.response = response
        self.tool_choice: object | None = None
        self.tools: list[dict[str, object]] = []

    def bind_tools(self, tools: list[dict[str, object]], *, tool_choice: object) -> _Bound:
        self.tools = tools
        self.tool_choice = tool_choice
        return _Bound(self.response)


def _judge(response: _Response | Exception) -> tuple[OpenAIVagueAnswerJudge, _Client]:
    client = _Client(response)
    judge = OpenAIVagueAnswerJudge(model_name="gpt-test", api_key="test-key", client=client)
    return judge, client


@pytest.mark.asyncio
async def test_forces_tool_and_parses_vague() -> None:
    judge, client = _judge(_Response(({"args": {"is_vague": True, "confidence": 0.93}},)))

    result = await judge.judge(user_message="tính thêm đã", last_question="ngân sách tối đa?")

    assert client.tool_choice == VAGUE_JUDGE_TOOL_NAME
    assert result == VagueJudgePrediction(is_vague=True, confidence=0.93)


@pytest.mark.asyncio
async def test_clean_answer_parses_false() -> None:
    judge, _ = _judge(_Response(({"args": {"is_vague": False, "confidence": 0.9}},)))

    result = await judge.judge(user_message="khoảng 500 triệu", last_question="ngân sách?")

    assert result == VagueJudgePrediction(is_vague=False, confidence=0.9)


@pytest.mark.asyncio
async def test_empty_tool_calls_fail_open() -> None:
    judge, _ = _judge(_Response(()))

    result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.EMPTY_TOOL_CALL


@pytest.mark.asyncio
async def test_invalid_payload_fail_open() -> None:
    judge, _ = _judge(_Response(({"args": {"is_vague": "maybe"}},)))

    result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.INVALID_PAYLOAD


@pytest.mark.asyncio
async def test_provider_error_fail_open() -> None:
    from openai import APIError

    judge, _ = _judge(APIError(message="provider boom", request=None, body=None))

    result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.PROVIDER_API_ERROR


@pytest.mark.asyncio
async def test_unexpected_error_fail_open() -> None:
    judge, _ = _judge(OSError("boom"))

    result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.UNEXPECTED_KNOWN_FAILURE


@pytest.mark.asyncio
async def test_missing_key_fail_open() -> None:
    judge = OpenAIVagueAnswerJudge(model_name="gpt-test", api_key="")

    result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.MISSING_API_KEY


@pytest.mark.asyncio
async def test_exhausted_budget_fail_open() -> None:
    judge, _ = _judge(_Response(({"args": {"is_vague": True, "confidence": 1.0}},)))

    with use_call_budget(TurnCallBudget(optional=0)):
        result = await judge.judge(user_message="x", last_question="y")

    assert result.fallback_reason is VagueFallbackReason.OPTIONAL_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_logs_never_leak_message(caplog: pytest.LogCaptureFixture) -> None:
    secret = "customer@example.com Bearer top-secret"
    judge, _ = _judge(_Response(({"args": {"is_vague": True, "confidence": 0.5}},)))
    caplog.set_level(logging.WARNING)

    await judge.judge(user_message=secret, last_question=secret)

    assert secret not in caplog.text
