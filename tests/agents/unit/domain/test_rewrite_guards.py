from __future__ import annotations

from src.agents.domain.rewrite import (
    RewriteResult,
    evaluate_rewrite,
    invented_token_ratio,
    invented_tokens,
    rewrite_trigger,
)

KNOWN = frozenset({"vf", "vf5", "5", "thong", "tin", "xe", "klara", "ha", "noi"})


# ── Cổng "có nên gọi LLM không" — bảo vệ ngân sách A4-2 ───────────────────────


def test_a_clean_message_never_reaches_the_model() -> None:
    """Ngân sách A4-2 (lượt hỏi slot ≤ 1 lần gọi LLM) chỉ giữ được nếu câu sạch
    đi qua Lớp 1 với 0 lần gọi thêm."""

    trigger = rewrite_trigger("vf5 gia bao nhieu", KNOWN)

    assert trigger.should_attempt is False
    assert trigger.reason == "clean"


def test_truncated_tokens_are_the_strongest_noise_signal() -> None:
    trigger = rewrite_trigger("tho ti x vf nam", KNOWN)

    assert trigger.should_attempt is True
    assert trigger.reason == "truncated_tokens"
    assert "ti" in trigger.suspicious_tokens


def test_a_single_token_is_never_rewritten() -> None:
    """Đoán một từ đứng riêng chính là "suy luận thêm nội dung"."""

    assert rewrite_trigger("vf", KNOWN).reason == "too_short"


def test_a_very_long_message_is_not_rewritten() -> None:
    assert rewrite_trigger(" ".join(["xe"] * 60), KNOWN).reason == "too_long"


def test_missing_diacritics_alone_is_not_noise() -> None:
    """Mọi so khớp về sau chạy trên dạng đã bỏ dấu, nên thiếu dấu vô hại.

    Coi thiếu dấu là nhiễu sẽ đốt một lần gọi LLM cho phần lớn tin nhắn tiếng
    Việt gõ nhanh.
    """

    assert rewrite_trigger("vf5 gia bao nhieu", KNOWN).should_attempt is False


def test_digits_are_always_explained() -> None:
    """ "700 triệu" là câu trả lời ngân sách, không phải một từ gõ sai."""

    assert rewrite_trigger("700 trieu", KNOWN).should_attempt is False


def test_greetings_are_not_treated_as_noise() -> None:
    """Câu chào đầu tiên của mọi hội thoại phải đi thẳng — `classify_scope`
    (A6-2) đã có nhãn SOCIAL xử lý đúng nhóm này."""

    assert rewrite_trigger("chao em", KNOWN).should_attempt is False


# ── Guard chặn mô hình sáng tác ───────────────────────────────────────────────


def test_a_heavy_but_legitimate_spelling_fix_is_accepted() -> None:
    """Ca lỗi gốc phải qua được guard.

    Bản sửa này đổi 4/5 token, nên một guard đếm token ĐỔI sẽ chặn đúng cái ca
    mà cả tính năng sinh ra để xử lý.
    """

    result = evaluate_rewrite(original="tho ti x vf năm", rewritten="thông tin xe VF 5", confidence=0.95)

    assert result.applied is True
    assert result.reason == "applied"
    assert result.text_for_matching == "thông tin xe VF 5"


def test_invented_content_is_rejected() -> None:
    """Mô hình thêm địa điểm khách chưa hề nhắc tới → huỷ rewrite."""

    result = evaluate_rewrite(
        original="vf5",
        rewritten="VF 5 giá lăn bánh ở Hà Nội bao nhiêu",
        confidence=0.99,
    )

    assert result.applied is False
    assert result.text_for_matching == "vf5"


def test_low_model_confidence_falls_back_to_the_original() -> None:
    result = evaluate_rewrite(original="tho ti x vf năm", rewritten="thông tin xe VF 5", confidence=0.4)

    assert result.applied is False
    assert result.reason == "low_confidence"
    assert result.text_for_matching == "tho ti x vf năm"


def test_an_unchanged_rewrite_is_reported_as_no_change() -> None:
    result = evaluate_rewrite(
        original="VF 8 có mấy chỗ ngồi",
        rewritten="VF 8 có mấy chỗ ngồi",
        confidence=1.0,
    )

    assert result.applied is False
    assert result.reason == "no_change"


def test_vietnamese_number_words_count_as_traceable() -> None:
    """ "năm" → "5" là bản sửa hợp lệ, không phải token bịa."""

    assert invented_tokens("vf năm", "VF 5") == ()


def test_invented_token_ratio_is_zero_for_an_empty_rewrite() -> None:
    assert invented_token_ratio("vf5", "") == 0.0


# ── Câu gốc không bao giờ bị ghi đè ───────────────────────────────────────────


def test_the_original_survives_every_rejection_path() -> None:
    for reason in ("clean", "llm_unavailable", "invalid_payload", "disabled"):
        result = RewriteResult.unchanged("tho ti x vf năm", reason)

        assert result.original == "tho ti x vf năm"
        assert result.text_for_matching == "tho ti x vf năm"


def test_trust_is_highest_when_no_rewrite_was_needed() -> None:
    """Câu vốn sạch không có bước suy đoán nào chen vào giữa khách và hệ thống."""

    assert RewriteResult.unchanged("vf5 giá bao nhiêu", "clean").trust == 1.0


def test_trust_is_capped_by_the_model_confidence_when_applied() -> None:
    result = evaluate_rewrite(original="tho ti x vf năm", rewritten="thông tin xe VF 5", confidence=0.8)

    assert result.applied is True
    assert result.trust == 0.8
