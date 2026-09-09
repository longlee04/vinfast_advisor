"""[A9-3] Gộp điểm và tìm câu tụt điểm — thuần Python, không LLM, không I/O."""

from __future__ import annotations

from eval.judge.ports import CriterionScores

#: Chênh lệch nhỏ hơn ngưỡng này coi như nhiễu chấm điểm, không phải tụt điểm.
REGRESSION_TOLERANCE = 1e-9


def average_score(scores: CriterionScores) -> float:
    """Điểm trung bình của ba tiêu chí."""
    return (scores.on_topic + scores.advisor_voice + scores.complete) / 3


def regressions(previous: dict[str, float], current: dict[str, float]) -> list[str]:
    """Câu nào điểm thấp hơn lần chạy trước.

    Câu mới (không có ở lần trước) **không** tính là tụt điểm — nếu tính, thêm
    câu vào bộ kiểm thử sẽ luôn báo hồi quy giả.
    """
    dropped = [
        question_id
        for question_id, score in current.items()
        if question_id in previous and score < previous[question_id] - REGRESSION_TOLERANCE
    ]
    return sorted(dropped)
