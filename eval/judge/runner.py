"""[A9-3] Chạy judge trên một bộ câu hỏi — mặc định TẮT.

Bật bằng biến môi trường `AGENT_EVAL_JUDGE=1`. Mặc định tắt vì judge tốn một lần
gọi LLM cho mỗi câu; bật nhầm trong CI là tốn tiền im lặng.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from eval.judge.ports import CriterionScores, JudgePort
from eval.judge.scoring import average_score

ENABLE_VARIABLE = "AGENT_EVAL_JUDGE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def judge_enabled(environment: dict[str, str] | None = None) -> bool:
    """`True` chỉ khi biến môi trường mang một giá trị bật rõ ràng."""
    source = environment if environment is not None else os.environ
    return source.get(ENABLE_VARIABLE, "").strip().lower() in _TRUTHY


@dataclass(frozen=True)
class JudgeReport:
    """Điểm trung bình từng câu, và chi tiết ba tiêu chí."""

    scores: dict[str, float] = field(default_factory=dict)
    details: dict[str, CriterionScores] = field(default_factory=dict)

    @property
    def mean_score(self) -> float | None:
        """Điểm trung bình toàn bộ; `None` khi chưa chấm câu nào."""
        if not self.scores:
            return None
        return sum(self.scores.values()) / len(self.scores)


async def run_judge(
    questions: dict[str, str], answers: dict[str, str], judge: JudgePort
) -> JudgeReport:
    """Chấm từng câu **có câu trả lời**; câu không có đáp án không tốn lần gọi nào."""
    scores: dict[str, float] = {}
    details: dict[str, CriterionScores] = {}
    for question_id, question in questions.items():
        answer = answers.get(question_id)
        if answer is None:
            continue
        criterion_scores = await judge.score(question, answer)
        details[question_id] = criterion_scores
        scores[question_id] = average_score(criterion_scores)
    return JudgeReport(scores=scores, details=details)
