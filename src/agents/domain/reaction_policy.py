"""Pure evidence-bound reaction policy for customer complaints.

Binds a complaint to the latest eligible assistant turn and structured
evidence. A deterministic acknowledgment can never invent facts: when evidence
is absent, stale, or from another session, the reaction is a neutral
acknowledgment that references nothing.

THUẦN Python — không import FastAPI/SQLAlchemy/LangGraph/LLM SDK. Marker tables
kế thừa `origin/dev/ngoc:src/agents/services/reaction_policy.py`, thích nghi với
`Topic` hiện tại (`PRICE_TCO`, `POLICY`, `CUSTOMER_EXPERIENCE`).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.values import DialogueAct, Topic

#: Marker nhận diện chủ đề phàn nàn, thích nghi từ bảng gốc của nhánh ngoc.
#: `_PRICE_NEGATIVE_MARKERS` → `PRICE_TCO`; `_WARRANTY_NEGATIVE_MARKERS` →
#: `POLICY`; `_RANGE_NEGATIVE_MARKERS` → `CUSTOMER_EXPERIENCE`.
#: Đo trên prod 2026-08-26: "giá hơi cao" xuất hiện 5 lần ở 5 phiên khác nhau và
#: KHÔNG marker nào khớp — "gia cao" hụt vì "hoi" chen vào giữa, "cao qua" hụt vì
#: câu không có "qua". Chủ đề rơi về `None`, lời đáp rơi về `NEUTRAL_ACK`, và
#: lượt chết đúng lúc khách còn muốn mua nhất. Các marker dưới bắt phần "cao"
#: kèm trạng từ giảm nhẹ, dạng người Việt hay dùng để chê giá mà vẫn giữ lịch sự.
_PRICE_TCO_MARKERS: Final[tuple[str, ...]] = (
    "dat",
    "chat",
    "gia cao",
    "cao qua",
    "hoi cao",
    "kha cao",
    "cao hon",
    "vuot ngan sach",
    "qua tam",
)
#: `ngan qua`/`it vay` chỉ giữ ở `CUSTOMER_EXPERIENCE` — hai bảng trùng nhau thì
#: "Quãng đường ngắn quá" bị đọc thành phàn nàn chính sách. `thoi han bao hanh
#: ngan` bắt "thời hạn bảo hành ngắn" (chuỗi con `thoi han ngan` không khớp vì
#: "bao hanh" chen giữa).
_POLICY_MARKERS: Final[tuple[str, ...]] = (
    "bao hanh it",
    "bao hanh hoi it",
    "thoi han bao hanh ngan",
    "thoi han ngan",
)
_CUSTOMER_EXPERIENCE_MARKERS: Final[tuple[str, ...]] = (
    "hoi it",
    "it nhi",
    "it vay",
    "ngan qua",
    "tam hoat dong thap",
    "quang duong ngan",
)

#: Câu chữ xác nhận theo chủ đề, giọng "Quý khách" của nhánh build-agent.
#: `{model}` là chỗ duy nhất được phép nhắc tên xe — chỉ điền khi evidence có.
_GROUNDED_TEMPLATES: Final[dict[Topic, str]] = {
    Topic.PRICE_TCO: "Dạ, em hiểu Quý khách thấy giá của {model} chưa phù hợp ạ.",
    Topic.POLICY: "Dạ, em hiểu Quý khách thấy chính sách của {model} chưa phù hợp ạ.",
    Topic.CUSTOMER_EXPERIENCE: "Dạ, em hiểu trải nghiệm của Quý khách với {model} chưa tốt ạ.",
}
_GENERIC_GROUNDED_ACK: Final[str] = "Dạ, em hiểu Quý khách chưa hài lòng với thông tin vừa được tư vấn ạ."

#: Lời xác nhận trung tính khi không có evidence hợp lệ — không nhắc gì tới
#: mẫu xe, giá, hay nội dung lượt trước.
NEUTRAL_ACK: Final[str] = "Dạ, em hiểu ạ."

#: Câu MỞ ĐƯỜNG nối sau lời xác nhận của một lượt phàn nàn thuần.
#:
#: Không có nó thì lượt phàn nàn là NGÕ CỤT: prod 2026-08-26 trả đúng bốn chữ
#: "Dạ, em hiểu ạ." rồi dừng, năm lần ở năm phiên. Xác nhận xong mà không hỏi gì
#: là đẩy việc nghĩ câu tiếp theo sang cho khách, ngay tại lượt họ vừa nói mình
#: chưa hài lòng — chỗ dễ rời đi nhất của cả cuộc tư vấn.
#:
#: Câu hỏi cố ý HỎI VỀ SLOT có sẵn đường xử lý (`budget_max_vnd`) thay vì hỏi
#: chung chung: khách đáp "khoảng 600 triệu" là luồng đề xuất chạy lại được ngay.
#: Không câu nào chứa chữ số hay tên xe, nên không cần evidence để nói ra.
#: ⚠️ Tránh cụm "em tìm": `output_guard._EM_ADDRESS` đọc "em" đứng trước một
#: động từ ý định (có "tìm") là KHÁCH tự xưng và đổi thành "Quý khách", nên câu
#: "để em tìm mẫu vừa tầm" ra tới khách thành "để Quý khách tìm mẫu vừa tầm" —
#: đảo ngược ai là người làm việc đó. Dùng "gợi ý", vốn không nằm trong bảng ấy.
_COMPLAINT_FOLLOW_UPS: Final[dict[Topic, str]] = {
    Topic.PRICE_TCO: ("Quý khách cho em biết mức ngân sách mong muốn để em gợi ý mẫu vừa tầm hơn ạ?"),
}
_GENERIC_FOLLOW_UP: Final[str] = "Quý khách cho em biết điểm nào chưa phù hợp để em tư vấn lại ạ?"


class ReactionDecision(StrEnum):
    """How the agent should react to a complaint turn."""

    #: Không có evidence hợp lệ — phản hồi trung tính, không bịa sự thật.
    IGNORE = "IGNORE"
    #: Phàn nàn thuần — xác nhận gắn với evidence, bỏ qua việc truy vấn lại.
    GROUNDED_ACK = "GROUNDED_ACK"
    #: Phàn nàn kèm câu hỏi — xác nhận làm tiền tố rồi tiếp tục nhiệm vụ chính.
    MIXED_PREFIX = "MIXED_PREFIX"


@dataclass(frozen=True, slots=True)
class ReactionEvidence:
    """Structured facts from the latest eligible assistant turn."""

    conversation_id: UUID
    message_id: UUID
    topic: Topic
    answer: str
    vehicle_model: str | None = None

    def __post_init__(self) -> None:
        if not self.answer.strip():
            raise ValueError("reaction evidence answer must not be empty")


@dataclass(frozen=True, slots=True)
class ReactionContext:
    """Session state the policy needs to prove evidence adjacency."""

    conversation_id: UUID
    last_message_id: UUID | None = None
    last_message_role: str | None = None

    def __post_init__(self) -> None:
        if self.last_message_role is not None and self.last_message_role not in {
            "USER",
            "ASSISTANT",
            "ADVISOR",
        }:
            raise ValueError("reaction context last_message_role must be USER, ASSISTANT, or ADVISOR")


@dataclass(frozen=True, slots=True)
class ReactionDecisionResult:
    """Deterministic reaction decision plus the customer-visible text."""

    decision: ReactionDecision
    text: str
    no_reretrieval: bool = False


def is_eligible_evidence(
    *,
    evidence: ReactionEvidence | None,
    context: ReactionContext,
) -> bool:
    """Return whether evidence is present, same-session, and assistant-adjacent.

    Assistant-message adjacency means the evidence message is the latest
    persisted message and that message is an ASSISTANT turn. Cross-session
    evidence is structurally rejected here, so a complaint can never leak
    facts from another conversation.
    """

    if evidence is None:
        return False
    if evidence.conversation_id != context.conversation_id:
        return False
    if context.last_message_id is None or evidence.message_id != context.last_message_id:
        return False
    return context.last_message_role == "ASSISTANT"


def complaint_topic(user_message: str, evidence: ReactionEvidence | None, canonical: CanonicalText) -> Topic | None:
    """Detect the complaint topic from markers, falling back to evidence topic.

    Marker là tín hiệu mạnh nhất (khôi phục chủ đề bị lược bớt trong câu);
    khi không có marker nào khớp, dùng topic của evidence. Không có cả hai thì
    trả `None` — lúc đó phản hồi dùng template chung, không đoán chủ đề.

    Marker so trên `canonical.folded` — gate không tự normalize (AMENDMENT 2).
    """

    normalized = canonical.folded
    if any(marker in normalized for marker in _PRICE_TCO_MARKERS):
        return Topic.PRICE_TCO
    if any(marker in normalized for marker in _POLICY_MARKERS):
        return Topic.POLICY
    if any(marker in normalized for marker in _CUSTOMER_EXPERIENCE_MARKERS):
        return Topic.CUSTOMER_EXPERIENCE
    if evidence is not None:
        return evidence.topic
    return None


def decide_reaction(
    *,
    user_message: str,
    canonical: CanonicalText,
    dialogue_acts: Collection[DialogueAct],
    evidence: ReactionEvidence | None,
    context: ReactionContext,
) -> ReactionDecisionResult:
    """Decide the deterministic reaction to a complaint turn.

    - Không có `DialogueAct.COMPLAIN` → `IGNORE` (không phải lượt phàn nàn).
    - Evidence thiếu/stale/khác phiên → `IGNORE` với lời trung tính, không bịa.
    - Phàn nàn thuần + evidence hợp lệ → `GROUNDED_ACK`, bỏ truy vấn lại.
    - Phàn nàn kèm hành vi khác (hỏi thêm) → `MIXED_PREFIX`: xác nhận làm tiền
      tố rồi tiếp tục nhiệm vụ chính.
    """

    if DialogueAct.COMPLAIN not in dialogue_acts:
        return ReactionDecisionResult(ReactionDecision.IGNORE, NEUTRAL_ACK)
    topic = complaint_topic(user_message, evidence, canonical)
    if evidence is None or not is_eligible_evidence(evidence=evidence, context=context):
        # Thiếu evidence thì KHÔNG được nhắc tên xe hay giá, nhưng vẫn hỏi tiếp
        # được: câu mở đường không dựa vào sự thật nào của lượt trước.
        return ReactionDecisionResult(ReactionDecision.IGNORE, _with_follow_up(NEUTRAL_ACK, topic))
    text = _grounded_text(topic, evidence.vehicle_model)
    if any(act is not DialogueAct.COMPLAIN for act in dialogue_acts):
        # Lượt vừa phàn nàn vừa hỏi: nhiệm vụ chính chạy tiếp và tự có câu hỏi
        # của nó, nên nối thêm câu mở đường ở đây là hỏi hai lần trong một tin.
        return ReactionDecisionResult(ReactionDecision.MIXED_PREFIX, text)
    return ReactionDecisionResult(
        ReactionDecision.GROUNDED_ACK,
        _with_follow_up(text, topic),
        no_reretrieval=True,
    )


def _with_follow_up(acknowledgment: str, topic: Topic | None) -> str:
    """Lời xác nhận + câu mở đường, cách nhau một dòng trống."""

    follow_up = _COMPLAINT_FOLLOW_UPS.get(topic) if topic is not None else None
    return f"{acknowledgment}\n\n{follow_up or _GENERIC_FOLLOW_UP}"


def _grounded_text(topic: Topic | None, vehicle_model: str | None) -> str:
    """Build the deterministic acknowledgment bound to evidence.

    Tên xe chỉ xuất hiện khi evidence cung cấp (`vehicle_model`); thiếu thì
    dùng "xe vừa được tư vấn" — không bao giờ tự đặt tên mẫu hay giá.
    """

    template = _GROUNDED_TEMPLATES.get(topic) if topic is not None else None
    if template is None:
        return _GENERIC_GROUNDED_ACK
    subject = vehicle_model if vehicle_model is not None else "xe vừa được tư vấn"
    return template.format(model=subject)


__all__ = [
    "NEUTRAL_ACK",
    "ReactionContext",
    "ReactionDecision",
    "ReactionDecisionResult",
    "ReactionEvidence",
    "complaint_topic",
    "decide_reaction",
    "is_eligible_evidence",
]
