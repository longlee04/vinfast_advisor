"""Fail-open OpenAI adapter for closed bottleneck classification."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Protocol, TypedDict, TypeVar, assert_never

import anyio
from openai import APIError
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckDetectionResult,
    BottleneckDetectionStatus,
    BottleneckNone,
    BottleneckUnavailable,
)
from src.agents.domain.conversation_memory import redact_sensitive
from src.agents.domain.customer_profile import Bottleneck
from src.agents.logging import get_agent_logger
from src.agents.prompts.bottleneck_detection import (
    BOTTLENECK_DETECTION_PROMPT_VERSION,
    BOTTLENECK_DETECTION_TOOL_NAME,
    SYSTEM_PROMPT,
    BottleneckToolSchema,
    build_bottleneck_detection_tool,
)
from src.config import get_settings

logger = get_agent_logger("agent.adapters.bottleneck_detector")
_DEFAULT_TIMEOUT_SECONDS = 3.0


class ToolCall(TypedDict):
    args: dict[str, str]


class UsageMetadata(TypedDict):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class DetectorResponse(Protocol):
    tool_calls: tuple[ToolCall, ...] | list[ToolCall]
    usage_metadata: UsageMetadata


class BoundDetectorClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> DetectorResponse: ...


class DetectorClient(Protocol):
    def bind_tools(self, tools: list[BottleneckToolSchema], *, tool_choice: object) -> BoundDetectorClient: ...


ResultT = TypeVar("ResultT")


class TimeoutRunner(Protocol):
    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT: ...


@dataclass(frozen=True, slots=True)
class AnyioTimeoutRunner:
    """Run one async provider operation under injected wall-clock budget."""

    async def run(self, seconds: float, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        with anyio.fail_after(seconds):
            return await operation()


@dataclass(frozen=True, slots=True)
class BottleneckMetricEvent:
    """PII-free detector telemetry."""

    status: BottleneckDetectionStatus
    model: str
    prompt_version: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(slots=True)
class BottleneckDetectorMetrics:
    """In-memory metric sink; fake-friendly and contains no content fields."""

    events: list[BottleneckMetricEvent] = field(default_factory=list)

    def record(self, event: BottleneckMetricEvent) -> None:
        self.events.append(event)


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: BottleneckDetectionStatus
    label: Bottleneck | None = None
    confidence: float = 0.0

    @model_validator(mode="after")
    def enforce_closed_shape(self) -> _ProviderPayload:
        match self.status:
            case BottleneckDetectionStatus.DETECTED:
                if self.label is None:
                    raise ValueError("detected bottleneck requires label")
                if not 0.0 <= self.confidence <= 1.0:
                    raise ValueError("bottleneck confidence must be between 0 and 1")
            case BottleneckDetectionStatus.NONE:
                if self.label is not None:
                    raise ValueError("none bottleneck forbids label")
            case BottleneckDetectionStatus.UNAVAILABLE:
                raise ValueError("provider cannot return unavailable")
        return self


class OpenAIBottleneckDetector:
    """Force one closed tool call; map every expected provider failure to unavailable."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: DetectorClient | None = None,
        timeout: TimeoutRunner | None = None,
        metrics: BottleneckDetectorMetrics | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()
        self._metrics = metrics or BottleneckDetectorMetrics()

    async def detect(self, current_server_quote: str) -> BottleneckDetectionResult:
        """Classify redacted current quote without allowing provider-authored evidence."""

        started = monotonic()
        if not self._api_key:
            result = BottleneckUnavailable(BottleneckDetectionStatus.UNAVAILABLE)
            self._record(result.status, started)
            return result

        try:
            client = self._client or self._build_client()
            bound = client.bind_tools(
                [build_bottleneck_detection_tool()],
                tool_choice=BOTTLENECK_DETECTION_TOOL_NAME,
            )
            response = await self._timeout.run(
                _DEFAULT_TIMEOUT_SECONDS,
                lambda: bound.ainvoke(self._messages(redact_sensitive(current_server_quote))),
            )
            result = self._parse(response, redact_sensitive(current_server_quote))
        except (
            APIError,
            ImportError,
            KeyError,
            OSError,
            TimeoutError,
            ValidationError,
            ValueError,
        ) as error:
            logger.warning(
                "bottleneck.detect unavailable status=%s model=%s prompt=%s error_type=%s",
                "UNAVAILABLE",
                self._model_name,
                BOTTLENECK_DETECTION_PROMPT_VERSION,
                type(error).__name__,
            )
            result = BottleneckUnavailable(BottleneckDetectionStatus.UNAVAILABLE)
            response = None
        self._record(result.status, started, response)
        return result

    def _build_client(self) -> DetectorClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            temperature=0.0,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _messages(current_server_quote: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=current_server_quote)]

    def _parse(self, response: DetectorResponse, current_server_quote: str) -> BottleneckDetectionResult:
        if not response.tool_calls:
            raise ValueError("provider omitted forced tool call")
        payload = _ProviderPayload.model_validate(response.tool_calls[0]["args"])
        match payload.status:
            case BottleneckDetectionStatus.DETECTED:
                if payload.label is None:
                    raise ValueError("detected bottleneck requires label")
                return BottleneckDetected(
                    status=payload.status,
                    label=payload.label,
                    evidence_quote=current_server_quote,
                    confidence=payload.confidence,
                    model_name=self._model_name,
                    prompt_version=BOTTLENECK_DETECTION_PROMPT_VERSION,
                )
            case BottleneckDetectionStatus.NONE:
                return BottleneckNone(status=payload.status)
            case BottleneckDetectionStatus.UNAVAILABLE:
                raise ValueError("provider cannot return unavailable")
            case unreachable:
                assert_never(unreachable)

    def _record(
        self,
        status: BottleneckDetectionStatus,
        started: float,
        response: DetectorResponse | None = None,
    ) -> None:
        usage = response.usage_metadata if response is not None else None
        event = BottleneckMetricEvent(
            status=status,
            model=self._model_name,
            prompt_version=BOTTLENECK_DETECTION_PROMPT_VERSION,
            latency_ms=max(0, round((monotonic() - started) * 1_000)),
            input_tokens=usage["input_tokens"] if usage is not None else 0,
            output_tokens=usage["output_tokens"] if usage is not None else 0,
            total_tokens=usage["total_tokens"] if usage is not None else 0,
        )
        self._metrics.record(event)
        logger.info(
            "bottleneck.detect status=%s model=%s prompt=%s latency_ms=%d input_tokens=%d output_tokens=%d total_tokens=%d",
            event.status.value,
            event.model,
            event.prompt_version,
            event.latency_ms,
            event.input_tokens,
            event.output_tokens,
            event.total_tokens,
        )
