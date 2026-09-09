"""LLM tự gọi tool `tra_thong_so` — chọn NHÓM thông số cho câu hỏi tự do.

Cùng khuôn `tco_tool_llm`/`location_tool_llm`: ép tool_choice, pydantic
validate, mọi lỗi biết trước thành `None`. LLM chỉ trỏ nhóm — con số và lời
đánh giá vẫn tất định từ catalog (`render.spec_answer_by_group`).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from openai import APIError
from pydantic import BaseModel, ConfigDict, ValidationError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.agents.adapters.understanding_llm import model_kwargs
from src.agents.domain.spec_tool import SPEC_GROUPS, SPEC_TOOL_NAME, SpecToolArgs
from src.config import get_settings

logger = logging.getLogger(__name__)

SPEC_TOOL_TIMEOUT_SECONDS = 8.0

_SYSTEM_PROMPT = (
    "Bạn là bộ phân loại câu hỏi thông số xe điện.\n"
    "Đọc câu khách rồi GỌI tool `tra_thong_so` với `group` = nhóm thông số khách "
    "đang hỏi, chọn trong danh sách cho sẵn.\n"
    "Khách không hỏi về thông số nào trong danh sách thì để null.\n"
    "TUYỆT ĐỐI không đoán: không chắc thì null."
)


def build_spec_tool() -> dict[str, Any]:
    """Schema đóng — enum nhóm sinh TỪ `SPEC_GROUPS`, không chép tay."""
    described = "; ".join(f"{key}: {label}" for key, label in SPEC_GROUPS.items())
    return {
        "type": "function",
        "function": {
            "name": SPEC_TOOL_NAME,
            "description": f"Xếp câu hỏi của khách vào một nhóm thông số xe. Các nhóm: {described}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": ["string", "null"],
                        "enum": [*SPEC_GROUPS.keys(), None],
                        "description": "Nhóm thông số khách hỏi; null nếu không thuộc nhóm nào.",
                    }
                },
                "required": ["group"],
            },
        },
    }


class _SpecArgsPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    group: str | None = None


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class SpecToolClient(Protocol):
    def bind_tools(self, tools: list[dict[str, Any]], *, tool_choice: object) -> _BoundClient: ...


class OpenAISpecArgResolver:
    """Ép đúng một lần gọi tool `tra_thong_so`; mọi lỗi biết trước thành `None`."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: SpecToolClient | None = None,
        timeout: TimeoutRunner | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()

    async def resolve(self, *, question: str, vehicle_name: str) -> SpecToolArgs | None:
        if not self._api_key:
            return self._failed("no_api_key")
        try:
            client = self._client or self._build_client()
            bound = client.bind_tools([build_spec_tool()], tool_choice=SPEC_TOOL_NAME)
            user_prompt = f"Xe đang hỏi: {vehicle_name}\nCâu khách: {question}"
            response = await self._timeout.run(
                SPEC_TOOL_TIMEOUT_SECONDS,
                lambda: bound.ainvoke(self._messages(user_prompt)),
            )
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return self._failed("no_tool_call")
            payload = _SpecArgsPayload.model_validate(tool_calls[0]["args"])
        except ValidationError:
            return self._failed("invalid_payload")
        except (APIError, ImportError, KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            return self._failed(type(error).__name__)
        logger.info("spec_tool.called model=%s group=%s", self._model_name, payload.group)
        return SpecToolArgs(group=payload.group)

    def _failed(self, error: str) -> None:
        logger.warning("spec_tool.failed error=%s model=%s", error, self._model_name)
        return None

    def _build_client(self) -> SpecToolClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=SPEC_TOOL_TIMEOUT_SECONDS,
            **model_kwargs(self._model_name),
        )

    @staticmethod
    def _messages(user_prompt: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
