"""[A9-3] Cổng chấm điểm — LLM thật cắm vào đây, test cắm fake vào cùng chỗ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CriterionScores:
    """Ba tiêu chí chấm, mỗi tiêu chí trong khoảng [0, 1].

    Ba tiêu chí lấy đúng theo A9-3: đúng trọng tâm câu hỏi, giọng tư vấn viên,
    đủ ý.
    """

    on_topic: float
    advisor_voice: float
    complete: float


class JudgePort(Protocol):
    """Chấm một cặp (câu hỏi, câu trả lời)."""

    async def score(self, question: str, answer: str) -> CriterionScores: ...
