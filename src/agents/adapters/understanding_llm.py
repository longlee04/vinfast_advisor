"""Một cửa LLM lõi v2 trên OpenAI — forced tool call, không bao giờ ném lỗi.

Chép hình `adapters/bottleneck_detector.py`: bind một tool đóng, ép gọi đúng
tool đó, pydantic validate, mọi lỗi biết trước thành một kết quả an toàn. Khác
một chỗ: kết quả an toàn ở đây KHÔNG phải một nhãn, mà là "không hiểu gì" —
`core/understand.understand()` đổi tiếp thành `UNCLEAR_UNDERSTANDING`.
"""

from __future__ import annotations

from typing import Any, Final, Protocol, TypedDict

from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.adapters.bottleneck_detector import AnyioTimeoutRunner, TimeoutRunner
from src.agents.core.state import DialogueAct, Intent
from src.agents.core.understand import (
    UNDERSTAND_PROMPT_VERSION,
    UNDERSTAND_TOOL_NAME,
    RawSlots,
    RawUnderstanding,
    UnderstandOutcome,
)
from src.agents.logging import get_agent_logger
from src.config import get_settings

logger = get_agent_logger("agent.adapters.understanding_llm")

#: Rộng hơn bottleneck (3s) vì prompt mang cả trạng thái, transcript và danh mục
#: xe. Đây là call CHẶN của lượt: quá hạn thì khách phải nhận câu hỏi lại, nên
#: không được để nó kéo dài hơn kiên nhẫn của người đang gõ.
UNDERSTAND_TIMEOUT_SECONDS: Final = 6.0


class JsonSchemaProperty(TypedDict, total=False):
    type: str
    description: str
    enum: list[str]
    minimum: float
    maximum: float
    items: dict[str, str]
    properties: dict[str, JsonSchemaProperty]
    additionalProperties: bool


class JsonSchema(TypedDict):
    type: str
    properties: dict[str, JsonSchemaProperty]
    required: list[str]
    additionalProperties: bool


class FunctionSchema(TypedDict):
    name: str
    description: str
    parameters: JsonSchema


class UnderstandingToolSchema(TypedDict):
    type: str
    function: FunctionSchema


def build_understanding_tool() -> UnderstandingToolSchema:
    """Schema đóng của tool. Enum sinh TỪ `DialogueAct`/`Intent`, không chép tay."""

    slots: dict[str, JsonSchemaProperty] = {
        "vehicle_type": {"type": "string", "enum": ["CAR", "ELECTRIC_MOTORBIKE"]},
        "budget_text": {"type": "string", "description": "Nguyên văn phần nói về tiền của khách"},
        "purpose": {"type": "string"},
        "seats": {"type": "integer"},
        "daily_km": {"type": "integer"},
        "features": {"type": "array", "items": {"type": "string"}},
        "region": {"type": "string"},
        "vehicle_names": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "function",
        "function": {
            "name": UNDERSTAND_TOOL_NAME,
            "description": "Ghi lại cách hiểu lượt nói mới nhất của khách.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dialogue_act": {"type": "string", "enum": [item.value for item in DialogueAct]},
                    "intent": {"type": "string", "enum": [item.value for item in Intent]},
                    "slots": {"type": "object", "properties": slots, "additionalProperties": False},
                    "choice_ref": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "features_all": {"type": "boolean"},
                    "question": {"type": "string"},
                },
                "required": ["dialogue_act", "intent", "confidence"],
                "additionalProperties": False,
            },
        },
    }


def model_kwargs(model_name: str) -> dict[str, Any]:
    """Tham số sinh của model.

    gpt-5.x CHỈ gọi được tool khi `reasoning_effort="none"` (đã đốt một buổi trên
    prod ngày 25/08 mới ra), và dòng đó cũng không nhận `temperature` khác 1 —
    nên hai nhánh loại trừ nhau, không phải gộp.
    """

    if model_name.startswith("gpt-5"):
        return {"reasoning_effort": "none"}
    return {"temperature": 0.0}


class _SlotsPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    vehicle_type: str | None = None
    budget_text: str | None = None
    purpose: str | None = None
    seats: int | None = None
    daily_km: int | None = None
    features: list[str] = Field(default_factory=list)
    region: str | None = None
    vehicle_names: list[str] = Field(default_factory=list)


class _UnderstandingPayload(BaseModel):
    """Hình đóng của tool call.

    `extra="ignore"` chứ không `forbid`: schema đã khoá hình ở phía provider, và
    một khoá thừa không đáng để vứt cả lượt của khách thành "không hiểu".
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    dialogue_act: str
    intent: str = Intent.NONE.value
    slots: _SlotsPayload = Field(default_factory=_SlotsPayload)
    choice_ref: str | None = None
    confidence: float = 0.0
    features_all: bool = False
    question: str = ""


class _BoundClient(Protocol):
    async def ainvoke(self, messages: list[object]) -> Any: ...


class UnderstanderClient(Protocol):
    def bind_tools(self, tools: list[UnderstandingToolSchema], *, tool_choice: object) -> _BoundClient: ...


class OpenAIUnderstander:
    """Ép đúng một tool call cho mỗi lượt; mọi lỗi biết trước thành `error`."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        *,
        client: UnderstanderClient | None = None,
        timeout: TimeoutRunner | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.model_name
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._client = client
        self._timeout = timeout or AnyioTimeoutRunner()

    async def understand(self, *, system_prompt: str, user_prompt: str) -> UnderstandOutcome:
        if not self._api_key:
            return self._failed("no_api_key")
        try:
            client = self._client or self._build_client()
            bound = client.bind_tools([build_understanding_tool()], tool_choice=UNDERSTAND_TOOL_NAME)
            response = await self._timeout.run(
                UNDERSTAND_TIMEOUT_SECONDS,
                lambda: bound.ainvoke(self._messages(system_prompt, user_prompt)),
            )
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return self._failed("no_tool_call")
            payload = _UnderstandingPayload.model_validate(tool_calls[0]["args"])
        except ValidationError:
            return self._failed("invalid_payload")
        except (APIError, ImportError, KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            return self._failed(type(error).__name__)
        return UnderstandOutcome(raw=_to_raw(payload))

    def _failed(self, error: str) -> UnderstandOutcome:
        logger.warning(
            "understand.failed error=%s model=%s prompt=%s",
            error,
            self._model_name,
            UNDERSTAND_PROMPT_VERSION,
        )
        return UnderstandOutcome(raw=None, error=error)

    def _build_client(self) -> UnderstanderClient:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=self._model_name,
            api_key=SecretStr(self._api_key),
            timeout=UNDERSTAND_TIMEOUT_SECONDS,
            **model_kwargs(self._model_name),
        )

    @staticmethod
    def _messages(system_prompt: str, user_prompt: str) -> list[object]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def _to_raw(payload: _UnderstandingPayload) -> RawUnderstanding:
    return RawUnderstanding(
        dialogue_act=payload.dialogue_act,
        intent=payload.intent,
        slots=RawSlots(
            vehicle_type=payload.slots.vehicle_type,
            budget_text=payload.slots.budget_text,
            purpose=payload.slots.purpose,
            seats=payload.slots.seats,
            daily_km=payload.slots.daily_km,
            features=tuple(payload.slots.features),
            region=payload.slots.region,
            vehicle_names=tuple(payload.slots.vehicle_names),
        ),
        choice_ref=payload.choice_ref,
        confidence=payload.confidence,
        features_all=payload.features_all,
        question=payload.question,
    )
