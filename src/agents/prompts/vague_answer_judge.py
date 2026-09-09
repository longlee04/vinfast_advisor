"""Prompt đóng cho judge vague answer — phát hiện câu né giá trị mà regex bỏ sót."""

from __future__ import annotations

from typing import Final, TypedDict

VAGUE_JUDGE_PROMPT_VERSION: Final[str] = "vague-judge-v1"
VAGUE_JUDGE_TOOL_NAME: Final[str] = "classify_vague_answer"

SYSTEM_PROMPT: Final[str] = (
    "Bạn là bộ soát câu trả lời của khách trong một cuộc tư vấn xe. Bot vừa hỏi "
    "một thông tin cụ thể (ngân sách, số chỗ, quãng đường, mục đích...). Quyết "
    "định câu trả lời có THỰC SỰ cung cấp giá trị cho câu hỏi đó không. Câu mơ "
    "hồ ('tính thêm đã', 'tạm xem vậy', 'để em suy nghĩ', 'cũng được') là vague. "
    "Câu có giá trị — kể cả ngắn ('5', 'khoảng 500 triệu', 'gia đình') — KHÔNG "
    "phải vague. Dùng forced tool với is_vague và confidence từ 0 đến 1."
)


class JsonSchemaProperty(TypedDict, total=False):
    type: str
    minimum: float
    maximum: float


class JsonSchema(TypedDict):
    type: str
    properties: dict[str, JsonSchemaProperty]
    required: list[str]
    additionalProperties: bool


class FunctionSchema(TypedDict):
    name: str
    description: str
    parameters: JsonSchema


class VagueJudgeToolSchema(TypedDict):
    type: str
    function: FunctionSchema


def build_vague_judge_tool() -> VagueJudgeToolSchema:
    """Dựng forced-tool schema với verdict đóng và confidence giới hạn."""

    return {
        "type": "function",
        "function": {
            "name": VAGUE_JUDGE_TOOL_NAME,
            "description": "Decide whether a customer answer fails to provide the asked value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "is_vague": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["is_vague", "confidence"],
                "additionalProperties": False,
            },
        },
    }


__all__ = [
    "VAGUE_JUDGE_PROMPT_VERSION",
    "VAGUE_JUDGE_TOOL_NAME",
    "SYSTEM_PROMPT",
    "VagueJudgeToolSchema",
    "build_vague_judge_tool",
]
