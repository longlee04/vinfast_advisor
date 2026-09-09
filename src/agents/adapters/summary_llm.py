"""Dedicated OpenAI adapter for bounded incremental conversation summaries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.agents.logging import get_agent_logger
from src.agents.prompts.conversation_summary_prompts import (
    SUMMARY_TOOL,
    SYSTEM_PROMPT,
    summary_input,
)
from src.config import get_settings

logger = get_agent_logger("agent.adapters.summary_llm")


class SummaryPayload(BaseModel):
    """Validated structured result from the summary tool call."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1, max_length=2_000)


class OpenAIConversationSummarizer:
    """Update memory with a separate temperature-zero model call."""

    def __init__(self, model_name: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key

    @property
    def model_name(self) -> str:
        """Return summary model metadata without exposing credentials."""

        return self._model_name

    async def summarize(self, *, previous_summary: str, user_message: str, assistant_response: str) -> str:
        """Return a validated summary or raise for the best-effort caller to ignore."""

        if not self._api_key:
            raise RuntimeError("conversation summarizer is not configured")
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI
            from pydantic import SecretStr

            client = ChatOpenAI(
                model=self._model_name,
                api_key=SecretStr(self._api_key),
                temperature=0.0,
            )
            bound = client.bind_tools(
                [{"type": "function", "function": SUMMARY_TOOL}],
                tool_choice={
                    "type": "function",
                    "function": {"name": SUMMARY_TOOL["name"]},
                },
            )
            response = await bound.ainvoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=summary_input(
                            previous_summary=previous_summary,
                            user_message=user_message,
                            assistant_response=assistant_response,
                        )
                    ),
                ]
            )
        except Exception as error:  # noqa: BLE001 - SDK errors become a stable port error
            logger.warning("Conversation summary call failed (%s)", type(error).__name__)
            raise RuntimeError("conversation summary call failed") from error
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            raise ValueError("conversation summarizer returned no tool call")
        payload = SummaryPayload.model_validate(tool_calls[0].get("args") or {})
        return payload.summary.strip()
