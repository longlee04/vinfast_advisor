"""Facade phân nhánh tất định cho chặng sau đề xuất."""

from __future__ import annotations

import pytest

from src.agents.domain.post_pitch import PostPitchStage
from src.agents.domain.post_pitch_branch import (
    POST_PITCH_LLM_SHADOW_MODE,
    PostPitchBranch,
    PostPitchBranchPrediction,
    branch_from_readers,
    choose_post_pitch_branch,
)


def test_low_confidence_keeps_regex_branch() -> None:
    assert (
        choose_post_pitch_branch(
            PostPitchBranch.HAS_CONCERN,
            PostPitchBranchPrediction(PostPitchBranch.WANTS_COST, 0.99),
        )
        is PostPitchBranch.HAS_CONCERN
    )


def test_shadow_mode_keeps_regex_even_at_full_confidence() -> None:
    # Mô hình trả đúng 1.0 là chuyện thường, không phải ngoại lệ. Chừng nào còn
    # đo thì con số đó cũng không được đổi nhánh.
    assert (
        choose_post_pitch_branch(
            PostPitchBranch.HAS_CONCERN,
            PostPitchBranchPrediction(PostPitchBranch.WANTS_COST, 1.0),
        )
        is PostPitchBranch.HAS_CONCERN
    )


def test_default_is_shadow_mode() -> None:
    assert POST_PITCH_LLM_SHADOW_MODE is True


def test_exact_threshold_allows_llm_branch_once_measuring_ends() -> None:
    assert (
        choose_post_pitch_branch(
            PostPitchBranch.HAS_CONCERN,
            PostPitchBranchPrediction(PostPitchBranch.WANTS_COST, 1.0),
            shadow_mode=False,
        )
        is PostPitchBranch.WANTS_COST
    )


def test_below_threshold_keeps_regex_once_measuring_ends() -> None:
    assert (
        choose_post_pitch_branch(
            PostPitchBranch.HAS_CONCERN,
            PostPitchBranchPrediction(PostPitchBranch.WANTS_COST, 0.99),
            shadow_mode=False,
        )
        is PostPitchBranch.HAS_CONCERN
    )


@pytest.mark.parametrize(
    ("stage", "message", "answered_as_lookup", "expected"),
    [
        (PostPitchStage.AWAITING_DECISION, "có", False, PostPitchBranch.WANTS_TEST_DRIVE),
        (PostPitchStage.AWAITING_COST_CONSENT, "có", False, PostPitchBranch.WANTS_COST),
        (PostPitchStage.AWAITING_DECISION, "tính chi phí giúp anh", False, PostPitchBranch.WANTS_COST),
        (PostPitchStage.AWAITING_DECISION, "giá hơi cao", False, PostPitchBranch.HAS_CONCERN),
        (PostPitchStage.AWAITING_DECISION, "thôi để sau", False, PostPitchBranch.DECLINED),
        (PostPitchStage.AWAITING_DECISION, "cũng được", False, PostPitchBranch.UNCLEAR),
        (PostPitchStage.AWAITING_DECISION, "pin đi được bao xa", True, PostPitchBranch.ASK_ABOUT_CAR),
    ],
)
def test_branch_from_readers_preserves_stage_semantics(
    stage: PostPitchStage,
    message: str,
    answered_as_lookup: bool,
    expected: PostPitchBranch,
) -> None:
    # Given: stage hiện tại và câu trả lời khách.
    # When: facade chạy đúng các reader tất định hiện có.
    branch = branch_from_readers(stage, message, answered_as_lookup=answered_as_lookup)

    # Then: nhánh giữ nguyên nghĩa theo stage.
    assert branch is expected


@pytest.mark.parametrize(
    "stage",
    [
        PostPitchStage.AWAITING_CHOICE,
        PostPitchStage.AWAITING_DECISION,
        PostPitchStage.AWAITING_COST_CONSENT,
        PostPitchStage.IN_HITL,
        PostPitchStage.AWAITING_SLOT,
    ],
)
@pytest.mark.parametrize(
    "message",
    ["đăng ký lái thử", "đặt lịch lái thử", "dat lich lai thu", "cho anh lái thử"],
)
def test_test_drive_request_is_read_at_every_open_stage(stage: PostPitchStage, message: str) -> None:
    """Xin lái thử đọc được ở MỌI chặng còn mở, không riêng `AWAITING_DECISION`.

    BUG THẬT prod 2026-08-27: phiên đã qua `AWAITING_DECISION`, khách gõ *"đăng
    ký lái thử"* rồi *"đặt lịch lái thử"*. Bốn chặng còn lại đều trả `UNCLEAR`
    vô điều kiện, nên lời xin đặt lịch rơi xuống luồng tư vấn và khách nhận lại
    đúng bản đề xuất cũ.
    """

    assert branch_from_readers(stage, message) is PostPitchBranch.WANTS_TEST_DRIVE


def test_a_closed_stage_reads_nothing() -> None:
    """Chặng đã đóng thì không đọc nữa — `chain` đã chặn `DONE` từ trước."""

    assert branch_from_readers(PostPitchStage.DONE, "đặt lịch lái thử") is PostPitchBranch.UNCLEAR


def test_choosing_a_model_is_not_a_test_drive_request() -> None:
    """Cửa lái thử KHÔNG được nuốt lượt chốt mẫu ở `AWAITING_CHOICE`."""

    assert branch_from_readers(PostPitchStage.AWAITING_CHOICE, "Tôi chọn VinFast VF 5 All New") is (
        PostPitchBranch.UNCLEAR
    )
