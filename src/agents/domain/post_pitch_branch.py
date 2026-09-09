"""Facade chung cho các bộ đọc tất định sau đề xuất."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.concern_reply import PostPitchDecision, classify_post_pitch_decision
from src.agents.domain.intent_reconciliation import is_test_drive_request
from src.agents.domain.offer_reply import CostConsent, asks_for_cost_estimate, classify_cost_consent
from src.agents.domain.post_pitch import PostPitchStage
from src.agents.domain.pricing_intent import detect_province
from src.agents.domain.range_normalizer import daily_distance_from_message

POST_PITCH_LLM_THRESHOLD: Final[float] = 1.0

#: Giai đoạn ĐO: LLM chạy mỗi lượt và ghi vào trace, nhưng KHÔNG quyết nhánh nào.
#:
#: Ngưỡng 1.0 một mình KHÔNG đủ để giữ điều đó. Schema forced-tool cho phép
#: `confidence` tối đa đúng 1.0, và mô hình gặp câu dễ thì trả thẳng 1.0 —
#: `confidence >= 1.0` khi ấy là ĐÚNG, và LLM lái nhánh thật trên prod bằng một
#: prompt còn chưa định nghĩa nổi từng nhãn. Cờ này là thứ chặn, không phải
#: ngưỡng. Chỉ hạ xuống False sau khi đã đọc `turn_traces.payload.post_pitch` đủ
#: nhiều để biết LLM lệch regex ở đâu.
POST_PITCH_LLM_SHADOW_MODE: Final[bool] = True


class PostPitchBranch(StrEnum):
    """Nhánh chung sau khi gom kết quả từ các bộ đọc tất định."""

    ASK_ABOUT_CAR = "ASK_ABOUT_CAR"
    HAS_CONCERN = "HAS_CONCERN"
    WANTS_COST = "WANTS_COST"
    WANTS_TEST_DRIVE = "WANTS_TEST_DRIVE"
    DECLINED = "DECLINED"
    UNCLEAR = "UNCLEAR"


class PostPitchFallbackReason(StrEnum):
    """Lý do classifier LLM fail-open về UNCLEAR."""

    OPTIONAL_BUDGET_EXHAUSTED = "optional_budget_exhausted"
    MISSING_API_KEY = "missing_api_key"
    TIMEOUT = "timeout"
    EMPTY_TOOL_CALL = "empty_tool_call"
    INVALID_PAYLOAD = "invalid_payload"
    PROVIDER_API_ERROR = "provider_api_error"
    UNEXPECTED_KNOWN_FAILURE = "unexpected_known_failure"


@dataclass(frozen=True, slots=True)
class PostPitchBranchPrediction:
    """Nhánh LLM quan sát cùng độ chắc chắn đã validate."""

    branch: PostPitchBranch
    confidence: float
    fallback_reason: PostPitchFallbackReason | None = None


def choose_post_pitch_branch(
    regex_branch: PostPitchBranch,
    prediction: PostPitchBranchPrediction,
    *,
    shadow_mode: bool = POST_PITCH_LLM_SHADOW_MODE,
) -> PostPitchBranch:
    """Ở chế độ đo thì luôn giữ lưới regex; tắt đo mới xét ngưỡng của LLM."""

    if shadow_mode:
        return regex_branch
    return prediction.branch if prediction.confidence >= POST_PITCH_LLM_THRESHOLD else regex_branch


def _asks_for_a_test_drive(user_message: str) -> bool:
    """Lượt này có XIN LÁI THỬ một cách rõ ràng không.

    Đòi HAI bằng chứng, cố ý:

    1. `is_test_drive_request` — câu phải NÓI RA việc đặt lịch ("lái thử", "đặt
       lịch"). Chỉ dùng bộ đọc có/không thì ở `AWAITING_COST_CONSENT` một tiếng
       "có" (nghĩa là "vâng, tính chi phí đi") sẽ bị đọc thành lời nhận lái thử.
    2. `classify_post_pitch_decision` — bộ đọc này xét NỖI LO trước, nên câu vừa
       xin lái thử vừa nêu vướng mắc ("lái thử được không nhưng anh lo giá") ngã
       về phía lắng nghe, đúng luật thứ tự ở `domain/concern_reply`.

    BUG THẬT prod 2026-08-27: bốn chặng ngoài `AWAITING_DECISION` trả `UNCLEAR`
    vô điều kiện, nên *"đăng ký lái thử"* và *"đặt lịch lái thử"* rơi xuống luồng
    tư vấn và khách nhận lại đúng bản đề xuất cũ.
    """

    return is_test_drive_request(user_message) and classify_post_pitch_decision(user_message) is (
        PostPitchDecision.TEST_DRIVE
    )


def _revises_cost_assumption(user_message: str, canonical: CanonicalText) -> bool:
    """Khách nêu tỉnh đăng ký hoặc km/ngày sau khi đã thấy bảng chi phí.

    Đo 2026-08-29 (LP35): sau bảng chi phí, khách gõ "Hà Nội" để sửa tỉnh; bộ đọc
    có/không đọc thành "không băn khoăn" → mời lái thử, còn bảng số thì không tính
    lại. Tỉnh/km là một giả định của bảng chi phí, nên câu đó thuộc nhánh chi phí.
    """

    return detect_province(user_message, canonical) is not None or daily_distance_from_message(user_message) is not None


def branch_from_readers(
    stage: PostPitchStage,
    user_message: str,
    *,
    answered_as_lookup: bool = False,
) -> PostPitchBranch:
    """Gom reader hiện có thành một nhánh, giữ nghĩa câu trả lời theo stage."""

    canonical = build_canonical_text(user_message)
    match stage:
        case PostPitchStage.AWAITING_DECISION:
            if answered_as_lookup:
                return PostPitchBranch.ASK_ABOUT_CAR
            if asks_for_cost_estimate(canonical):
                return PostPitchBranch.WANTS_COST
            decision = classify_post_pitch_decision(user_message)
            # Tỉnh/km đứng riêng là sửa giả định chi phí; nhưng "có, anh ở Hà Nội"
            # là nhận lời lái thử kèm địa điểm → bộ đọc quyết định xét trước.
            if decision is not PostPitchDecision.TEST_DRIVE and _revises_cost_assumption(user_message, canonical):
                return PostPitchBranch.WANTS_COST
            match decision:
                case PostPitchDecision.TEST_DRIVE:
                    return PostPitchBranch.WANTS_TEST_DRIVE
                case PostPitchDecision.HAS_CONCERN:
                    return PostPitchBranch.HAS_CONCERN
                case PostPitchDecision.DECLINED:
                    return PostPitchBranch.DECLINED
                case PostPitchDecision.NO_CONCERN | PostPitchDecision.UNCLEAR:
                    return PostPitchBranch.UNCLEAR
                case unreachable:
                    assert_never(unreachable)
        case PostPitchStage.AWAITING_COST_CONSENT:
            if classify_post_pitch_decision(user_message) is PostPitchDecision.HAS_CONCERN:
                return PostPitchBranch.HAS_CONCERN
            if asks_for_cost_estimate(canonical):
                return PostPitchBranch.WANTS_COST
            if _asks_for_a_test_drive(user_message):
                return PostPitchBranch.WANTS_TEST_DRIVE
            if _revises_cost_assumption(user_message, canonical):
                return PostPitchBranch.WANTS_COST
            match classify_cost_consent(canonical):
                case CostConsent.AGREE:
                    return PostPitchBranch.WANTS_COST
                case CostConsent.DECLINE:
                    return PostPitchBranch.DECLINED
                case CostConsent.UNCLEAR:
                    return PostPitchBranch.UNCLEAR
                case unreachable:
                    assert_never(unreachable)
        case PostPitchStage.AWAITING_CHOICE | PostPitchStage.IN_HITL | PostPitchStage.AWAITING_SLOT:
            if _asks_for_a_test_drive(user_message):
                return PostPitchBranch.WANTS_TEST_DRIVE
            return PostPitchBranch.UNCLEAR
        case PostPitchStage.DONE:
            return PostPitchBranch.UNCLEAR
        case unreachable:
            assert_never(unreachable)
