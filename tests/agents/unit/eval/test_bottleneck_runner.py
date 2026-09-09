"""Offline runner and safe live-command tests for bottleneck eval."""

import json
from pathlib import Path

import pytest

from eval.bottleneck.loader import load_bottleneck_dataset
from eval.bottleneck.models import EvalLabel, EvalObservation
from eval.bottleneck.runner import run_dataset
from scripts.evaluate_bottlenecks import live_eval_enabled, main


class _PerfectDetector:
    async def evaluate(self, case_id: str, text: str, expected: EvalLabel) -> EvalObservation:
        return EvalObservation(
            case_id=case_id,
            expected_label=expected,
            predicted_label=expected,
            status="NONE" if expected is EvalLabel.NONE else "DETECTED",
            latency_ms=10,
            input_tokens=10,
            output_tokens=2,
            invalid_payload=False,
        )


@pytest.mark.asyncio
async def test_offline_runner_passes_full_dataset_without_provider() -> None:
    # Given / When
    report = await run_dataset(load_bottleneck_dataset(), _PerfectDetector())

    # Then
    assert report.metrics.case_count >= 50
    assert report.gates.passed is True
    assert report.metrics.macro_f1 == 1.0
    assert report.metrics.per_label[EvalLabel.PRICE].precision == 1.0


@pytest.mark.parametrize(
    ("environment", "expected"),
    [({}, False), ({"AGENT_BOTTLENECK_EVAL_LIVE": "false"}, False), ({"AGENT_BOTTLENECK_EVAL_LIVE": "1"}, True)],
)
def test_live_command_requires_explicit_opt_in(environment: dict[str, str], expected: bool) -> None:
    assert live_eval_enabled(environment) is expected


def test_seeded_failing_report_writes_safe_json_and_exits_nonzero(tmp_path: Path) -> None:
    # Given
    output = tmp_path / "report.json"

    # When
    exit_code = main(["--mode", "seeded-failure", "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    # Then
    assert exit_code == 1
    assert payload["gates"]["passed"] is False
    assert "text" not in output.read_text(encoding="utf-8")
    assert "api_key" not in output.read_text(encoding="utf-8")
