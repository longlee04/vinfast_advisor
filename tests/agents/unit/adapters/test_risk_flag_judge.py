"""J2 OpenAI risk-flag judge adapter fail-open behavior."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from src.agents.adapters.risk_flag_judge import OpenAIRiskFlagJudge
from src.agents.domain.quote_risk import RiskFlagFallbackReason, RiskFlagPrediction
from src.agents.prompts.risk_flag_judge import RISK_FLAG_JUDGE_TOOL_NAME
from src.agents.services.call_budget import TurnCallBudget, use_call_budget

_FLAGS = ("is_negotiated", "has_non_standard_offer", "has_financial_commitment", "is_personalized")


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


def _judge(response: _Response | Exception) -> tuple[OpenAIRiskFlagJudge, _Client]:
    client = _Client(response)
    judge = OpenAIRiskFlagJudge(model_name="gpt-test", api_key="test-key", client=client)
    return judge, client


@pytest.mark.asyncio
async def test_forces_tool_and_parses_flags() -> None:
    judge, client = _judge(
        _Response(({"args": {"is_negotiated": True, "confidence": 0.95}},)),
    )

    result = await judge.judge(user_message="giá mềm giúp em", draft_answer="em chốt 750 triệu")

    assert client.tool_choice == RISK_FLAG_JUDGE_TOOL_NAME
    assert result == RiskFlagPrediction(
        flags={"is_negotiated": True, **{name: False for name in _FLAGS[1:]}},
        confidence=0.95,
    )


@pytest.mark.asyncio
async def test_defaults_absent_flags_to_false() -> None:
    judge, _ = _judge(_Response(({"args": {"confidence": 0.8}},)))

    result = await judge.judge(user_message="xe này giá bao nhiêu", draft_answer=None)

    assert result.flags == {name: False for name in _FLAGS}


@pytest.mark.asyncio
async def test_empty_tool_calls_fail_open() -> None:
    judge, _ = _judge(_Response(()))

    result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.EMPTY_TOOL_CALL
    assert result.flags == {name: False for name in _FLAGS}


@pytest.mark.asyncio
async def test_invalid_payload_fail_open() -> None:
    judge, _ = _judge(_Response(({"args": {"is_negotiated": "maybe"}},)))

    result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.INVALID_PAYLOAD


@pytest.mark.asyncio
async def test_provider_error_fail_open() -> None:
    from openai import APIError

    judge, _ = _judge(APIError(message="provider boom", request=None, body=None))

    result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.PROVIDER_API_ERROR


@pytest.mark.asyncio
async def test_unexpected_error_fail_open() -> None:
    judge, _ = _judge(OSError("boom"))

    result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.UNEXPECTED_KNOWN_FAILURE


@pytest.mark.asyncio
async def test_missing_key_fail_open() -> None:
    judge = OpenAIRiskFlagJudge(model_name="gpt-test", api_key="")

    result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.MISSING_API_KEY


@pytest.mark.asyncio
async def test_exhausted_budget_fail_open() -> None:
    judge, _ = _judge(_Response(({"args": {"is_negotiated": True, "confidence": 1.0}},)))

    with use_call_budget(TurnCallBudget(optional=0)):
        result = await judge.judge(user_message="x", draft_answer=None)

    assert result.fallback_reason is RiskFlagFallbackReason.OPTIONAL_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_logs_never_leak_message_or_secret(caplog: pytest.LogCaptureFixture) -> None:
    secret = "customer@example.com Bearer top-secret"
    judge, _ = _judge(_Response(({"args": {"confidence": 0.5}},)))
    caplog.set_level(logging.WARNING)

    await judge.judge(user_message=secret, draft_answer=secret)

    assert secret not in caplog.text
