from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.pending_intent_confirmation import (
    ConfirmationAnswer,
    PendingIntentConfirmation,
    read_confirmation,
)
from src.agents.services.pending_intent_confirmation import (
    PendingIntentConfirmationServiceImpl,
)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
SERVICE = PendingIntentConfirmationServiceImpl(suggestions=("VF 3", "VF 5"))


def _payload(asked_at: datetime = NOW, turn_count: int = 0) -> dict:
    return PendingIntentConfirmation(
        proposed_text="thông tin xe VF 5",
        intent_hint="CATALOG_LOOKUP",
        vehicle_names=("VF 5",),
        confidence=0.72,
        asked_at=asked_at,
        turn_count=turn_count,
    ).to_payload()


# ── Đọc phản hồi của khách ────────────────────────────────────────────────────


def test_affirmations_are_recognised() -> None:
    for message in ("đúng", "Đúng rồi", "vâng", "ok", "chuẩn", "phải rồi"):
        assert read_confirmation(message, build_canonical_text(message)) is ConfirmationAnswer.AFFIRMED


def test_denials_are_recognised() -> None:
    for message in ("không phải", "sai", "ko", "chưa phải"):
        assert read_confirmation(message, build_canonical_text(message)) is ConfirmationAnswer.DENIED


def test_a_negation_inside_a_longer_sentence_is_not_a_denial() -> None:
    """ "không" nằm trong "xe không cần sạc nhà" — đọc thành phủ nhận sẽ vứt mất
    nội dung khách vừa cung cấp."""

    assert read_confirmation("cho tôi xem xe không cần sạc tại nhà", build_canonical_text("cho tôi xem xe không cần sạc tại nhà")) is ConfirmationAnswer.UNRELATED


# ── Vòng đời bản ghi ──────────────────────────────────────────────────────────


def test_confirming_substitutes_the_message_and_lets_the_turn_continue() -> None:
    """Dừng lượt ở đây sẽ khiến khách gật đầu xong không nhận được gì."""

    resolution = SERVICE.resolve(payload=_payload(), user_message="đúng", canonical=build_canonical_text("đúng"), now=NOW)

    assert resolution.substitute_message == "thông tin xe VF 5"
    assert resolution.reply is None
    assert resolution.clear_pending is True


def test_denying_ends_the_turn_with_an_open_question() -> None:
    """Bằng chứng không đổi thì suy đoán thứ hai cũng sai theo đúng kiểu đó."""

    resolution = SERVICE.resolve(payload=_payload(), user_message="không phải", canonical=build_canonical_text("không phải"), now=NOW)

    assert resolution.reply is not None
    assert resolution.substitute_message is None
    assert resolution.clear_pending is True


def test_an_unrelated_message_drops_the_record_and_runs_normally() -> None:
    resolution = SERVICE.resolve(payload=_payload(), user_message="VF 8 giá bao nhiêu", canonical=build_canonical_text("VF 8 giá bao nhiêu"), now=NOW)

    assert resolution.substitute_message is None
    assert resolution.reply is None
    assert resolution.clear_pending is True


def test_an_expired_record_is_cleaned_up_on_read() -> None:
    resolution = SERVICE.resolve(
        payload=_payload(asked_at=NOW - timedelta(hours=1)),
        user_message="đúng", canonical=build_canonical_text("đúng"),
        now=NOW,
    )

    assert resolution.substitute_message is None
    assert resolution.clear_pending is True


def test_no_record_means_the_turn_is_untouched() -> None:
    resolution = SERVICE.resolve(payload=None, user_message="đúng", canonical=build_canonical_text("đúng"), now=NOW)

    assert resolution.substitute_message is None
    assert resolution.reply is None
    assert resolution.clear_pending is False


# ── Payload hỏng không được làm chết lượt ─────────────────────────────────────


def test_a_corrupt_payload_is_treated_as_no_record() -> None:
    """Một `ValueError` ở đây làm chết lượt của khách vì một cột dữ liệu cũ."""

    for broken in ({"proposed_text": ""}, {"khong_dung_khoa": 1}, {"proposed_text": 5}):
        assert PendingIntentConfirmation.from_payload(broken) is None


def test_a_record_without_a_timestamp_is_treated_as_expired() -> None:
    """Chiều an toàn: giữ một bản ghi không rõ tuổi thì mọi tin nhắn về sau bị
    đọc sai."""

    record = PendingIntentConfirmation(proposed_text="thông tin xe VF 5")

    assert record.is_expired(NOW) is True


def test_the_payload_survives_a_round_trip() -> None:
    original = PendingIntentConfirmation(
        proposed_text="thông tin xe VF 5",
        intent_hint="CATALOG_LOOKUP",
        vehicle_names=("VF 5",),
        confidence=0.72,
        asked_at=NOW,
    )

    restored = PendingIntentConfirmation.from_payload(original.to_payload())

    assert restored == original
