"""Closed prompt and tool schema for bottleneck classification."""

from __future__ import annotations

from typing import Final, TypedDict

from src.agents.domain.customer_profile import Bottleneck

BOTTLENECK_DETECTION_PROMPT_VERSION: Final = "bottleneck-detection-v2"
BOTTLENECK_DETECTION_TOOL_NAME: Final = "detect_customer_bottleneck"
SYSTEM_PROMPT: Final = (
    "Classify only current customer message. Use supplied tool. "
    "Choose DETECTED with one supported label or NONE. Do not create evidence. "
    "When DETECTED, report confidence from 0.0 to 1.0."
)


class JsonSchemaProperty(TypedDict, total=False):
    type: str
    enum: list[str]
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


class BottleneckToolSchema(TypedDict):
    type: str
    function: FunctionSchema


def build_bottleneck_detection_tool() -> BottleneckToolSchema:
    """Build schema with closed status and customer bottleneck enums."""

    return {
        "type": "function",
        "function": {
            "name": BOTTLENECK_DETECTION_TOOL_NAME,
            "description": "Classify current customer turn into one supported bottleneck or none.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["DETECTED", "NONE"]},
                    "label": {
                        "type": "string",
                        "enum": [label.value for label in Bottleneck],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["status"],
                "additionalProperties": False,
            },
        },
    }
