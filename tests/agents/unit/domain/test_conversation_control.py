from __future__ import annotations

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.conversation_control import (
    ConversationControlAction,
    classify_conversation_control,
)


@pytest.mark.parametrize(
    "message",
    [
        "Thôi bỏ yêu cầu này đi.",
        "Thôi bỏ đi.",
        "Hủy việc tính giá giúp tôi.",
        "Không cần làm tiếp nữa.",
    ],
)
def test_explicit_cancel_is_recognized(message: str) -> None:
    assert classify_conversation_control(message) is ConversationControlAction.CANCEL


@pytest.mark.parametrize(
    "message",
    [
        "Tôi không muốn cung cấp tỉnh đăng ký.",
        "Cho tôi bỏ qua câu này nhé.",
        "Tôi xin phép không trả lời thông tin đó.",
    ],
)
def test_explicit_slot_refusal_is_recognized(message: str) -> None:
    assert classify_conversation_control(message) is ConversationControlAction.DECLINE_SLOT


@pytest.mark.parametrize(
    "message",
    [
        "Thôi không tính giá nữa, tư vấn xe 7 chỗ cho tôi.",
        "VF 8 hiện có những màu gì?",
        "Tìm showroom ở Nghệ An giúp tôi.",
    ],
)
def test_clear_new_request_switches_away_from_old_focus(message: str) -> None:
    assert classify_conversation_control(message) is ConversationControlAction.SWITCH_TASK


def test_a_valid_short_slot_answer_is_not_control_language() -> None:
    assert classify_conversation_control("Hà Nội") is ConversationControlAction.CONTINUE


def test_request_for_other_recommendations_revises_instead_of_clearing_focus() -> None:
    assert classify_conversation_control("Tôi muốn tư vấn xe khác") is ConversationControlAction.REVISE_TASK


def test_gate_consumes_canonical_not_raw_message() -> None:
    """Gate đọc canonical từ state (AMENDMENT 2) — user_message thô không quyết định.

    Failing-first: code cũ `_ascii_fold(user_message)` đọc "Hà Nội" → CONTINUE.
    Sau khi đổi sang canonical, canonical nói "hủy yêu cầu" → CANCEL.
    """

    canonical = build_canonical_text("Hủy yêu cầu này đi")
    assert classify_conversation_control("Hà Nội", canonical=canonical) is ConversationControlAction.CANCEL
