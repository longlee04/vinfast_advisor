"""Adapter `ConversationalWriter` — gpt viết câu đáp xã giao theo PERSONA của Vivi.

Cùng khuôn `spec_tool_llm`: không key → `None`, mọi lỗi biết trước → `None`, có
timeout. Câu viết ra CHƯA được tin: `services.conversational._acceptable` soi
lại (không bịa số, không giới thiệu lại, đúng một câu hỏi) rồi mới tới khách.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from openai import APIError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.config import get_settings

logger = logging.getLogger(__name__)

#: Lượt xã giao phải nhanh: quá mức này thì dùng câu mẫu, khách không phải chờ.
CONVERSATIONAL_TIMEOUT_SECONDS = 6.0


class _ChatClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class OpenAIConversationalWriter:
    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: _ChatClient | None = None,
        timeout: TimeoutRunner | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()

    async def write(self, *, system_prompt: str, user_prompt: str) -> str | None:
        if not self._api_key:
            return self._failed("no_api_key")
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            client = self._client or self._build_client()
            messages: list[object] = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            response = await self._timeout.run(CONVERSATIONAL_TIMEOUT_SECONDS, lambda: client.ainvoke(messages))
        except (APIError, ImportError, KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            return self._failed(type(error).__name__)
        content = getattr(response, "content", "")
        text = content if isinstance(content, str) else ""
        return text.strip() or self._failed("empty")

    def _failed(self, error: str) -> None:
        logger.warning("conversational_llm.failed error=%s model=%s", error, self._model_name)
        return None

    def _build_client(self) -> _ChatClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        # Câu xã giao cần tự nhiên, không cần tất định như cửa hiểu ý: nhiệt độ
        # vừa phải. Dòng gpt-5 không nhận temperature khác 1 (xem `model_kwargs`).
        extra: dict[str, Any] = (
            {"reasoning_effort": "none"} if self._model_name.startswith("gpt-5") else {"temperature": 0.6}
        )
        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=CONVERSATIONAL_TIMEOUT_SECONDS,
            **extra,
        )


__all__ = ["CONVERSATIONAL_TIMEOUT_SECONDS", "OpenAIConversationalWriter"]
