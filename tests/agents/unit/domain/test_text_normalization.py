from __future__ import annotations

import unicodedata

from src.agents.domain.text_normalization import (
    changed_tokens,
    digits_from_words,
    normalize,
    squash,
    strip_diacritics,
    token_change_ratio,
    tokenize,
)


def test_strip_diacritics_handles_every_vietnamese_tone() -> None:
    assert strip_diacritics("thông tin xe") == "thong tin xe"
    assert strip_diacritics("Đà Nẵng") == "Da Nang"
    assert strip_diacritics("nghệ an") == "nghe an"


def test_precomposed_and_decomposed_forms_normalize_to_the_same_string() -> None:
    """Cùng một chữ gõ từ hai bàn phím phải cho cùng một dạng so khớp.

    "ế" có hai cách mã hoá Unicode; nếu chuẩn hoá phụ thuộc cách mã hoá thì hai
    khách gõ cùng một câu sẽ nhận hai kết quả nhận diện khác nhau.
    """

    precomposed = unicodedata.normalize("NFC", "xe điện")
    decomposed = unicodedata.normalize("NFD", "xe điện")

    assert precomposed != decomposed
    assert normalize(precomposed) == normalize(decomposed) == "xe dien"


def test_normalize_drops_punctuation_so_it_does_not_split_tokens() -> None:
    assert normalize("VF5, giá bao nhiêu?") == "vf5 gia bao nhieu"
    assert tokenize("VF5, giá bao nhiêu?") == ["vf5", "gia", "bao", "nhieu"]


def test_normalize_returns_empty_string_for_empty_input() -> None:
    assert normalize("") == ""
    assert normalize("   ") == ""
    assert tokenize("") == []


def test_squash_matches_the_catalog_reader_convention() -> None:
    """Cùng quy ước với `adapters/catalog_reader._squash`: "VF 3" ≡ "vf3"."""

    assert squash("VF 3") == squash("vf3") == "vf3"


def test_digits_from_words_only_converts_standalone_tokens() -> None:
    assert digits_from_words("vf năm") == "vf 5"
    # "nam" nằm trong "nam giới" và "chin" nằm trong "chính sách" — thay theo
    # chuỗi con sẽ phá cả hai câu đó.
    assert digits_from_words("chính sách pin") == "chinh sach pin"


def test_changed_tokens_measures_on_the_normalized_form() -> None:
    """Thêm dấu là sửa chính tả, không phải thêm nội dung."""

    assert changed_tokens("thong tin xe", "thông tin xe") == ()
    assert changed_tokens("tho ti x", "thông tin xe") == ("thong", "tin", "xe")


def test_token_change_ratio_is_zero_for_empty_original() -> None:
    assert token_change_ratio("", "bất cứ gì") == 0.0


def test_token_change_ratio_counts_new_tokens_against_the_original_length() -> None:
    """Tách "vf5" thành "VF 5" sinh hai token mới trên bốn token gốc.

    Con số này CHỈ dùng để báo cáo/audit. Guard của Lớp 1 KHÔNG dùng nó — xem
    `domain/rewrite.MAX_TOKEN_CHANGE_RATIO`: một bản sửa chính tả nặng đổi gần
    hết token, nên đếm token đổi sẽ chặn đúng ca cần sửa.
    """

    assert token_change_ratio("vf5 gia bao nhieu", "VF 5 giá bao nhiêu") == 0.5
