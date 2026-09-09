"""Ranh giới giữa "bắt đầu lại cuộc tư vấn" và "nói thêm cho cuộc đang chạy"."""

from __future__ import annotations

import pytest

from src.agents.domain.advisory_restart import (
    RESTART_SLOTS,
    AdvisoryFlowAction,
    classify_advisory_flow,
)
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.values import SlotName


@pytest.mark.parametrize(
    "message",
    [
        "tôi cần tư vấn xe",
        "tôi muốn tư vấn xe",
        "tư vấn cho tôi xe khác",
        "cho tôi tư vấn lại",
        "tư vấn xe mới",
        "tư vấn lại từ đầu",
        "chào em, mình muốn tư vấn xe ạ",
        # Lớp 1 sửa lỗi gõ chạy TRONG graph, còn luật này chạy trước đó — nên nó
        # phải tự đọc được cách gõ tắt thường gặp.
        "e can tu van xe",
    ],
)
def test_a_bare_request_for_advice_starts_a_new_consultation(message: str) -> None:
    assert classify_advisory_flow(message).action is AdvisoryFlowAction.RESTART_ADVISORY


@pytest.mark.parametrize(
    "message",
    [
        # Ca tái hiện thứ hai: câu mở cuộc tư vấn có kèm LOẠI XE. Trước đây bị
        # đọc là "còn mang thông tin" nên giữ nguyên state, và ngân sách
        # 400-900tr của lượt trước lọc tiếp dù câu này không nhắc gì tới tiền.
        "tôi cần tư vấn xe ô tô điện",
        "tôi muốn tư vấn xe ô tô điện",
        "tư vấn xe máy điện giúp em",
        # Kèm cả tiêu chí: tiêu chí trong CHÍNH câu này được `extract_slots`
        # điền lại ngay sau reset; tiêu chí của cuộc cũ thì không.
        "tôi cần tư vấn xe ô tô giá từ 400 - 900 triệu",
        "tư vấn xe cho gia đình 5 người",
        "tư vấn giúp em xe 7 chỗ",
    ],
)
def test_an_opening_sentence_restarts_even_when_it_carries_criteria(message: str) -> None:
    """Khuôn "nhờ tư vấn + xe/ô tô/xe máy" là khuôn câu MỞ ĐẦU một cuộc tư vấn."""

    assert classify_advisory_flow(message).action is AdvisoryFlowAction.RESTART_ADVISORY


@pytest.mark.parametrize(
    "message",
    [
        # Điền slot cho cuộc đang chạy — ca đắt nhất nếu reset nhầm.
        "900 triệu và cho 5 người",
        "vậy còn xe 7 chỗ thì sao",
        "xe ô tô điện",
        # "tiếp"/"thêm" là nói tiếp, không phải làm lại.
        "tư vấn tiếp giúp em",
        "tư vấn thêm cho tôi",
        # Xin gặp người thật, không phải mở lượt tư vấn mới.
        "tôi muốn gặp tư vấn viên",
        # Nêu tên một mẫu cụ thể = hỏi về mẫu đó, không mở lại việc chọn xe.
        "tư vấn giúp em vf5 hay vf6",
        "tư vấn xe VF 5 với",
        # Có chữ "tư vấn" nhưng hỏi một thủ tục, không có tân ngữ phương tiện.
        "anh tư vấn giúp em trả góp thế nào",
        "em mua xe này được trả góp không",
        # Tra cứu, không có cụm nhờ tư vấn nào.
        "giá lăn bánh VF 5 ở Hà Nội",
        "xe vf 5 đi được bao nhiêu km/1 lần sạc",
        "",
    ],
)
def test_everything_else_continues_the_running_consultation(message: str) -> None:
    assert classify_advisory_flow(message).action is AdvisoryFlowAction.CONTINUE


def test_every_decision_carries_a_reason_for_the_log() -> None:
    """Lý do là thứ đọc được trong log khi truy một lần reset sai."""

    assert classify_advisory_flow("tôi muốn tư vấn xe").reason
    assert classify_advisory_flow("vậy còn xe 7 chỗ thì sao").reason


def test_the_reset_covers_the_whole_slot_tree() -> None:
    """Sót một slot là để cuộc tư vấn cũ sống tiếp qua lệnh reset."""

    # `interest_vehicle` là bối cảnh, cố ý KHÔNG bị mở-tư-vấn xoá (2026-08-29).
    assert RESTART_SLOTS == frozenset(slot.value for slot in SlotName if slot is not SlotName.INTEREST_VEHICLE)


def test_gate_consumes_canonical_not_raw_message() -> None:
    """Gate đọc canonical từ state (AMENDMENT 2) — user_message thô không quyết định.

    Failing-first: code cũ `_ascii_fold(user_message)` đọc "giá lăn bánh VF 5"
    → CONTINUE. Sau khi đổi sang canonical, canonical nói "tôi cần tư vấn xe"
    → RESTART_ADVISORY.
    """

    canonical = build_canonical_text("tôi cần tư vấn xe")
    decision = classify_advisory_flow("giá lăn bánh VF 5", canonical=canonical)
    assert decision.action is AdvisoryFlowAction.RESTART_ADVISORY
