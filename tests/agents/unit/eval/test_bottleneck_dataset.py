"""Versioned bottleneck dataset contract tests."""

from collections import Counter

import pytest
from pydantic import ValidationError

from eval.bottleneck.loader import load_bottleneck_dataset
from eval.bottleneck.models import BottleneckCase, EvalLabel


def test_v1_dataset_is_balanced_grouped_and_keeps_context_separate() -> None:
    # Given / When
    dataset = load_bottleneck_dataset()
    labels = Counter(case.expected_label for case in dataset.cases)
    groups = {group for case in dataset.cases for group in case.groups}

    # Then
    assert dataset.version == 1
    assert len(dataset.cases) >= 50
    assert all(labels[label] >= 10 for label in EvalLabel)
    assert {"paraphrase", "neutral_after_recommendation", "ambiguous"} <= groups
    assert any(case.eligible and case.anchor for case in dataset.cases)
    assert any(not case.eligible and case.expected_label is EvalLabel.NONE for case in dataset.cases)


def test_case_rejects_anchor_without_eligibility() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        BottleneckCase(
            id="invalid-anchor",
            text="Không liên quan",
            expected_label=EvalLabel.NONE,
            eligible=False,
            anchor="turn-1",
            groups=("ambiguous",),
        )
