"""Prompt cho hai việc nền của Customer 360 (plan §5.3, §5.4).

Cả hai là forced tool call, nhiệt độ 0, và KHÔNG bao giờ sinh câu gửi khách.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

INSIGHT_PROMPT_VERSION: Final = "insight-v1"
INSIGHT_TOOL_NAME: Final = "ghi_thong_tin_khach"
CLASSIFY_PROMPT_VERSION: Final = "opportunity-classify-v1"
CLASSIFY_TOOL_NAME: Final = "phan_loai_co_hoi"

INSIGHT_SYSTEM_PROMPT: Final = """Bạn là bộ trích xuất THÔNG TIN KHÁCH TỰ NÓI trong hội thoại mua xe VinFast.
Chỉ ghi điều khách NÓI RA TRỰC TIẾP. CẤM suy diễn.
Ví dụ CẤM: "chở con đi học" KHÔNG suy ra "đã có gia đình", "thu nhập khá", hay tuổi.
Mỗi mục PHẢI có evidence_quote là đoạn CHÉP NGUYÊN VĂN (không sửa chữ) từ đúng câu có turn_index đó.
Không có bằng chứng nguyên văn → không ghi. Không chắc → không ghi.
Chỉ dùng các field trong schema. Không có gì để ghi → trả insights: [].
Ý nghĩa field:
- purchase_timeframe: khách định mua khi nào.
- payment_method: trả thẳng hay trả góp.
- current_vehicle: xe khách đang đi (hãng/mẫu) nếu khách nói.
- trade_in: khách muốn đổi/bán xe cũ khi mua (YES/NO).
- decision_maker: ai quyết định mua, nếu khách nói rõ.
- competitor_brand: hãng xe khác khách đang cân nhắc.
- other_concern: băn khoăn khác ngoài giá/sạc/pin/quãng đường.
- buyer_for: khách mua cho ai, nếu khách nói rõ.
- customer_group: khách tự nói mình thuộc nhóm công an/quân đội, VNPost, hội viên VinClub."""

CLASSIFY_SYSTEM_PROMPT: Final = """Bạn phân loại MỘT phiên chat mua xe so với các nhu cầu mua (cơ hội) đã biết của cùng khách.
Trả lời:
- same: phiên này nói tiếp đúng nhu cầu mua đó, không đổi gì đáng kể.
- update: vẫn nhu cầu mua đó nhưng khách đổi/bổ sung tiêu chí (ngân sách, số người, mục đích...).
- new: khách đang tìm một chiếc xe KHÁC cho một nhu cầu khác (người dùng khác, mục đích khác).
Chọn opportunity_id của cơ hội phù hợp nhất khi trả lời same/update.
confidence từ 0 đến 1 — không chắc thì cho thấp, tư vấn viên sẽ quyết."""

_VALUE_CODE_DESCRIPTION: Final = (
    "purchase_timeframe: WITHIN_1_MONTH|1_3_MONTHS|3_6_MONTHS|OVER_6_MONTHS|UNDECIDED; "
    "payment_method: CASH|INSTALLMENT|UNDECIDED; trade_in: YES|NO; "
    "decision_maker: SELF|SPOUSE|PARENTS|COMPANY|OTHER; buyer_for: SELF|FAMILY|COMPANY|OTHER; "
    "customer_group: POLICE_MILITARY|VNPOST|VINCLUB|OTHER; các field khác: null"
)

INSIGHT_TOOL: Final[dict[str, Any]] = {
    "name": INSIGHT_TOOL_NAME,
    "description": "Ghi các thông tin khách tự nói ra, mỗi mục kèm câu nguyên văn.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["insights"],
        "properties": {
            "insights": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field", "value", "value_code", "evidence_quote", "turn_index", "confidence"],
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": [
                                "purchase_timeframe",
                                "payment_method",
                                "current_vehicle",
                                "trade_in",
                                "decision_maker",
                                "competitor_brand",
                                "other_concern",
                                "buyer_for",
                                "customer_group",
                            ],
                        },
                        "value": {"type": "string", "maxLength": 120},
                        "value_code": {"type": ["string", "null"], "description": _VALUE_CODE_DESCRIPTION},
                        "evidence_quote": {"type": "string", "minLength": 2, "maxLength": 300},
                        "turn_index": {"type": "integer", "minimum": 0},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    },
}

CLASSIFY_TOOL: Final[dict[str, Any]] = {
    "name": CLASSIFY_TOOL_NAME,
    "description": "Phiên này thuộc nhu cầu mua nào.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "opportunity_id", "confidence"],
        "properties": {
            "verdict": {"type": "string", "enum": ["same", "update", "new"]},
            "opportunity_id": {"type": ["string", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}


def insight_input(user_turns: Mapping[int, str]) -> str:
    """Chỉ câu của KHÁCH, mỗi câu kèm số lượt — bằng chứng phải trỏ đúng số này."""

    return "\n".join(f"[turn {index}] {text}" for index, text in sorted(user_turns.items()))


def classify_input(session_summary: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    lines = [session_summary, "", "Các nhu cầu mua đã biết:"]
    for item in candidates:
        lines.append(
            f"- opportunity_id={item['opportunity_id']} xe={item.get('vehicle_type')} mua_cho={item.get('buyer_for')} "
            f"trang_thai={item.get('status')} slot={item.get('slots')} lan_cuoi={item.get('last_seen_at')}"
        )
    return "\n".join(lines)
