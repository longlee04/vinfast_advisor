"""Unit tests for Vietnamese number-word parser (T2)."""

from __future__ import annotations

import pytest

from src.agents.domain.number_word_parser import parse_amount_from_folded


@pytest.mark.parametrize(
    ("folded", "expected"),
    [
        ("ba tram trieu", 300_000_000),
        ("mot tram trieu", 100_000_000),
        ("chin tram trieu", 900_000_000),
        ("mot ty", 1_000_000_000),
        ("mot ty hai tram trieu", 1_200_000_000),
        ("hai muoi mot trieu", 21_000_000),
        ("muoi lam trieu", 15_000_000),
        ("muoi trieu", 10_000_000),
        ("nua ty", 500_000_000),
        ("ba tram nghin", 300_000),
        ("hai trieu", 2_000_000),
        ("bon muoi lam trieu", 45_000_000),
        ("tram trieu", 100_000_000),
        ("ba tram trieu dong", 300_000_000),
        ("mot ty hai tram trieu dong", 1_200_000_000),
    ],
)
def test_parses_clean_amounts(folded: str, expected: int) -> None:
    assert parse_amount_from_folded(folded) == expected


@pytest.mark.parametrize(
    "folded",
    [
        "",  # rỗng
        "xe o to",  # không phải số
        "ba dua chau",  # false-positive: "ba" = 3 nhưng không phải tiền
        "ba tram trieu cung ok",  # token lạ cuối → fail-closed
        "mot ty hai tram",  # nhóm cuối thiếu scale → mơ hồ
        "hai tram trieu ty",  # scale tăng dần (trieu rồi ty) → vô lý
        "mot ty mot tram trieu nghin",  # scale giảm rồi nghin (lệch thứ tự)
        "bon tram lam muoi trieu",  # "lam muoi" không hợp lệ
        "chin chin trieu",  # "chin chin" không phải grammar
    ],
)
def test_rejects_outside_grammar(folded: str) -> None:
    assert parse_amount_from_folded(folded) is None
