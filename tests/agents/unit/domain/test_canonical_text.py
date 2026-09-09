"""CanonicalText — ba dạng chuẩn hoá + bộ so khớp keyword dùng chung."""

from __future__ import annotations

import pytest

from src.agents.domain.canonical_text import (
    CanonicalText,
    MatchTier,
    build_canonical_text,
    compile_keyword_variants,
    match_tier,
)


def test_build_canonical_text_produces_three_forms() -> None:
    canonical = build_canonical_text("Xe của tôi đang cháy!!")

    assert canonical.original == "xe của tôi đang cháy"
    assert canonical.folded == "xe cua toi dang chay"
    assert canonical.leet_decoded == "xe cua toi dang chay"


def test_leet_decoded_maps_digits_to_similar_letters() -> None:
    canonical = build_canonical_text("b0c ch4y rồi ạ")

    assert canonical.leet_decoded == "boc chay roi a"
    assert canonical.folded == "b0c ch4y roi a"


def test_leet_decoded_keeps_vehicle_digits_intact_in_folded() -> None:
    """Entity path dùng `folded` (giữ số) — "vf5" không thành "vfs"."""

    canonical = build_canonical_text("xe vf5 giá bao nhiêu")

    assert canonical.folded == "xe vf5 gia bao nhieu"
    assert canonical.leet_decoded == "xe vfs gia bao nhieu"


def test_match_tier_original_beats_folded() -> None:
    canonical = build_canonical_text("xe của tôi đang cháy")

    assert match_tier(canonical, "đang cháy") is MatchTier.ORIGINAL
    assert match_tier(canonical, "dang chay") is MatchTier.FOLDED


def test_match_tier_folded_only_when_original_has_diacritics() -> None:
    """ "đang chạy" có dấu: needle có dấu không khớp original, chỉ folded."""

    canonical = build_canonical_text("xe của tôi đang chạy")

    assert match_tier(canonical, "đang cháy") is MatchTier.NONE
    assert match_tier(canonical, "dang chay") is MatchTier.FOLDED


def test_match_tier_original_on_diacritic_free_input() -> None:
    """Không dấu: needle folded khớp thẳng original (original không dấu)."""

    canonical = build_canonical_text("xe cua toi dang chay")

    assert match_tier(canonical, "dang chay") is MatchTier.ORIGINAL


def test_match_tier_leet_catches_stylized_keyword() -> None:
    canonical = build_canonical_text("xe t0i b0c ch4y")

    assert match_tier(canonical, "boc chay") is MatchTier.LEET


def test_match_tier_word_boundary_not_substring() -> None:
    """ "chay" không được khớp khi dính vào từ khác — ranh giới từ."""

    canonical = build_canonical_text("xe cua toi chaytot")

    assert match_tier(canonical, "chay") is MatchTier.NONE
    assert match_tier(canonical, "chay tot") is MatchTier.NONE


def test_match_tier_none_when_absent() -> None:
    canonical = build_canonical_text("xe của tôi hết pin")

    assert match_tier(canonical, "mat phanh") is MatchTier.NONE


def test_compile_keyword_variants_folds_and_dedupes() -> None:
    variants = compile_keyword_variants(("đang cháy", "dang chay", "bốc cháy"))

    assert variants == ("đang cháy", "dang chay", "bốc cháy", "boc chay")


def test_compile_keyword_variants_drops_empty() -> None:
    assert compile_keyword_variants(("", "   ", "boc chay")) == ("boc chay",)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "!!!",
        "🚗🔥",
        "xe 123 !@# $%^",
        "Xe Đà Nẵng — VF 9 (màu ế)",
    ],
)
def test_build_canonical_text_handles_malformed_input(text: str) -> None:
    canonical = build_canonical_text(text)

    assert isinstance(canonical.original, str)
    assert isinstance(canonical.folded, str)
    assert isinstance(canonical.leet_decoded, str)
    assert match_tier(canonical, "boc chay") is MatchTier.NONE


def test_build_canonical_text_none_safe() -> None:
    canonical = build_canonical_text(None)  # type: ignore[arg-type]

    assert canonical == CanonicalText(original="", folded="", leet_decoded="")
