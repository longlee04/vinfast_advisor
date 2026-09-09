"""Load versioned bottleneck classifier datasets."""

from pathlib import Path

from eval.bottleneck.models import BottleneckDataset

DEFAULT_DATASET_PATH = Path(__file__).parents[1] / "datasets" / "bottleneck_detection.json"


def load_bottleneck_dataset(path: Path = DEFAULT_DATASET_PATH) -> BottleneckDataset:
    return BottleneckDataset.model_validate_json(path.read_text(encoding="utf-8"))
