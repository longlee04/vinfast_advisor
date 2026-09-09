"""Nhận diện câu "còn tính năng nào khác không" — T7, Sếp 2026-08-21."""

from __future__ import annotations

import pytest

from src.agents.domain.feature_followup import wants_more_features


@pytest.mark.parametrize(
    "message",
    [
        "có tính năng nào khác không em",
        "còn tính năng nào khác không",
        "còn gì khác không em",
        "con tinh nang nao khac khong",
        "tính năng nào khác",
        "Tính Năng Nào Khác",
    ],
)
def test_recognizes_the_follow_up(message: str) -> None:
    assert wants_more_features(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "anh có khoảng 500 triệu",
        "gia đình anh 4 người",
        "khoá chống trộm thì sao",
        "còn xe nào khác không",
        "",
    ],
)
def test_does_not_misfire_on_unrelated_messages(message: str) -> None:
    assert wants_more_features(message) is False
