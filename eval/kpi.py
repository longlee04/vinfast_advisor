"""[A9-3] Ba KPI baseline — thuần Python, tính từ kết quả một lần chạy.

- **KPI-1 Factual Accuracy** — độ chính xác sự kiện.
- **KPI-2 Unwarned Over-Budget Recommendation Rate** — tỉ lệ đề xuất vượt ngân
  sách mà không kèm cảnh báo.
- **KPI-4 Required-Slot Completion** — mức hoàn thành slot bắt buộc.

Không đủ dữ liệu thì trả `None` ("không tính được"), **không** trả 0 hay 1: một
báo cáo KPI hoàn hảo dựng trên tập rỗng còn nguy hiểm hơn không có báo cáo.

Ngưỡng đạt của ba KPI chưa được chốt — xem `docs/docs_buildagent_long/nghiemthu/A9-3.md`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class TurnOutcome:
    """Kết quả một lượt chạy, đủ để tính cả ba KPI."""

    question_id: str
    every_number_has_evidence: bool
    recommended_over_budget: bool
    over_budget_warned: bool
    required_slots_asked: int
    required_slots_filled: int


def factual_accuracy(outcomes: Sequence[TurnOutcome]) -> float | None:
    """KPI-1 — tỉ lệ câu trả lời mà mọi con số đều truy được về bằng chứng."""
    if not outcomes:
        return None
    sourced = sum(1 for outcome in outcomes if outcome.every_number_has_evidence)
    return sourced / len(outcomes)


def unwarned_over_budget_rate(outcomes: Sequence[TurnOutcome]) -> float | None:
    """KPI-2 — trong các lượt **có đề xuất vượt ngân sách**, bao nhiêu phần không cảnh báo.

    Mẫu số là số đề xuất vượt ngân sách, không phải tổng số câu hỏi: chia cho
    tổng số câu sẽ làm KPI đẹp lên chỉ vì bộ kiểm thử có nhiều câu vô hại.
    """
    over_budget = [outcome for outcome in outcomes if outcome.recommended_over_budget]
    if not over_budget:
        return None
    unwarned = sum(1 for outcome in over_budget if not outcome.over_budget_warned)
    return unwarned / len(over_budget)


def required_slot_completion(outcomes: Sequence[TurnOutcome]) -> float | None:
    """KPI-4 — số slot bắt buộc đã thu được trên tổng số slot bắt buộc đã hỏi."""
    asked = sum(outcome.required_slots_asked for outcome in outcomes)
    filled = sum(outcome.required_slots_filled for outcome in outcomes)
    if filled > asked:
        raise ValueError(f"slot đã thu ({filled}) nhiều hơn slot đã hỏi ({asked})")
    if asked == 0:
        return None
    return filled / asked
