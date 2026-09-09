"""Thống kê vệt quyết định — số liệu màn admin đọc để hiệu chuẩn ngưỡng.

Sếp 2026-08-26. Đo trên log thật ngày 26/08 cho thấy **26/27 lượt `intent=None`**
và điểm chỉ rơi vào ba giá trị (0.0 / 0.2 / 1.0). Nên con số đáng nhìn nhất
KHÔNG phải ngưỡng, mà là **độ phủ**: bao nhiêu phần trăm lượt Lớp 3 nhận ra được
một ý định. Hiệu chuẩn `0.85/0.60` khi độ phủ 4% là chỉnh nhầm chỗ.
"""

from __future__ import annotations

from src.agents.services.operations.turn_trace import summarize_traces


def _row(intent: str | None, confidence: float | None, tier: str | None) -> dict:
    return {"intent_hint": intent, "confidence": confidence, "tier": tier}


def test_coverage_is_the_share_of_turns_that_produced_an_intent() -> None:
    rows = [
        _row("CATALOG_LOOKUP", 1.0, "AUTO"),
        _row(None, 0.2, "AUTO"),
        _row(None, 0.0, "AUTO"),
        _row(None, 1.0, "AUTO"),
    ]

    summary = summarize_traces(rows)

    assert summary.total == 4
    assert summary.with_intent == 1
    assert summary.coverage_pct == 25.0


def test_tier_counts_show_how_often_the_gate_would_actually_stop_a_turn() -> None:
    rows = [_row("A", 0.9, "AUTO"), _row("B", 0.7, "CONFIRM"), _row("C", 0.5, "CLARIFY"), _row("D", 0.8, "CONFIRM")]

    summary = summarize_traces(rows)

    assert summary.tier_counts == {"AUTO": 1, "CONFIRM": 2, "CLARIFY": 1}


def test_histogram_buckets_expose_the_gap_between_the_thresholds() -> None:
    """Dải [0.6, 0.85) là toàn bộ vùng `CONFIRM`. Rỗng nghĩa là ngưỡng vô dụng —
    đúng thứ đo được trên prod hôm nay."""

    rows = [_row(None, 0.0, "AUTO"), _row(None, 0.2, "AUTO"), _row("A", 1.0, "AUTO"), _row("B", 0.83, "CONFIRM")]

    summary = summarize_traces(rows)

    assert summary.histogram["0.0-0.2"] == 1
    assert summary.histogram["0.2-0.4"] == 1
    assert summary.histogram["0.6-0.8"] == 0
    assert summary.histogram["0.8-1.0"] == 2


def test_turns_without_a_confidence_never_distort_the_histogram() -> None:
    """Lượt không qua Lớp 4 (lỗi, hoặc chưa nối) có `confidence=None`.

    Đếm chúng thành 0.0 sẽ dựng một cột giả ở đáy và làm cả biểu đồ nói dối.
    """

    summary = summarize_traces([_row(None, None, None), _row("A", 0.9, "AUTO")])

    assert summary.total == 2
    assert sum(summary.histogram.values()) == 1


def test_an_empty_window_reports_zero_not_a_crash() -> None:
    summary = summarize_traces([])

    assert summary.total == 0
    assert summary.coverage_pct == 0.0
    assert summary.tier_counts == {}
