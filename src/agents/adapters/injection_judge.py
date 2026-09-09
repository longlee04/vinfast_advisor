"""Fail-open OpenAI adapter cho judge tiêm nhiễm (lớp hai sau blocklist)."""

from __future__ import annotations

import logging
from typing import Final, Protocol, TypedDict

import anyio
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.injection_gate import (
    InjectionFallbackReason,
    InjectionJudgePrediction,
)
from src.agents.prompts.injection_judge import (
    INJECTION_JUDGE_TOOL_NAME,
    SYSTEM_PROMPT,
    InjectionJudgeToolSchema,
    build_injection_judge_tool,
)
from src.agents.services.call_budget import CallKind, current_call_budget
from src.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: Final[float] = 3.0
_FALLBACK_LOG_MESSAGE: Final[str] = "injection_judge.fallback"


class ToolCall(TypedDict):
    args: dict[str, object]


class JudgeResponse(Protocol):
    tool_calls: tuple[ToolCall, ...] | list[ToolCall]


class BoundJudgeClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> JudgeResponse: ...


class JudgeClient(Protocol):
    def bind_tools(self, tools: list[InjectionJudgeToolSchema], *, tool_choice: object) -> BoundJudgeClient: ...


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_injection: bool
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIInjectionJudge:
    """Forced tool call có quota; mọi lỗi dự kiến fail-open về không-tiêm-nhiễm.

    Fail-open về `False` là ĐÚNG chiều an toàn ở đây: regex blocklist vẫn là
    đáy (bên ngoài adapter). Judge lỗi thì lượt đi tiếp như chưa từng có lớp
    hai — cửa vẫn đóng bằng regex, không biến thành cửa mở.
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

    async def judge(self, user_message: str) -> InjectionJudgePrediction:
        """Đọc một tin khách; thiếu quota/key/provider trả không-tiêm-nhiễm, không raise."""

        budget = current_call_budget()
        if budget is not None and not budget.take(CallKind.OPTIONAL):
            return self._fallback(InjectionFallbackReason.OPTIONAL_BUDGET_EXHAUSTED)
        if not self._api_key:
            return self._fallback(InjectionFallbackReason.MISSING_API_KEY)
        try:
            if budget is not None:
                budget.record_provider_call()
            client = self._client or self._build_client()
            bound = client.bind_tools(
                [build_injection_judge_tool()],
                tool_choice=INJECTION_JUDGE_TOOL_NAME,
            )
            with anyio.fail_after(_TIMEOUT_SECONDS):
                response = await bound.ainvoke(self._messages(user_message))
            if not response.tool_calls:
                return self._fallback(InjectionFallbackReason.EMPTY_TOOL_CALL)
            payload = _ProviderPayload.model_validate(response.tool_calls[0]["args"])
            return InjectionJudgePrediction(payload.is_injection, payload.confidence)
        except TimeoutError:
            return self._fallback(InjectionFallbackReason.TIMEOUT)
        except (KeyError, ValidationError):
            return self._fallback(InjectionFallbackReason.INVALID_PAYLOAD)
        except APIError:
            return self._fallback(InjectionFallbackReason.PROVIDER_API_ERROR)
        except (ImportError, OSError, ValueError):
            return self._fallback(InjectionFallbackReason.UNEXPECTED_KNOWN_FAILURE)

    @staticmethod
    def _fallback(reason: InjectionFallbackReason) -> InjectionJudgePrediction:
        logger.warning(
            _FALLBACK_LOG_MESSAGE,
            extra={
                "injection_fallback_reason": reason.value,
                "injection_is_injection": False,
                "injection_confidence": 0.0,
            },
        )
        return InjectionJudgePrediction(False, 0.0, reason)

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
    def _messages(user_message: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"message={user_message}"),
        ]
