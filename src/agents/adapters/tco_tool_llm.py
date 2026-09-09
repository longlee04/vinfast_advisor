"""LLM tự gọi tool `tinh_chi_phi` để chọn km/ngày và tỉnh cho bảng chi phí.

Chép hình `adapters/understanding_llm.py` (bind tool, ép tool_choice, pydantic
validate, mọi lỗi biết trước thành kết quả an toàn) nhưng khác một điểm cố ý:
đây là đường PHỤ — lỗi trả `None` chứ không trả outcome có cờ error, vì
`core/act._tco` chỉ cần biết "có tham số dùng được hay không" rồi tự đi tiếp
đường tất định. gpt-5.x vẫn cần `reasoning_effort="none"` mới gọi được tool
(bài học 25/08) — dùng lại `model_kwargs` cho khỏi dính lần hai.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from openai import APIError
from pydantic import BaseModel, ConfigDict, ValidationError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.agents.adapters.understanding_llm import model_kwargs
from src.agents.domain.tco_tool import TCO_TOOL_NAME, TcoToolArgs
from src.config import get_settings

logger = logging.getLogger(__name__)

TCO_TOOL_TIMEOUT_SECONDS = 8.0

_SYSTEM_PROMPT = (
    "Bạn là bộ chọn tham số cho tool tính chi phí sử dụng xe điện.\n"
    "Đọc câu khách và thông tin đã biết, rồi GỌI tool `tinh_chi_phi`.\n"
    "- `daily_km`: số km khách chạy MỖI NGÀY. Khách nói theo tháng thì chia 30, "
    "theo tuần thì chia 7, làm tròn về số nguyên. Khách không nhắc gì tới quãng "
    "đường thì để null.\n"
    "- `province`: tỉnh/thành khách đăng ký xe hoặc đang sống, ghi đúng như khách "
    "nói. Khách không nhắc thì để null.\n"
    "TUYỆT ĐỐI không bịa: thiếu thông tin thì để null, không đoán."
)


def build_tco_tool() -> dict[str, Any]:
    """Schema đóng của tool — hai tham số, đều cho phép null."""
    return {
        "type": "function",
        "function": {
            "name": TCO_TOOL_NAME,
            "description": "Tính chi phí sử dụng xe điện theo quãng đường mỗi ngày và tỉnh đăng ký.",
            "parameters": {
                "type": "object",
                "properties": {
                    "daily_km": {
                        "type": ["integer", "null"],
                        "description": "Số km khách chạy mỗi ngày; null nếu khách không nói.",
                    },
                    "province": {
                        "type": ["string", "null"],
                        "description": "Tỉnh/thành khách đăng ký xe; null nếu khách không nói.",
                    },
                },
                "required": ["daily_km", "province"],
            },
        },
    }


class _TcoArgsPayload(BaseModel):
    """`extra="ignore"`: khoá thừa không đáng vứt cả lần gọi (cùng lý do extractor)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    daily_km: int | None = None
    province: str | None = None


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class TcoToolClient(Protocol):
    def bind_tools(self, tools: list[dict[str, Any]], *, tool_choice: object) -> _BoundClient: ...


class OpenAITcoArgResolver:
    """Ép đúng một lần gọi tool `tinh_chi_phi`; mọi lỗi biết trước thành `None`."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: TcoToolClient | None = None,
        timeout: TimeoutRunner | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()

    async def resolve(
        self,
        *,
        user_message: str,
        vehicle_name: str,
        known_daily_km: int | None,
        known_province: str | None,
    ) -> TcoToolArgs | None:
        if not self._api_key:
            return self._failed("no_api_key")
        try:
            client = self._client or self._build_client()
            bound = client.bind_tools([build_tco_tool()], tool_choice=TCO_TOOL_NAME)
            user_prompt = (
                f"Xe đang tính: {vehicle_name}\n"
                f"Đã biết: km/ngày={known_daily_km if known_daily_km is not None else 'chưa rõ'}; "
                f"tỉnh={known_province or 'chưa rõ'}\n"
                f"Khách vừa nói: {user_message}"
            )
            response = await self._timeout.run(
                TCO_TOOL_TIMEOUT_SECONDS,
                lambda: bound.ainvoke(self._messages(user_prompt)),
            )
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return self._failed("no_tool_call")
            payload = _TcoArgsPayload.model_validate(tool_calls[0]["args"])
        except ValidationError:
            return self._failed("invalid_payload")
        except (APIError, ImportError, KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            return self._failed(type(error).__name__)
        logger.info(
            "tco_tool.called model=%s daily_km=%s province=%s",
            self._model_name,
            payload.daily_km,
            payload.province,
        )
        return TcoToolArgs(daily_km=payload.daily_km, province=payload.province)

    def _failed(self, error: str) -> None:
        logger.warning("tco_tool.failed error=%s model=%s", error, self._model_name)
        return None

    def _build_client(self) -> TcoToolClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=TCO_TOOL_TIMEOUT_SECONDS,
            **model_kwargs(self._model_name),
        )

    @staticmethod
    def _messages(user_prompt: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
