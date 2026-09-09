"""Run versioned bottleneck classifier evaluation and write aggregate JSON.

Live usage (paid, explicit opt-in):
AGENT_BOTTLENECK_EVAL_LIVE=1 OPENAI_API_KEY=... uv run python -m scripts.evaluate_bottlenecks --mode live --output /tmp/bottleneck-eval.json
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

import anyio

from eval.bottleneck.loader import DEFAULT_DATASET_PATH, load_bottleneck_dataset
from eval.bottleneck.models import DetectionStatus, EvalLabel, EvalObservation
from eval.bottleneck.reporting import render_json
from eval.bottleneck.runner import run_dataset
from src.agents.adapters.bottleneck_detector import (
    BottleneckDetectorMetrics,
    OpenAIBottleneckDetector,
)
from src.agents.domain.bottleneck_signal import (
    BottleneckDetected,
    BottleneckNone,
    BottleneckUnavailable,
)
from src.agents.prompts.bottleneck_detection import BOTTLENECK_DETECTION_PROMPT_VERSION
from src.config import get_settings

LIVE_ENABLE_VARIABLE = "AGENT_BOTTLENECK_EVAL_LIVE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def live_eval_enabled(environment: dict[str, str] | None = None) -> bool:
    source = environment if environment is not None else os.environ
    return source.get(LIVE_ENABLE_VARIABLE, "").strip().lower() in _TRUTHY


class _LiveDetector:
    def __init__(self) -> None:
        self.model = get_settings().model_name
        self._metrics = BottleneckDetectorMetrics()
        self._detector = OpenAIBottleneckDetector(metrics=self._metrics)

    async def evaluate(self, case_id: str, text: str, expected: EvalLabel) -> EvalObservation:
        result = await self._detector.detect(text)
        event = self._metrics.events[-1]
        match result:
            case BottleneckDetected(label=label):
                predicted = EvalLabel(label.value)
                status = DetectionStatus.DETECTED
                invalid = False
            case BottleneckNone():
                predicted = EvalLabel.NONE
                status = DetectionStatus.NONE
                invalid = False
            case BottleneckUnavailable():
                predicted = None
                status = DetectionStatus.UNAVAILABLE
                invalid = True
            case unreachable:
                assert_never(unreachable)
        return EvalObservation(
            case_id=case_id,
            expected_label=expected,
            predicted_label=predicted,
            status=status,
            latency_ms=event.latency_ms,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
            invalid_payload=invalid,
        )


class _SeededFailureDetector:
    async def evaluate(self, case_id: str, text: str, expected: EvalLabel) -> EvalObservation:
        return EvalObservation(
            case_id=case_id,
            expected_label=expected,
            predicted_label=EvalLabel.NONE,
            status=DetectionStatus.NONE,
            latency_ms=3_001,
            input_tokens=10,
            output_tokens=2,
            invalid_payload=case_id == "P01",
        )


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--mode", choices=("live", "seeded-failure"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    dataset = load_bottleneck_dataset(args.dataset)
    match args.mode:
        case "live":
            if not live_eval_enabled():
                raise SystemExit(f"live eval locked; set {LIVE_ENABLE_VARIABLE}=1 to allow paid calls")
            detector = _LiveDetector()
            model = detector.model
        case "seeded-failure":
            detector = _SeededFailureDetector()
            model = "seeded-failure"
        case unreachable:
            assert_never(unreachable)
    report = await run_dataset(
        dataset,
        detector,
        model=model,
        prompt_version=BOTTLENECK_DETECTION_PROMPT_VERSION,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_json(report), encoding="utf-8")
    return 0 if report.gates.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    return anyio.run(_run, _arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
