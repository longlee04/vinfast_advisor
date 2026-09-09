"""Dataset loading and validation for the four-axis turn-understanding eval."""

from __future__ import annotations

import json
from pathlib import Path

from eval.turn_axes.models import TurnAxesDataset

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "turn_axes.json"


def load_turn_axes_dataset(path: Path = DEFAULT_DATASET_PATH) -> TurnAxesDataset:
    """Load a UTF-8 JSON dataset and validate every scenario with Pydantic."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return TurnAxesDataset.model_validate(payload)
