"""Fail-open OpenAI adapter cho judge risk flag (lớp hai sau regex quote_risk)."""

from __future__ import annotations

import logging
from typing import Final, Protocol, TypedDict

import anyio
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.quote_risk import RiskFlagFallbackReason, RiskFlagPrediction
from src.agents.prompts.risk_flag_judge import (
    RISK_FLAG_JUDGE_TOOL_NAME,
    SYSTEM_PROMPT,
    RiskFlagJudgeToolSchema,
    build_risk_flag_judge_tool,
)
from src.agents.services.call_budget import CallKind, current_call_budget
from src.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: Final[float] = 3.0
_FALLBACK_LOG_MESSAGE: Final[str] = "risk_flag_judge.fallback"

_FLAG_NAMES: Final[tuple[str, ...]] = (
    "is_negotiated",
    "has_non_standard_offer",
    "has_financial_commitment",
    "is_personalized",
)


class ToolCall(TypedDict):
    args: dict[str, object]


class JudgeResponse(Protocol):
    tool_calls: tuple[ToolCall, ...] | list[ToolCall]


class BoundJudgeClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> JudgeResponse: ...


class JudgeClient(Protocol):
    def bind_tools(self, tools: list[RiskFlagJudgeToolSchema], *, tool_choice: object) -> BoundJudgeClient: ...


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_negotiated: bool = False
    has_non_standard_offer: bool = False
    has_financial_commitment: bool = False
    is_personalized: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIRiskFlagJudge:
    """Forced tool call có quota; mọi lỗi dự kiến fail-open về không-cờ-nào.

    Fail-open về `flags` toàn `False` là ĐÚNG chiều an toàn: regex
    `detect_risk_flags` vẫn là đáy (bên ngoài adapter), judge lỗi thì lượt đi
    tiếp như không có lớp hai.
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: JudgeClient | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client

    async def judge(self, *, user_message: str, draft_answer: str | None) -> RiskFlagPrediction:
        """Soát một nội dung sắp gửi; lỗi/quota/key trả không-cờ-nào, không raise."""

        budget = current_call_budget()
        if budget is not None and not budget.take(CallKind.OPTIONAL):
            return self._fallback(RiskFlagFallbackReason.OPTIONAL_BUDGET_EXHAUSTED)
        if not self._api_key:
            return self._fallback(RiskFlagFallbackReason.MISSING_API_KEY)
        try:
            if budget is not None:
                budget.record_provider_call()
            client = self._client or self._build_client()
            bound = client.bind_tools(
                [build_risk_flag_judge_tool()],
                tool_choice=RISK_FLAG_JUDGE_TOOL_NAME,
            )
            with anyio.fail_after(_TIMEOUT_SECONDS):
                response = await bound.ainvoke(self._messages(user_message, draft_answer))
            if not response.tool_calls:
                return self._fallback(RiskFlagFallbackReason.EMPTY_TOOL_CALL)
            payload = _ProviderPayload.model_validate(response.tool_calls[0]["args"])
            flags = {name: getattr(payload, name) for name in _FLAG_NAMES}
            return RiskFlagPrediction(flags=flags, confidence=payload.confidence)
        except TimeoutError:
            return self._fallback(RiskFlagFallbackReason.TIMEOUT)
        except (KeyError, ValidationError):
            return self._fallback(RiskFlagFallbackReason.INVALID_PAYLOAD)
        except APIError:
            return self._fallback(RiskFlagFallbackReason.PROVIDER_API_ERROR)
        except (ImportError, OSError, ValueError):
            return self._fallback(RiskFlagFallbackReason.UNEXPECTED_KNOWN_FAILURE)

    @staticmethod
    def _fallback(reason: RiskFlagFallbackReason) -> RiskFlagPrediction:
        logger.warning(
            _FALLBACK_LOG_MESSAGE,
            extra={
                "risk_flag_fallback_reason": reason.value,
                "risk_flag_confidence": 0.0,
            },
        )
        return RiskFlagPrediction(
            flags={name: False for name in _FLAG_NAMES},
            confidence=0.0,
            fallback_reason=reason,
        )

    def _build_client(self) -> JudgeClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            temperature=0.0,
            timeout=_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _messages(user_message: str, draft_answer: str | None) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        draft = draft_answer or "(chưa có bản nháp)"
        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Tin khách:\n{user_message}\n\nBản nháp hồi đáp:\n{draft}"),
        ]
