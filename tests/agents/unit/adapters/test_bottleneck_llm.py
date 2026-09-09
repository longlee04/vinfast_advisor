"""Todo 5 OpenAI bottleneck adapter fail-open behavior."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest

from src.agents.adapters.bottleneck_detector import (
    BottleneckDetectorMetrics,
    OpenAIBottleneckDetector,
)
from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionStatus,
    BottleneckNone,
    BottleneckUnavailable,
)
from src.agents.domain.customer_profile import Bottleneck
from src.agents.prompts.bottleneck_detection import (
    BOTTLENECK_DETECTION_PROMPT_VERSION,
    BOTTLENECK_DETECTION_TOOL_NAME,
)

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class _Response:
    tool_calls: tuple[dict[str, object], ...]
    usage_metadata: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 11,
            "output_tokens": 4,
            "total_tokens": 15,
        }
    )


class _Bound:
    def __init__(self, response: _Response | OSError) -> None:
        self._response = response

    async def ainvoke(self, messages: list[object]) -> _Response:
        match self._response:
            case OSError() as error:
                raise error
            case _Response() as response:
                return response
            case unreachable:
                raise AssertionError(unreachable)


class _Client:
    def __init__(self, response: _Response | OSError) -> None:
        self.response = response
        self.tool_choice: object | None = None
        self.tools: list[dict[str, object]] = []

    def bind_tools(self, tools: list[dict[str, object]], *, tool_choice: object) -> _Bound:
        self.tools = tools
        self.tool_choice = tool_choice
        return _Bound(self.response)


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


def _detector(
    response: _Response | OSError,
    *,
    timeout: _Timeout | _TimedOut | None = None,
    metrics: BottleneckDetectorMetrics | None = None,
) -> tuple[OpenAIBottleneckDetector, _Client]:
    client = _Client(response)
    detector = OpenAIBottleneckDetector(
        model_name="gpt-test",
        api_key="test-key",
        client=client,
        timeout=timeout,
        metrics=metrics,
    )
    return detector, client


@pytest.mark.asyncio
async def test_detected_preserves_current_redacted_server_quote() -> None:
    # Given
    detector, _ = _detector(_Response(({"args": {"status": "DETECTED", "label": "PRICE", "confidence": 0.82}},)))

    # When
    result = await detector.detect("Giá cao, key=[REDACTED]")

    # Then
    assert result == BottleneckDetected(
        status=BottleneckDetectionStatus.DETECTED,
        label=Bottleneck.PRICE,
        evidence_quote="Giá cao, key=[REDACTED]",
        model_name="gpt-test",
        prompt_version=BOTTLENECK_DETECTION_PROMPT_VERSION,
        confidence=0.82,
    )


@pytest.mark.asyncio
async def test_missing_confidence_uses_backward_compatible_default() -> None:
    # Given
    detector, _ = _detector(_Response(({"args": {"status": "DETECTED", "label": "PRICE"}},)))

    # When
    result = await detector.detect("Giá cao")

    # Then
    assert isinstance(result, BottleneckDetected)
    assert result.confidence == 0.0
    assert result.offer_suggestion_withheld is True


@pytest.mark.asyncio
async def test_none_result_is_typed() -> None:
    # Given
    detector, _ = _detector(_Response(({"args": {"status": "NONE"}},)))

    # When
    result = await detector.detect("Tôi thích xe này")

    # Then
    assert result == BottleneckNone(status=BottleneckDetectionStatus.NONE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _Response(()),
        _Response(({"args": {"status": "DETECTED", "label": "OTHER"}},)),
        _Response(({"args": {"status": "DETECTED"}},)),
        OSError("Bearer private-provider-payload"),
    ],
)
async def test_provider_and_payload_failures_return_unavailable(
    response: _Response | OSError,
) -> None:
    # Given
    detector, _ = _detector(response)

    # When
    result = await detector.detect("customer@example.com cannot charge")

    # Then
    assert result == BottleneckUnavailable(status=BottleneckDetectionStatus.UNAVAILABLE)


@pytest.mark.asyncio
async def test_missing_key_and_timeout_return_unavailable() -> None:
    # Given
    missing = OpenAIBottleneckDetector(model_name="gpt-test", api_key="")
    timed, _ = _detector(_Response(()), timeout=_TimedOut())

    # When
    missing_result = await missing.detect("private quote")
    timeout_result = await timed.detect("private quote")

    # Then
    assert missing_result.status is BottleneckDetectionStatus.UNAVAILABLE
    assert timeout_result.status is BottleneckDetectionStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_forces_tool_and_uses_injected_three_second_timeout() -> None:
    # Given
    timeout = _Timeout()
    detector, client = _detector(_Response(({"args": {"status": "NONE"}},)), timeout=timeout)

    # When
    await detector.detect("neutral")

    # Then
    assert timeout.seconds == 3.0
    assert client.tool_choice == BOTTLENECK_DETECTION_TOOL_NAME


@pytest.mark.asyncio
async def test_metrics_and_logs_exclude_message_quote_and_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given
    secret = "customer@example.com Bearer top-secret"
    metrics = BottleneckDetectorMetrics()
    detector, _ = _detector(
        _Response(({"args": {"status": "DETECTED", "label": "RANGE", "confidence": 0.55}},)),
        metrics=metrics,
    )
    caplog.set_level(logging.INFO)

    # When
    await detector.detect(secret)

    # Then
    event = metrics.events[0]
    assert event.status is BottleneckDetectionStatus.DETECTED
    assert event.model == "gpt-test"
    assert event.prompt_version
    assert event.latency_ms >= 0
    assert event.input_tokens == 11
    assert event.output_tokens == 4
    assert event.total_tokens == 15
    assert secret not in caplog.text
    assert "top-secret" not in repr(event)
