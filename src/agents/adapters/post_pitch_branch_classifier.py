"""Fail-open OpenAI adapter cho phân nhánh sau đề xuất."""

from __future__ import annotations

import logging
from typing import Final, Protocol, TypedDict

import anyio
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.post_pitch import PostPitchStage
from src.agents.domain.post_pitch_branch import (
    PostPitchBranch,
    PostPitchBranchPrediction,
    PostPitchFallbackReason,
)
from src.agents.prompts.post_pitch_branch import (
    POST_PITCH_BRANCH_TOOL_NAME,
    SYSTEM_PROMPT,
    PostPitchBranchToolSchema,
    build_post_pitch_branch_tool,
)
from src.agents.services.call_budget import CallKind, current_call_budget
from src.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: Final[float] = 3.0
_FALLBACK_LOG_MESSAGE: Final[str] = "post_pitch_classifier.fallback"


class ToolCall(TypedDict):
    args: dict[str, str | float]


class ClassifierResponse(Protocol):
    tool_calls: tuple[ToolCall, ...] | list[ToolCall]


class BoundClassifierClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> ClassifierResponse: ...


class ClassifierClient(Protocol):
    def bind_tools(self, tools: list[PostPitchBranchToolSchema], *, tool_choice: object) -> BoundClassifierClient: ...


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    branch: PostPitchBranch
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIPostPitchBranchClassifier:
    """Forced tool call có quota; mọi lỗi dự kiến đều fail-open về UNCLEAR."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: ClassifierClient | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client

    async def classify(self, stage: PostPitchStage, user_message: str) -> PostPitchBranchPrediction:
        """Đọc một lượt post-pitch; thiếu quota/key/provider trả UNCLEAR, không raise."""

        budget = current_call_budget()
        if budget is not None and not budget.take(CallKind.OPTIONAL):
            return self._fallback(PostPitchFallbackReason.OPTIONAL_BUDGET_EXHAUSTED)
        if not self._api_key:
            return self._fallback(PostPitchFallbackReason.MISSING_API_KEY)
        try:
            if budget is not None:
                budget.record_provider_call()
            client = self._client or self._build_client()
            bound = client.bind_tools(
                [build_post_pitch_branch_tool()],
                tool_choice=POST_PITCH_BRANCH_TOOL_NAME,
            )
            with anyio.fail_after(_TIMEOUT_SECONDS):
                response = await bound.ainvoke(self._messages(stage, user_message))
            if not response.tool_calls:
                return self._fallback(PostPitchFallbackReason.EMPTY_TOOL_CALL)
            payload = _ProviderPayload.model_validate(response.tool_calls[0]["args"])
            return PostPitchBranchPrediction(payload.branch, payload.confidence)
        except TimeoutError:
            return self._fallback(PostPitchFallbackReason.TIMEOUT)
        except (KeyError, ValidationError):
            return self._fallback(PostPitchFallbackReason.INVALID_PAYLOAD)
        except APIError:
            return self._fallback(PostPitchFallbackReason.PROVIDER_API_ERROR)
        except (ImportError, OSError, ValueError):
            return self._fallback(PostPitchFallbackReason.UNEXPECTED_KNOWN_FAILURE)

    @staticmethod
    def _fallback(reason: PostPitchFallbackReason) -> PostPitchBranchPrediction:
        logger.warning(
            _FALLBACK_LOG_MESSAGE,
            extra={
                "post_pitch_fallback_reason": reason.value,
                "post_pitch_branch": PostPitchBranch.UNCLEAR.value,
                "post_pitch_confidence": 0.0,
            },
        )
        return PostPitchBranchPrediction(PostPitchBranch.UNCLEAR, 0.0, reason)

    def _build_client(self) -> ClassifierClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            temperature=0.0,
            timeout=_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _messages(stage: PostPitchStage, user_message: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"stage={stage.value}\nmessage={user_message}"),
        ]
