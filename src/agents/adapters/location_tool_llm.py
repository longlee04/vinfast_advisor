"""LLM tự gọi tool `tim_diem_dich_vu` — chọn LOẠI điểm và KHU VỰC từ câu khách.

Cùng khuôn `adapters/tco_tool_llm.py`: ép tool_choice, pydantic validate, mọi
lỗi biết trước thành `None`. Giá trị của tool nằm ở chỗ bộ dò từ khoá chịu
thua: "chỗ nào cắm điện được", "tủ pin gần chợ Bến Thành" — LLM đọc ra loại
điểm và địa danh mà regex không bắt nổi.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.agents.adapters.understanding_llm import model_kwargs
from src.agents.domain.location_tool import LOCATION_TOOL_NAME, LocationToolArgs
from src.agents.domain.nearby_location import LocationKind
from src.config import get_settings

logger = logging.getLogger(__name__)

LOCATION_TOOL_TIMEOUT_SECONDS = 8.0

_SYSTEM_PROMPT = (
    "Bạn là bộ chọn tham số cho tool tìm điểm dịch vụ VinFast (trạm sạc, showroom, "
    "tủ đổi pin, xưởng dịch vụ).\n"
    "Đọc câu khách rồi GỌI tool `tim_diem_dich_vu`.\n"
    "- `kinds`: LOẠI điểm khách đang tìm, chọn trong danh sách cho sẵn; ô tô hay xe "
    "máy suy từ ngữ cảnh, không rõ loại xe thì lấy cả hai bản CAR và MOTORBIKE; "
    "khách không tìm điểm nào thì để mảng rỗng.\n"
    "- `area`: địa danh khách nhắc (quận/huyện/tỉnh/địa điểm), ghi đúng như khách "
    "nói. Không nhắc thì null.\n"
    "TUYỆT ĐỐI không bịa: không chắc thì để rỗng/null, không đoán."
)


def build_location_tool() -> dict[str, Any]:
    """Schema đóng — `kinds` là enum sinh TỪ `LocationKind`, không chép tay."""
    return {
        "type": "function",
        "function": {
            "name": LOCATION_TOOL_NAME,
            "description": "Tìm trạm sạc, showroom, tủ đổi pin hoặc xưởng dịch vụ VinFast gần một khu vực.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": [kind.value for kind in LocationKind]},
                        "description": "Các loại điểm khách tìm; rỗng nếu không rõ.",
                    },
                    "area": {
                        "type": ["string", "null"],
                        "description": "Địa danh khách nhắc; null nếu khách không nói.",
                    },
                },
                "required": ["kinds", "area"],
            },
        },
    }


class _LocationArgsPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    kinds: list[str] = Field(default_factory=list)
    area: str | None = None


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class LocationToolClient(Protocol):
    def bind_tools(self, tools: list[dict[str, Any]], *, tool_choice: object) -> _BoundClient: ...


class OpenAILocationArgResolver:
    """Ép đúng một lần gọi tool `tim_diem_dich_vu`; mọi lỗi biết trước thành `None`."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: LocationToolClient | None = None,
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
        known_kinds: tuple[str, ...],
        known_area: str | None,
    ) -> LocationToolArgs | None:
        if not self._api_key:
            return self._failed("no_api_key")
        try:
            client = self._client or self._build_client()
            bound = client.bind_tools([build_location_tool()], tool_choice=LOCATION_TOOL_NAME)
            user_prompt = (
                f"Đã biết: loại điểm={', '.join(known_kinds) or 'chưa rõ'}; "
                f"khu vực={known_area or 'chưa rõ'}\n"
                f"Khách vừa nói: {user_message}"
            )
            response = await self._timeout.run(
                LOCATION_TOOL_TIMEOUT_SECONDS,
                lambda: bound.ainvoke(self._messages(user_prompt)),
            )
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return self._failed("no_tool_call")
            payload = _LocationArgsPayload.model_validate(tool_calls[0]["args"])
        except ValidationError:
            return self._failed("invalid_payload")
        except (APIError, ImportError, KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            return self._failed(type(error).__name__)
        logger.info(
            "location_tool.called model=%s kinds=%s area=%s",
            self._model_name,
            payload.kinds,
            payload.area,
        )
        return LocationToolArgs(kinds=tuple(payload.kinds), area=payload.area)

    def _failed(self, error: str) -> None:
        logger.warning("location_tool.failed error=%s model=%s", error, self._model_name)
        return None

    def _build_client(self) -> LocationToolClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=LOCATION_TOOL_TIMEOUT_SECONDS,
            **model_kwargs(self._model_name),
        )

    @staticmethod
    def _messages(user_prompt: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
