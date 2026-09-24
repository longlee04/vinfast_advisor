"""OpenAI cho hai việc NỀN của Customer 360: trích insight và phân loại cơ hội (plan §5.3–5.4).

Fail-open: thiếu key, hết giờ, provider lỗi, payload sai hình → trả `None`/verdict rỗng,
service tự xử (gắn tạm chờ TVV, bỏ lượt trích). Câu khách đi qua `redact_pii` trước khi
rời máy chủ — LLM không cần SĐT thật để biết khách định mua khi nào.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.opportunity_attach import LlmVerdict
from src.agents.domain.pii import redact_pii
from src.agents.logging import get_agent_logger
from src.agents.prompts.customer_360 import (
    CLASSIFY_SYSTEM_PROMPT,
    CLASSIFY_TOOL,
    INSIGHT_PROMPT_VERSION,
    INSIGHT_SYSTEM_PROMPT,
    INSIGHT_TOOL,
    classify_input,
    insight_input,
)
from src.agents.services.operations.customer_360 import ClassifierResult, ExtractionResult
from src.config import get_settings

logger = get_agent_logger("agent.adapters.customer_360_llm")
_TIMEOUT_SECONDS: Final[float] = 20.0


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class _Client(Protocol):
    def bind_tools(self, tools: list[dict[str, Any]], *, tool_choice: object) -> _BoundClient: ...


class _ClassifyPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    verdict: LlmVerdict
    opportunity_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class _OpenAIToolCaller:
    def __init__(self, model_name: str | None, api_key: str | None, client: _Client | None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model_name

    def _build_client(self) -> _Client:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(model=self._model_name, api_key=SecretStr(self._api_key or ""), temperature=0.0)

    async def call(self, tool: dict[str, Any], system_prompt: str, content: str) -> dict[str, Any] | None:
        if not self._api_key and self._client is None:
            return None
        from langchain_core.messages import HumanMessage, SystemMessage

        client = self._client or self._build_client()
        bound = client.bind_tools(
            [{"type": "function", "function": tool}],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
        )
        with anyio.fail_after(_TIMEOUT_SECONDS):
            response = await bound.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=content)])
        tool_calls = getattr(response, "tool_calls", None) or []
        return dict(tool_calls[0].get("args") or {}) if tool_calls else None


class OpenAIInsightExtractor:
    """Trích insight; `None` khi không gọi được — service coi như lượt này không có gì mới."""

    def __init__(
        self, model_name: str | None = None, api_key: str | None = None, *, client: _Client | None = None
    ) -> None:
        self._caller = _OpenAIToolCaller(model_name, api_key, client)

    async def extract(self, user_turns: Mapping[int, str]) -> ExtractionResult | None:
        redacted = {index: redact_pii(text) for index, text in user_turns.items()}
        try:
            args = await self._caller.call(INSIGHT_TOOL, INSIGHT_SYSTEM_PROMPT, insight_input(redacted))
        except Exception as error:  # noqa: BLE001 — việc nền, hỏng thì bỏ lượt
            logger.warning("customer360.extract that bai error_type=%s", type(error).__name__)
            return None
        if args is None:
            return None
        items = args.get("insights")
        if not isinstance(items, list):
            return None
        return ExtractionResult(
            items=[item for item in items if isinstance(item, dict)],
            model_name=self._caller.model_name,
            prompt_version=INSIGHT_PROMPT_VERSION,
        )


class OpenAIOpportunityClassifier:
    """Phân loại same/update/new cho ca R7; lỗi → verdict rỗng (gắn tạm, chờ TVV)."""

    def __init__(
        self, model_name: str | None = None, api_key: str | None = None, *, client: _Client | None = None
    ) -> None:
        self._caller = _OpenAIToolCaller(model_name, api_key, client)

    async def classify(self, session_summary: str, candidates: Sequence[Mapping[str, object]]) -> ClassifierResult:
        try:
            args = await self._caller.call(
                CLASSIFY_TOOL, CLASSIFY_SYSTEM_PROMPT, classify_input(redact_pii(session_summary), candidates)
            )
            if args is None:
                return ClassifierResult(None, 0.0)
            payload = _ClassifyPayload.model_validate(args)
        except (ValidationError, ValueError, TimeoutError) as error:
            logger.warning("customer360.classify payload loi error_type=%s", type(error).__name__)
            return ClassifierResult(None, 0.0)
        except Exception as error:  # noqa: BLE001 — việc nền, hỏng thì chờ TVV
            logger.warning("customer360.classify that bai error_type=%s", type(error).__name__)
            return ClassifierResult(None, 0.0)
        return ClassifierResult(payload.verdict, payload.confidence, payload.opportunity_id)


__all__ = ["OpenAIInsightExtractor", "OpenAIOpportunityClassifier"]
