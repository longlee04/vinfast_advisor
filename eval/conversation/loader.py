"""Dataset loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

from eval.conversation.models import ConversationDataset

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "slot_conversations.json"
#: Hợp đồng golden của Ngọc (nhánh dev/ngoc, "kiến trúc mới"): giữ NGUYÊN VĂN kỳ
#: vọng của cô ấy, để riêng — KHÔNG đi qua runner offline của develop (hướng 1,
#: Sếp + Ngọc chốt 2026-08-28). Chỉ `tests/agents/unit/eval/test_architecture_golden.py` đọc.
ARCHITECTURE_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "datasets" / "architecture_golden.json"


def load_conversation_dataset(path: Path = DEFAULT_DATASET_PATH) -> ConversationDataset:
    """Load a UTF-8 JSON dataset and validate every scenario with Pydantic."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return ConversationDataset.model_validate(payload)


def load_architecture_golden_dataset(path: Path = ARCHITECTURE_GOLDEN_PATH) -> ConversationDataset:
    """Load the architecture golden contract dataset (kept apart from the offline runner)."""

    return load_conversation_dataset(path)
