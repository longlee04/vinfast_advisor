from __future__ import annotations

import pytest

from src.agents.domain.conversation_memory import (
    ConversationMessage,
    ConversationSummary,
    build_working_memory,
    redact_sensitive,
    sanitize_summary,
    stabilize_vehicle_summary,
)


def test_projection_keeps_slots_current_message_and_orders_summary_before_recent() -> None:
    context = build_working_memory(
        slots={"vehicle_type": "CAR", "budget_max_vnd": 500_000_000},
        summary=ConversationSummary(
            content="Khách đã loại VF 5 vì chật; đang cân nhắc VF 7.",
            summarized_through_turn=2,
        ),
        recent_messages=(
            ConversationMessage(role="USER", content="VF 7 có mấy chỗ?", turn_index=3),
            ConversationMessage(role="ASSISTANT", content="VF 7 có 7 chỗ.", turn_index=4),
        ),
        current_user_message="Mẫu còn lại giá bao nhiêu?",
        max_chars=2_000,
    )

    assert '"vehicle_type": "CAR"' in context
    assert '"budget_max_vnd": 500000000' in context
    assert "Mẫu còn lại giá bao nhiêu?" in context
    assert context.index("TÓM TẮT") < context.index("TIN NHẮN GẦN ĐÂY")


def test_projection_drops_oldest_recent_message_before_required_context() -> None:
    context = build_working_memory(
        slots={"vehicle_type": "CAR"},
        summary=None,
        recent_messages=(
            ConversationMessage(role="USER", content="TIN-CU-" * 30, turn_index=1),
            ConversationMessage(role="ASSISTANT", content="TIN-MOI", turn_index=2),
        ),
        current_user_message="GIỮ-CÂU-HIỆN-TẠI",
        max_chars=180,
    )

    assert "TIN-CU-" not in context
    assert "TIN-MOI" in context
    assert '"vehicle_type": "CAR"' in context
    assert "GIỮ-CÂU-HIỆN-TẠI" in context


@pytest.mark.parametrize("role", ["SYSTEM", "TOOL", ""])
def test_message_rejects_non_customer_visible_roles(role: str) -> None:
    with pytest.raises(ValueError):
        ConversationMessage(role=role, content="nội dung", turn_index=1)


def test_message_rejects_empty_content() -> None:
    with pytest.raises(ValueError):
        ConversationMessage(role="USER", content="   ", turn_index=1)


def test_projection_redacts_credentials() -> None:
    context = build_working_memory(
        slots={},
        summary=ConversationSummary(
            content="token=sk-secret-value password=hunter2",
            summarized_through_turn=2,
        ),
        recent_messages=(),
        current_user_message="DATABASE_URL=postgresql://admin:secret@db/app",
    )

    assert "sk-secret-value" not in context
    assert "hunter2" not in context
    assert "admin:secret" not in context
    assert "[REDACTED]" in context


@pytest.mark.parametrize(
    "secret",
    [
        "Cookie: sessionid=customer-secret",
        "session=browser-secret",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature-secret",
    ],
)
def test_redaction_covers_cookie_session_and_jwt_shapes(secret: str) -> None:
    redacted = redact_sensitive(f"Xin tư vấn xe. {secret}")

    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_summary_removes_new_numeric_fact_not_present_in_source() -> None:
    source = "Khách cân nhắc VF 5 và VF 7, đã loại VF 5 vì chật."

    cleaned = sanitize_summary(
        "Khách đã loại VF 5 vì chật. VF 7 có giá 999 triệu đồng.",
        source_text=source,
    )

    assert "loại VF 5" in cleaned
    assert "999" not in cleaned


def test_summary_keeps_canonical_eliminated_and_active_vehicle_state() -> None:
    stable = stabilize_vehicle_summary(
        candidate="Khách đang cân nhắc VF 5 và VF 7.",
        previous_summary="",
        user_message="Tôi cân nhắc VF 5 và VF 7 nhưng loại VF 5 vì chật.",
    )

    assert "Đã loại: VF 5" in stable
    assert "Đang xem: VF 7" in stable


def test_summary_preserves_canonical_state_when_llm_omits_it_next_turn() -> None:
    stable = stabilize_vehicle_summary(
        candidate="Khách hỏi giá mẫu còn lại.",
        previous_summary="Trạng thái xe — Đã loại: VF 5; Đang xem: VF 7.",
        user_message="Mẫu còn lại giá bao nhiêu?",
    )

    assert stable.endswith("Trạng thái xe — Đã loại: VF 5; Đang xem: VF 7.")
