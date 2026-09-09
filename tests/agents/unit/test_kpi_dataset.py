"""[A9-3] Bộ câu hỏi KPI — kiểm hình dạng dữ liệu, không cần chạy graph."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = REPOSITORY_ROOT / "eval" / "datasets" / "kpi_questions.yaml"

VALID_VEHICLE_TYPES = {"CAR", "ELECTRIC_MOTORBIKE"}
VALID_INTENTS = {"ADVISORY", "CATALOG_LOOKUP", "OUT_OF_SCOPE"}


@pytest.fixture(scope="module")
def questions() -> list[dict[str, object]]:
    payload = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    return list(payload["questions"])


def test_the_dataset_has_at_least_fifty_questions(questions: list[dict[str, object]]) -> None:
    assert len(questions) >= 50


def test_every_question_identifier_is_unique(questions: list[dict[str, object]]) -> None:
    duplicates = [key for key, count in Counter(q["id"] for q in questions).items() if count > 1]
    assert duplicates == []


def test_every_question_declares_a_known_vehicle_type(questions: list[dict[str, object]]) -> None:
    unknown = sorted({str(q["vehicle_type"]) for q in questions} - VALID_VEHICLE_TYPES)
    assert unknown == []


def test_every_question_declares_a_known_intent(questions: list[dict[str, object]]) -> None:
    unknown = sorted({str(q["intent"]) for q in questions} - VALID_INTENTS)
    assert unknown == []


def test_no_question_text_is_empty(questions: list[dict[str, object]]) -> None:
    empty = [q["id"] for q in questions if not str(q.get("text", "")).strip()]
    assert empty == []


def test_both_vehicle_branches_are_covered(questions: list[dict[str, object]]) -> None:
    counts = Counter(str(q["vehicle_type"]) for q in questions)
    assert counts["CAR"] >= 10
    assert counts["ELECTRIC_MOTORBIKE"] >= 10


def test_out_of_scope_questions_are_present(questions: list[dict[str, object]]) -> None:
    # Guardrail A6-2 chỉ được nghiệm thu khi bộ kiểm thử có câu ngoài phạm vi
    assert sum(1 for q in questions if q["intent"] == "OUT_OF_SCOPE") >= 3
