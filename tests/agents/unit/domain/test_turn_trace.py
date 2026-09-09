"""Vệt quyết định của một lượt — thứ trả lời câu "vì sao nó đáp như vậy".

Sếp 2026-08-26: màn admin phải cho thấy **vì sao** máy quyết định thế, không chỉ
cho thấy điểm số. Nên vệt này giữ đủ ba tầng lý do:

1. bốn lớp NLU tất định — bảng điểm ý định và entity đã dẫn tới nó;
2. nhãn LLM gắn cho lượt (phạm vi, ý định, slot);
3. các cửa TẤT ĐỊNH đã bật cờ (`advisory_requested`, `customer_declined`, …) —
   chính những cờ đã đè lên phán đoán của LLM ở `luong-tu-van-da-sua.md` mục 1.

Xây từ `state` cuối lượt nên KHÔNG thêm một lần gọi nào; nó chỉ đọc lại thứ các
node đã ghi.
"""

from __future__ import annotations

from src.agents.domain.turn_trace import build_turn_trace


def _state(**overrides: object) -> dict:
    base = {
        "user_message": "vf ba gia bao nhieu",
        "nlu_trace": {
            "intent_hint": "CATALOG_LOOKUP",
            "confidence": 0.83,
            "tier": "CONFIRM",
            "routing_enabled": False,
            "candidates": [{"intent": "CATALOG_LOOKUP", "score": 0.85}],
            "entities": [{"category": "VEHICLE", "canonical": "VF 3", "score": 92.0, "matched_on": "original"}],
            "rewrite_text": "vf 3 gia bao nhieu",
            "rewrite_trust": 1.0,
            "input_looks_noisy": False,
        },
        "scope_label": "IN_SCOPE",
        "intents": ["CATALOG_LOOKUP"],
        "slots": {"vehicle_type": "CAR"},
        "slots_at_turn_start": {},
        "terminal_reason": None,
        "recommendations": [{"vehicle_id": "x"}],
        "advisory_requested": True,
        "customer_declined": False,
    }
    base.update(overrides)
    return base


def test_scalar_columns_carry_what_the_dashboard_filters_on() -> None:
    """Sáu cột vô hướng là thứ đếm/lọc được bằng SQL, không phải đào trong JSON."""

    trace = build_turn_trace(session_id="s1", client_turn_id="c1", state=_state())

    assert trace.session_id == "s1"
    assert trace.client_turn_id == "c1"
    assert trace.user_message == "vf ba gia bao nhieu"
    assert trace.intent_hint == "CATALOG_LOOKUP"
    assert trace.confidence == 0.83
    assert trace.tier == "CONFIRM"
    assert trace.scope_label == "IN_SCOPE"


def test_the_reason_trail_survives_in_the_json_payload() -> None:
    """Bảng điểm ý định là CÂU TRẢ LỜI cho "vì sao" — mất nó thì màn admin chỉ
    còn một con số không giải thích được gì."""

    trace = build_turn_trace(session_id="s1", client_turn_id="c1", state=_state())

    assert trace.payload["nlu"]["candidates"] == [{"intent": "CATALOG_LOOKUP", "score": 0.85}]
    assert trace.payload["nlu"]["entities"][0]["canonical"] == "VF 3"
    assert trace.payload["nlu"]["rewrite_text"] == "vf 3 gia bao nhieu"
    assert trace.payload["llm"]["intents"] == ["CATALOG_LOOKUP"]
    assert trace.payload["outcome"]["recommendation_count"] == 1


def test_bottleneck_confidence_is_recorded_in_trace_and_review_snapshot() -> None:
    trace = build_turn_trace(
        session_id="s1",
        client_turn_id="c1",
        state=_state(
            bottleneck_detection={"status": "DETECTED", "label": "PRICE", "confidence": 0.55},
            advisor_review_snapshot={},
        ),
    )

    assert trace.payload["bottleneck"]["confidence"] == 0.55
    assert trace.payload["review"]["profile_snapshot"]["bottleneck_confidence"] == 0.55
    assert trace.payload["review"]["profile_snapshot"]["offer_suggestion_withheld"] is True


def test_deterministic_gate_flags_are_recorded_because_they_override_the_llm() -> None:
    """Bốn cờ này là thứ ĐÈ lên nhãn LLM (mục 1 của `luong-tu-van-da-sua.md`).

    Không ghi lại thì đọc log sẽ thấy "LLM gắn OUT_OF_SCOPE mà lượt vẫn chạy" và
    không cách nào biết cờ nào đã cứu nó.
    """

    trace = build_turn_trace(
        session_id="s1",
        client_turn_id=None,
        state=_state(customer_delegates_choice=True, customer_answered_vaguely=False),
    )

    gates = trace.payload["gates"]
    assert gates["advisory_requested"] is True
    assert gates["customer_delegates_choice"] is True
    assert gates["customer_declined"] is False
    assert gates["customer_answered_vaguely"] is False


def test_post_pitch_decision_is_recorded_in_payload() -> None:
    trace = build_turn_trace(
        session_id="s1",
        client_turn_id="c1",
        state=_state(
            post_pitch_trace={
                "stage": "AWAITING_COST_CONSENT",
                "branch_llm": "UNCLEAR",
                "confidence": 0.0,
                "fallback_reason": "invalid_payload",
                "branch_regex": "WANTS_COST",
                "branch_chosen": "WANTS_COST",
            }
        ),
    )

    assert trace.payload["post_pitch"] == {
        "stage": "AWAITING_COST_CONSENT",
        "branch_llm": "UNCLEAR",
        "confidence": 0.0,
        "fallback_reason": "invalid_payload",
        "branch_regex": "WANTS_COST",
        "branch_chosen": "WANTS_COST",
    }


def test_trace_without_post_pitch_decision_keeps_legacy_payload_shape() -> None:
    trace = build_turn_trace(session_id="s1", client_turn_id="c1", state=_state())

    assert "post_pitch" not in trace.payload


def test_a_turn_without_the_nlu_layer_still_produces_a_row() -> None:
    """Lớp 4 chưa nối / lỗi giữa lượt → vẫn phải có dòng, chỉ thiếu phần NLU.

    Bỏ dòng đi là mất đúng những lượt đáng điều tra nhất.
    """

    trace = build_turn_trace(session_id="s1", client_turn_id=None, state=_state(nlu_trace=None))

    assert trace.intent_hint is None
    assert trace.confidence is None
    assert trace.tier is None
    assert trace.payload["nlu"] == {}
    assert trace.user_message == "vf ba gia bao nhieu"


def test_slots_gained_this_turn_are_spelled_out() -> None:
    """Slot MỚI của lượt đáng giá hơn ảnh chụp toàn bộ: đọc log là biết ngay lượt
    đó thu được gì, không phải tự so hai dict."""

    trace = build_turn_trace(
        session_id="s1",
        client_turn_id=None,
        state=_state(
            slots_at_turn_start={"vehicle_type": "CAR"},
            slots={"vehicle_type": "CAR", "budget_max_vnd": 700_000_000},
        ),
    )

    assert trace.payload["llm"]["slots_gained"] == {"budget_max_vnd": 700_000_000}


def test_uuid_objects_are_normalised_to_strings_at_this_boundary() -> None:
    """Bug thật bắt được trên prod 2026-08-26.

    `TurnTrace` khai `session_id: str`, nhưng `chain` truyền xuống một `UUID` —
    kiểu chỉ là lời khai, không phải ràng buộc lúc chạy. Tầng dưới gọi
    `UUID(trace.client_turn_id)` và nổ `'UUID' object has no attribute 'replace'`
    mỗi lượt, hook nuốt lỗi đúng như thiết kế, bảng rỗng trong im lặng.

    Chuẩn hoá NGAY tại biên này: ai gọi cũng chỉ cần biết `TurnTrace` giữ chuỗi.
    """

    from uuid import UUID

    trace = build_turn_trace(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),  # type: ignore[arg-type]
        client_turn_id=UUID("22222222-2222-2222-2222-222222222222"),  # type: ignore[arg-type]
        state=_state(),
    )

    assert trace.session_id == "11111111-1111-1111-1111-111111111111"
    assert trace.client_turn_id == "22222222-2222-2222-2222-222222222222"


def test_a_missing_client_turn_id_stays_none_not_the_string_none() -> None:
    """`str(None)` cho ra `"None"` — một chuỗi bốn ký tự mà `UUID()` sẽ nuốt vào
    rồi nổ ở tầng dưới. Vắng vẫn phải là vắng."""

    trace = build_turn_trace(session_id="s1", client_turn_id=None, state=_state())

    assert trace.client_turn_id is None
