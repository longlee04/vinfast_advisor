"""Prompt đóng cho phân nhánh sau đề xuất."""

from __future__ import annotations

from typing import Final, TypedDict

from src.agents.domain.post_pitch_branch import PostPitchBranch

POST_PITCH_BRANCH_PROMPT_VERSION: Final[str] = "post-pitch-branch-v1"
POST_PITCH_BRANCH_TOOL_NAME: Final[str] = "classify_post_pitch_branch"
SYSTEM_PROMPT: Final[str] = (
    "Classify current customer message for the supplied post-pitch stage. "
    "Use the forced tool with one branch and confidence from 0 to 1."
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


class PostPitchBranchToolSchema(TypedDict):
    type: str
    function: FunctionSchema


def build_post_pitch_branch_tool() -> PostPitchBranchToolSchema:
    """Dựng forced-tool schema với tập nhánh đóng và confidence giới hạn."""

    return {
        "type": "function",
        "function": {
            "name": POST_PITCH_BRANCH_TOOL_NAME,
            "description": "Classify one post-pitch customer reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {"type": "string", "enum": [branch.value for branch in PostPitchBranch]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["branch", "confidence"],
                "additionalProperties": False,
            },
        },
    }
