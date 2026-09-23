"""Dataset 30 câu + bộ so sánh của `scripts/agent_eval` (plan agent-migration Bước 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.agent_eval import compare_runs, load_cases, regression_ids, render_markdown

DATASET = Path(__file__).resolve().parents[3] / "eval" / "datasets" / "agent_fallback_cases.json"


def test_dataset_du_30_cau_va_co_ky_vong() -> None:
    cases = load_cases(DATASET)
    assert len(cases) == 30
    assert [case["id"] for case in cases] == list(range(1, 31))
    assert all(case["message"].strip() and case["ky_vong"].strip() for case in cases)
    assert all(isinstance(case["setup"], list) for case in cases)


def test_du_9_cau_regression_chan_phat_hanh() -> None:
    """§5.1: câu 16, 17, 23-29 là bộ regression cốt lõi — không thương lượng."""

    assert regression_ids(load_cases(DATASET)) == [16, 17, 23, 24, 25, 26, 27, 28, 29]


def test_case_thieu_khoa_thi_no_ngay(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"cases": [{"id": 1, "message": "x"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="thieu khoa"):
        load_cases(bad)


def test_compare_runs_bat_cau_doi_chu_va_latency() -> None:
    off = {1: {"answer": "a", "latency_s": 2.0}, 2: {"answer": "b", "latency_s": 4.0}}
    on = {1: {"answer": "a", "latency_s": 3.0}, 2: {"answer": "khac", "latency_s": 9.0, "agent_used": True}}
    diff = compare_runs(off, on)
    assert diff["changed_ids"] == [2]
    assert diff["agent_ids"] == [2]
    assert diff["latency_off"]["p50"] == 3.0
    assert diff["latency_on"]["p95"] == 9.0


def test_bao_cao_neu_ro_so_case_regression_bi_doi() -> None:
    cases = load_cases(DATASET)
    off = {case["id"]: {"answer": "cu", "latency_s": 1.0} for case in cases}
    on = {case["id"]: {"answer": "moi" if case["id"] == 16 else "cu", "latency_s": 1.0} for case in cases}
    report = {
        "run_at": "2026-09-23T00:00:00+00:00",
        "base_url": "http://x/api/v1",
        "dataset": str(DATASET),
        "cases": cases,
        "regression_ids": regression_ids(cases),
        "off": off,
        "on": on,
        "ok_off": 30,
        "ok_on": 30,
        "comparison": compare_runs(off, on),
    }
    text = render_markdown(report)
    assert "**1**" in text  # đúng một case regression bị đổi
    assert "REGRESSION" in text
