"""[A6-2] Adapter cho phân loại phạm vi và nhật ký `out_of_scope_log`."""

from __future__ import annotations

from uuid import UUID

from src.agents.domain.values import ScopeLabel
from src.agents.turn_context import current_session_id


class LlmScopeClassifier:
    """Gọi LLM và chuẩn hoá chuỗi trả về thành một nhãn đóng."""

    def __init__(self, llm) -> None:
        self._llm = llm

    async def classify_scope(self, *, prompt: str) -> str:
        """Chuỗi lạ trả `IN_SCOPE`: chặn nhầm khách tệ hơn cho qua một câu hợp lệ."""

        raw = (await self._llm.synthesize(prompt=prompt)).strip().upper()
        return raw if raw in {label.value for label in ScopeLabel} else ScopeLabel.IN_SCOPE.value


class ContextVarScopeSessionContext:
    """Lấy `session_id` của lượt đang chạy từ `turn_context`."""

    def current_session_id(self) -> UUID:
        session_id = current_session_id()
        if session_id is None:
            raise RuntimeError("scope classification chạy ngoài một lượt hội thoại")
        return session_id


# Ghi `out_of_scope_log` không còn ở đây: `SqlAlchemyScopeLogUnitOfWork`
# (`src/agents/adapters/unit_of_work.py`) là đường ghi DUY NHẤT — mở session
# mới và commit ở mỗi lần `log()`, thay vì dùng chung một `AsyncSession` cho
# toàn app (PRD 8.5 — 50 phiên đồng thời). Từng có một `SqlAlchemyScopeLogAdapter`
# ở đây chỉ `flush()` mà không `commit()`; đã xoá để tránh hai đường ghi cùng
# một bảng lệch nhau âm thầm.
