"""Run the four-axis turn-understanding evaluation and emit Markdown or JSON.

Offline mặc định (fixture, không gọi mạng). Chạy mô hình thật chỉ khi đặt
`RUN_AGENT_EVAL=1` — secrets đọc từ env, không commit, không ghi artifact nào
vào version control.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.turn_axes.loader import (  # noqa: E402
    DEFAULT_DATASET_PATH,
    load_turn_axes_dataset,
)
from eval.turn_axes.metrics import calculate_metrics  # noqa: E402
from eval.turn_axes.models import TurnAxesDataset, TurnAxesRun  # noqa: E402
from eval.turn_axes.reporting import render_json, render_markdown  # noqa: E402
from scripts.turn_axes_runner import run_turn_axes_dataset  # noqa: E402

LIVE_ENABLE_VARIABLE = "RUN_AGENT_EVAL"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def live_eval_enabled(environment: dict[str, str] | None = None) -> bool:
    """Allow paid live evaluation only after explicit environment opt-in."""

    source = environment if environment is not None else os.environ
    return source.get(LIVE_ENABLE_VARIABLE, "").strip().lower() in _TRUTHY


def disable_live_tracing(environment: dict[str, str] | None = None) -> None:
    """Prevent eval probes from failing because an external tracing project is unavailable."""

    target = environment if environment is not None else os.environ
    target["LANGCHAIN_TRACING_V2"] = "false"
    target["LANGSMITH_TRACING"] = "false"


def select_scenarios(dataset: TurnAxesDataset, scenario_ids: list[str] | None) -> TurnAxesDataset:
    """Return the requested deterministic subset while preserving dataset order."""

    if not scenario_ids:
        return dataset
    requested = set(scenario_ids)
    known = {scenario.id for scenario in dataset.scenarios}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"unknown scenario id: {', '.join(unknown)}")
    return dataset.model_copy(
        update={"scenarios": [scenario for scenario in dataset.scenarios if scenario.id in requested]}
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Run one scenario ID; repeat this option to select a critical subset.",
    )
    parser.add_argument("--repeat", type=int, default=1)
    return parser.parse_args()


def _attach_metadata(output: str, *, output_format: str, metadata: dict[str, object]) -> str:
    if output_format == "json":
        payload = json.loads(output)
        payload["metadata"] = metadata
        return json.dumps(payload, ensure_ascii=False, indent=2)
    lines = ["# Evaluation run metadata", ""]
    lines.extend(f"- {key}: {value}" for key, value in metadata.items())
    return "\n".join(lines) + "\n\n" + output


async def _main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _arguments()
    disable_live_tracing()
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")
    live_llm = None
    model_name = "scripted fixtures"
    if args.mode == "live":
        if not live_eval_enabled():
            raise SystemExit(f"live eval bị khóa; đặt {LIVE_ENABLE_VARIABLE}=1 nếu chấp nhận gọi LLM thật")
        from src.agents.adapters.llm import OpenAIChatAdapter

        live_llm = OpenAIChatAdapter()
        model_name = live_llm.model_name

    try:
        dataset = select_scenarios(load_turn_axes_dataset(args.dataset), args.scenario_ids)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    scenarios = []
    for _ in range(args.repeat):
        current = await run_turn_axes_dataset(dataset, live_llm=live_llm)
        scenarios.extend(current.scenarios)
    run = TurnAxesRun(scenarios=scenarios)
    metrics = calculate_metrics(run)
    output = render_json(run, metrics) if args.format == "json" else render_markdown(run, metrics)
    output = _attach_metadata(
        output,
        output_format=args.format,
        metadata={
            "mode": args.mode,
            "model": model_name,
            "temperature": 0,
            "run_count": args.repeat,
            "scenario_ids": ", ".join(scenario.id for scenario in dataset.scenarios),
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    if args.output is None:
        print(output, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return 0 if metrics.scenario_pass_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
