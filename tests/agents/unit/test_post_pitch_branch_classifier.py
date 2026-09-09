"""LLM post-pitch classifier fail-open và tuân quota OPTIONAL."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest
from openai import APIError

from src.agents.adapters.post_pitch_branch_classifier import OpenAIPostPitchBranchClassifier
from src.agents.domain.post_pitch import PostPitchStage
from src.agents.domain.post_pitch_branch import PostPitchBranch, PostPitchFallbackReason
from src.agents.services.call_budget import TurnCallBudget, use_call_budget


@dataclass
class _Response:
    tool_calls: list[dict]


@dataclass
class _Bound:
    response: _Response | BaseException

    async def ainvoke(self, _messages: list[object]) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@dataclass
class _Client:
    response: _Response | BaseException

    def bind_tools(self, _tools: list[dict], *, tool_choice: object) -> _Bound:
        assert tool_choice == "classify_post_pitch_branch"
        return _Bound(self.response)


@pytest.mark.asyncio
async def test_classifier_returns_validated_branch_and_confidence() -> None:
    classifier = OpenAIPostPitchBranchClassifier(
        api_key="test",
        client=_Client(_Response([{"args": {"branch": "WANTS_COST", "confidence": 0.8}}])),
    )

    result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.branch is PostPitchBranch.WANTS_COST
    assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_classifier_returns_unclear_on_invalid_provider_payload() -> None:
    classifier = OpenAIPostPitchBranchClassifier(
        api_key="test",
        client=_Client(_Response([{"args": {"branch": "WANTS_COST", "confidence": 2.0}}])),
    )

    result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.branch is PostPitchBranch.UNCLEAR
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classifier_returns_unclear_without_call_when_optional_budget_exhausted() -> None:
    classifier = OpenAIPostPitchBranchClassifier(
        api_key="test",
        client=_Client(_Response([{"args": {"branch": "WANTS_COST", "confidence": 1.0}}])),
    )
    budget = TurnCallBudget(optional=0)

    with use_call_budget(budget):
        result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.branch is PostPitchBranch.UNCLEAR
    assert result.confidence == 0.0
    assert budget.provider_calls == 0
    assert result.fallback_reason is PostPitchFallbackReason.OPTIONAL_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_classifier_records_missing_key_reason() -> None:
    classifier = OpenAIPostPitchBranchClassifier(api_key="", client=_Client(_Response([])))

    result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.fallback_reason is PostPitchFallbackReason.MISSING_API_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (_Response([]), PostPitchFallbackReason.EMPTY_TOOL_CALL),
        (_Response([{"args": {"branch": "WANTS_COST", "confidence": 2.0}}]), PostPitchFallbackReason.INVALID_PAYLOAD),
    ],
)
async def test_classifier_records_payload_fallback_reason(response: _Response, reason: PostPitchFallbackReason) -> None:
    classifier = OpenAIPostPitchBranchClassifier(api_key="test", client=_Client(response))

    result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.fallback_reason is reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError(), PostPitchFallbackReason.TIMEOUT),
        (APIError.__new__(APIError), PostPitchFallbackReason.PROVIDER_API_ERROR),
        (OSError(), PostPitchFallbackReason.UNEXPECTED_KNOWN_FAILURE),
    ],
)
async def test_classifier_records_exception_fallback_reason(
    error: BaseException, reason: PostPitchFallbackReason, caplog: pytest.LogCaptureFixture
) -> None:
    classifier = OpenAIPostPitchBranchClassifier(api_key="test", client=_Client(error))

    with caplog.at_level(logging.WARNING):
        result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "secret prompt content")

    record = caplog.records[-1]
    assert result.branch is PostPitchBranch.UNCLEAR
    assert result.confidence == 0.0
    assert result.fallback_reason is reason
    assert record.message == "post_pitch_classifier.fallback"
    assert record.post_pitch_fallback_reason == reason.value
    assert "secret prompt content" not in caplog.text


@pytest.mark.asyncio
async def test_classifier_success_has_no_fallback_reason() -> None:
    classifier = OpenAIPostPitchBranchClassifier(
        api_key="test",
        client=_Client(_Response([{"args": {"branch": "WANTS_COST", "confidence": 0.8}}])),
    )

    result = await classifier.classify(PostPitchStage.AWAITING_DECISION, "tính đi em")

    assert result.fallback_reason is None
