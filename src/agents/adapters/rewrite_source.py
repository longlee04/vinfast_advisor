"""[Lớp 1] Adapter gọi LLM cho bước sửa lỗi gõ, và chuẩn hoá chuỗi trả về.

Đi qua `LLMPort.synthesize` chứ không thêm method vào `LLMPort` — Protocol đó
đóng băng từ Ngày 0 (§2.2 `docs/team_split.md`). `LlmScopeClassifier` trong
`adapters/scope_source.py` đã đi đúng con đường này cho A6-2; đây là bản thứ hai
của cùng khuôn mẫu, nên cũng chịu trách nhiệm giống hệt: **chuỗi lạ không được
làm chết lượt**.

Khác `LlmScopeClassifier` ở chiều an toàn khi hỏng: bộ phân loại phạm vi trả
`IN_SCOPE` (cho qua) vì chặn nhầm khách tệ hơn bỏ sót; ở đây trả `None` (bỏ
rewrite) vì dùng một bản rewrite hỏng còn tệ hơn dùng câu gốc — câu gốc luôn là
thứ khách thật sự đã viết.
"""

from __future__ import annotations

import json
import re
from typing import Any, Final, Protocol

from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.adapters.rewrite")

#: LLM hay bọc JSON trong khối mã dù đã dặn không. Gỡ rào thay vì bỏ cả câu trả
#: lời: nội dung bên trong vẫn đúng, chỉ thừa ba dấu backtick.
_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)

#: Cứu vãn khi mô hình viết thêm lời rào trước/sau JSON.
_OBJECT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)


class TextRewriterPort(Protocol):
    """Cổng hẹp: nhận prompt, trả chuỗi thô của mô hình."""

    async def rewrite(self, *, prompt: str) -> str: ...


class LlmTextRewriter:
    """Gọi LLM qua `synthesize` và trả nguyên văn chuỗi mô hình viết ra."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def rewrite(self, *, prompt: str) -> str:
        return await self._llm.synthesize(prompt=prompt)


def parse_rewrite_payload(raw: str) -> tuple[str, float, tuple[str, ...]] | None:
    """Đọc `{rewritten, confidence, changed_tokens}`; hỏng → `None`.

    Trả `None` chứ không raise và cũng không dựng bản mặc định: một payload hỏng
    nghĩa là ta KHÔNG biết mô hình định nói gì, và đoán tiếp từ chỗ đó là đúng
    thứ Lớp 1 bị cấm làm. `None` đưa lượt về dùng câu gốc — luôn an toàn.
    """

    if not raw or not raw.strip():
        return None
    text = raw.strip()
    fenced = _FENCE_PATTERN.match(text)
    if fenced is not None:
        text = fenced.group("body").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        found = _OBJECT_PATTERN.search(text)
        if found is None:
            logger.warning("rewrite: khong doc duoc JSON tu chuoi dai %d ky tu", len(raw))
            return None
        try:
            payload = json.loads(found.group(0))
        except json.JSONDecodeError:
            logger.warning("rewrite: JSON hong, bo qua ban rewrite")
            return None
    if not isinstance(payload, dict):
        return None

    rewritten = payload.get("rewritten")
    if not isinstance(rewritten, str):
        return None
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        # `bool` chặn tường minh: `isinstance(True, int)` là `True` trong Python,
        # và một cờ boolean lọt vào ô confidence sẽ được đọc thành 1.0 — cùng bẫy
        # mà `domain/quote_risk._is_usable_score` đã phải chặn.
        return None
    score = max(0.0, min(1.0, float(confidence)))
    raw_tokens = payload.get("changed_tokens")
    tokens = tuple(item for item in (raw_tokens or ()) if isinstance(item, str))
    return rewritten, score, tokens


__all__ = ["LlmTextRewriter", "TextRewriterPort", "parse_rewrite_payload"]
