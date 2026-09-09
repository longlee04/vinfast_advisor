"""Vệt quyết định của MỘT lượt — thứ trả lời câu "vì sao nó đáp như vậy".

Sếp 2026-08-26: màn admin phải cho thấy **vì sao** máy quyết định thế, không chỉ
cho thấy điểm số. Nên bản ghi này giữ đủ ba tầng lý do của một lượt:

1. **Bốn lớp NLU tất định** — bảng điểm ý định (`candidates`) và entity đã dẫn
   tới nó. `nlu_confidence` được thiết kế để mọi kết luận đều mang theo bằng
   chứng; ghi lại bằng chứng đó là cách duy nhất để một nhãn sai truy được về
   đúng entity gây ra nó, thay vì phải đoán mô hình đã "nghĩ" gì.
2. **Nhãn LLM** gắn cho lượt: phạm vi, ý định, slot thu được.
3. **Các cửa TẤT ĐỊNH đã bật cờ** — chính những cờ ĐÈ lên phán đoán của LLM
   (`luong-tu-van-da-sua.md` mục 1). Không ghi lại thì đọc log sẽ thấy "LLM gắn
   OUT_OF_SCOPE mà lượt vẫn chạy" và không cách nào biết cờ nào đã cứu nó.

**Hình dạng bản ghi**: vài cột VÔ HƯỚNG cho những gì cần đếm/lọc bằng SQL
(`intent_hint`, `confidence`, `tier`, `scope_label`, `terminal_reason`), cộng một
`payload` JSON giữ trọn phần còn lại. Thêm trường mới về sau không cần migration
— đúng yêu cầu "thông tin nào có giá trị thì cũng muốn ghi lại".

Hàm này chỉ ĐỌC LẠI state cuối lượt, không gọi thêm gì: nó không được phép làm
một lượt chậm đi hay hỏng đi chỉ vì mục đích quan sát.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.agents.domain.bottleneck_signal import OFFER_SUGGESTION_THRESHOLD, BottleneckDetected

#: Cờ của các cửa TẤT ĐỊNH. Mỗi cờ ở đây là một lần "bản đọc tất định thắng bản
#: đọc của LLM" — xem nguyên tắc rút ra ở `luong-tu-van-da-sua.md` mục 1.
_GATE_FLAGS: tuple[str, ...] = (
    "advisory_requested",
    "customer_declined",
    "customer_delegates_choice",
    "customer_answered_vaguely",
    "handoff_active",
    "narrow_asked",
    # Điều kiện MỚI của ba cờ "đây là câu trả lời" (2026-08-26). Thiếu nó
    # trong vệt thì đọc log không phân biệt được "cờ bật nhưng cửa vẫn đóng"
    # với "cửa đã mở" — đúng câu hỏi cần trả lời khi điều tra lỗ rò.
    "bot_asked_last_turn",
    # Cờ thứ TƯ của nhóm "đây là câu trả lời" (2026-08-26): khách chọn HẾT tính
    # năng vừa liệt kê. Ngược hẳn `customer_declined` về ý, cùng hình dạng lỗi.
    "customer_selected_all_features",
    # Cửa phạm vi thứ SÁU: đang ở trong chặng sau đề xuất.
    "in_post_pitch_stage",
    "names_foreign_domain",
)

#: Nhãn bốn trục + nhãn phạm vi do LLM gắn.
_LLM_LABELS: tuple[str, ...] = (
    "scope_label",
    "dialogue_act",
    "task_action",
    "primary_topic",
    "severity",
)


@dataclass(frozen=True, slots=True)
class TurnTrace:
    """Một dòng cho một lượt."""

    session_id: str
    client_turn_id: str | None
    user_message: str
    intent_hint: str | None
    confidence: float | None
    tier: str | None
    scope_label: str | None
    terminal_reason: str | None
    routing_enabled: bool
    payload: dict[str, Any] = field(default_factory=dict)


def build_turn_trace(*, session_id: str, client_turn_id: str | None, state: Mapping[str, Any]) -> TurnTrace:
    """Dựng vệt quyết định từ state cuối lượt."""

    nlu = dict(state.get("nlu_trace") or {})
    return TurnTrace(
        # Chuẩn hoá về CHUỖI ngay tại biên. `chain` truyền xuống lúc `str`, lúc
        # `UUID` — chú thích kiểu chỉ là lời khai, không phải ràng buộc lúc chạy.
        # Bug thật 2026-08-26: tầng dưới gọi `UUID(trace.client_turn_id)` và nổ
        # `'UUID' object has no attribute 'replace'` MỖI LƯỢT; hook nuốt lỗi đúng
        # như thiết kế nên bảng rỗng suốt trong im lặng.
        session_id=str(session_id),
        client_turn_id=str(client_turn_id) if client_turn_id is not None else None,
        user_message=state.get("user_message") or "",
        intent_hint=nlu.get("intent_hint"),
        confidence=nlu.get("confidence"),
        tier=nlu.get("tier"),
        scope_label=state.get("scope_label"),
        terminal_reason=state.get("terminal_reason"),
        routing_enabled=bool(nlu.get("routing_enabled")),
        payload={
            "nlu": nlu,
            "llm": _llm_section(state),
            "gates": {name: bool(state.get(name)) for name in _GATE_FLAGS},
            "outcome": _outcome_section(state),
            **_bottleneck_section(state),
            **_review_section(state),
            **_post_pitch_section(state),
        },
    )


def _bottleneck_section(state: Mapping[str, Any]) -> dict[str, Any]:
    detection = state.get("bottleneck_detection")
    if isinstance(detection, BottleneckDetected):
        return {
            "bottleneck": {
                "status": detection.status.value,
                "label": detection.label.value,
                "confidence": detection.confidence,
                "offer_suggestion_withheld": detection.offer_suggestion_withheld,
                "model_name": detection.model_name,
                "prompt_version": detection.prompt_version,
            }
        }
    if isinstance(detection, Mapping):
        return {"bottleneck": dict(detection)}
    return {}


def _review_section(state: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = state.get("advisor_review_snapshot")
    detection = state.get("bottleneck_detection")
    if snapshot is not None and hasattr(snapshot, "model_dump"):
        profile_snapshot = snapshot.model_dump(mode="json")
    elif isinstance(snapshot, Mapping):
        profile_snapshot = dict(snapshot)
    else:
        return {}
    if isinstance(detection, BottleneckDetected):
        confidence = detection.confidence
        withheld = detection.offer_suggestion_withheld
    elif isinstance(detection, Mapping):
        confidence = float(detection.get("confidence", 0.0))
        withheld = confidence < OFFER_SUGGESTION_THRESHOLD
    else:
        return {"review": {"profile_snapshot": profile_snapshot}}
    profile_snapshot.update(
        bottleneck_confidence=confidence,
        offer_suggestion_withheld=withheld,
    )
    return {"review": {"profile_snapshot": profile_snapshot}}


def _post_pitch_section(state: Mapping[str, Any]) -> dict[str, Any]:
    post_pitch = state.get("post_pitch_trace")
    return {"post_pitch": dict(post_pitch)} if isinstance(post_pitch, Mapping) else {}


def _llm_section(state: Mapping[str, Any]) -> dict[str, Any]:
    section: dict[str, Any] = {name: state.get(name) for name in _LLM_LABELS}
    section["intents"] = list(state.get("intents") or [])
    section["vehicle_mentions"] = list(state.get("vehicle_mentions") or [])
    section["feature_mentions"] = list(state.get("feature_mentions") or [])
    section["slots_gained"] = _slots_gained(state)
    return section


def _slots_gained(state: Mapping[str, Any]) -> dict[str, Any]:
    """Slot MỚI của lượt này.

    Đáng giá hơn ảnh chụp toàn bộ hồ sơ: đọc log là biết ngay lượt đó thu được
    gì, không phải tự so hai dict. Ảnh chụp đầy đủ vẫn nằm ở `conversation_slots`.
    """

    before = dict(state.get("slots_at_turn_start") or {})
    after = dict(state.get("slots") or {})
    return {name: value for name, value in after.items() if before.get(name) != value}


def _outcome_section(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "terminal_reason": state.get("terminal_reason"),
        "awaiting_review": bool(state.get("awaiting_review")),
        "recommendation_count": len(state.get("recommendations") or []),
        "has_pending_question": bool(state.get("pending_question")),
        # Cắt ngắn: bản đầy đủ đã nằm ở `conversation_messages`, bảng này để
        # ĐỌC NHANH chứ không phải bản sao thứ hai của hội thoại.
        "answer_preview": (state.get("answer") or "")[:200] or None,
    }


__all__ = ["TurnTrace", "build_turn_trace"]
