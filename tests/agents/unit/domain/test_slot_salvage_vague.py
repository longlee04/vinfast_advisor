"""Việc B — vị từ "câu mơ hồ" cho lượt hỏi lại slot (không sửa `is_non_answer`)."""

import pytest

from src.agents.domain.slot_salvage import is_vague_answer


@pytest.mark.parametrize(
    "message",
    [
        "tầm tầm thôi",
        "cũng khá xa",
        "chở được vài người",
        "đại khái là được",
        "tương đối thôi",
    ],
)
def test_vague_answer_is_detected(message: str) -> None:
    assert is_vague_answer(message) is True


@pytest.mark.parametrize(
    "message",
    [
        # Ba câu bắt buộc trong test âm tính — câu trả lời THẬT không được nuốt.
        "khoá chống trộm",
        "chở được năm người",
        "khoảng 500 triệu",
    ],
)
def test_real_answer_is_not_vague(message: str) -> None:
    assert is_vague_answer(message) is False
