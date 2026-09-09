"""Fail-open OpenAI adapter cho judge vague answer (lớp hai sau regex slot_salvage)."""

from __future__ import annotations

import logging
from typing import Final, Protocol, TypedDict

import anyio
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.slot_salvage import VagueFallbackReason, VagueJudgePrediction
from src.agents.prompts.vague_answer_judge import (
    SYSTEM_PROMPT,
    VAGUE_JUDGE_TOOL_NAME,
    VagueJudgeToolSchema,
    build_vague_judge_tool,
)
from src.agents.services.call_budget import CallKind, current_call_budget
from src.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: Final[float] = 3.0
_FALLBACK_LOG_MESSAGE: Final[str] = "vague_judge.fallback"


class ToolCall(TypedDict):
    args: dict[str, object]


class JudgeResponse(Protocol):
    tool_calls: tuple[ToolCall, ...] | list[ToolCall]


class BoundJudgeClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> JudgeResponse: ...


class JudgeClient(Protocol):
    def bind_tools(self, tools: list[VagueJudgeToolSchema], *, tool_choice: object) -> BoundJudgeClient: ...


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_vague: bool
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIVagueAnswerJudge:
    """Forced tool call có quota; mọi lỗi dự kiến fail-open về không-mơ-hồ.

    Fail-open về `False` là ĐÚNG chiều an toàn: regex `is_vague_answer` vẫn là
    đáy (bên ngoài adapter), judge lỗi thì lượt đi tiếp như không có lớp hai.
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

    async def judge(self, *, user_message: str, last_question: str) -> VagueJudgePrediction:
        """Đọc một câu trả lời; lỗi/quota/key trả không-mơ-hồ, không raise."""

        budget = current_call_budget()
        if budget is not None and not budget.take(CallKind.OPTIONAL):
            return self._fallback(VagueFallbackReason.OPTIONAL_BUDGET_EXHAUSTED)
        if not self._api_key:
            return self._fallback(VagueFallbackReason.MISSING_API_KEY)
        try:
            if budget is not None:
                budget.record_provider_call()
            client = self._client or self._build_client()
            bound = client.bind_tools(
                [build_vague_judge_tool()],
                tool_choice=VAGUE_JUDGE_TOOL_NAME,
            )
            with anyio.fail_after(_TIMEOUT_SECONDS):
                response = await bound.ainvoke(self._messages(user_message, last_question))
            if not response.tool_calls:
                return self._fallback(VagueFallbackReason.EMPTY_TOOL_CALL)
            payload = _ProviderPayload.model_validate(response.tool_calls[0]["args"])
            return VagueJudgePrediction(payload.is_vague, payload.confidence)
        except TimeoutError:
            return self._fallback(VagueFallbackReason.TIMEOUT)
        except (KeyError, ValidationError):
            return self._fallback(VagueFallbackReason.INVALID_PAYLOAD)
        except APIError:
            return self._fallback(VagueFallbackReason.PROVIDER_API_ERROR)
        except (ImportError, OSError, ValueError):
            return self._fallback(VagueFallbackReason.UNEXPECTED_KNOWN_FAILURE)

    @staticmethod
    def _fallback(reason: VagueFallbackReason) -> VagueJudgePrediction:
        logger.warning(
            _FALLBACK_LOG_MESSAGE,
            extra={
                "vague_fallback_reason": reason.value,
                "vague_is_vague": False,
                "vague_confidence": 0.0,
            },
        )
        return VagueJudgePrediction(False, 0.0, reason)

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
    def _messages(user_message: str, last_question: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Bot vừa hỏi: {last_question}\nKhách trả lời: {user_message}"),
        ]
