"""Prompt đóng cho judge risk flag — soát nội dung sắp gửi khách có cam kết thương mại."""

from __future__ import annotations

from typing import Final, TypedDict

RISK_FLAG_JUDGE_PROMPT_VERSION: Final[str] = "risk-flag-judge-v1"
RISK_FLAG_JUDGE_TOOL_NAME: Final[str] = "classify_quote_risk"

SYSTEM_PROMPT: Final[str] = (
    "Bạn là cổng soát rủi ro thương mại của một trợ lý tư vấn xe. Đọc câu khách "
    "và BẢN NHÁP hồi đáp sắp gửi, quyết định hồi đáp có mang cam kết thương mại "
    "cần người duyệt không. Bốn cờ: is_negotiated (mặc cả giá), "
    "has_non_standard_offer (ưu đãi/quà ngoài chính sách), has_financial_commitment "
    "(cam kết tài chính: trả góp, cọc, hợp đồng, thanh toán), is_personalized "
    "(giá điều chỉnh riêng theo hồ sơ khách). Chỉ bật cờ khi nội dung THỰC SỰ hứa "
    "một điều khoản như vậy; tư vấn thông số/giá niêm yết bình thường thì tắt cả "
    "bốn. Dùng forced tool với bốn cờ và confidence từ 0 đến 1."
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


class RiskFlagJudgeToolSchema(TypedDict):
    type: str
    function: FunctionSchema


def build_risk_flag_judge_tool() -> RiskFlagJudgeToolSchema:
    """Dựng forced-tool schema với bốn cờ đóng và confidence giới hạn."""

    return {
        "type": "function",
        "function": {
            "name": RISK_FLAG_JUDGE_TOOL_NAME,
            "description": "Decide whether an outgoing reply carries a commercial commitment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "is_negotiated": {"type": "boolean"},
                    "has_non_standard_offer": {"type": "boolean"},
                    "has_financial_commitment": {"type": "boolean"},
                    "is_personalized": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": [
                    "is_negotiated",
                    "has_non_standard_offer",
                    "has_financial_commitment",
                    "is_personalized",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    }


__all__ = [
    "RISK_FLAG_JUDGE_PROMPT_VERSION",
    "RISK_FLAG_JUDGE_TOOL_NAME",
    "SYSTEM_PROMPT",
    "RiskFlagJudgeToolSchema",
    "build_risk_flag_judge_tool",
]
