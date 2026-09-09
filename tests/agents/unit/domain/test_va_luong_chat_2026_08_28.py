"""Khoá các lỗ bắt được khi bắn 16 hội thoại thật ngày 2026-08-28.

Mỗi test ghi đúng câu khách gõ đã làm luồng chết. Đây là lưới tất định — nếu
một ca ở đây đỏ thì khách thật đã gặp lại đúng lỗi cũ.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.domain.budget_parsing import parse_budget_range
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.claim_policy import feature_codes_mentioned, negated_feature_codes
from src.agents.domain.conversation_control import ConversationControlAction, classify_conversation_control
from src.agents.domain.foreign_brand import foreign_brand_named, foreign_brand_reply
from src.agents.domain.slot_recall import is_slot_recall_request, recall_reply
from src.agents.domain.turn_understanding import is_restart_task_request
from src.agents.services.synthesis import _deterministic_fallback_draft, _tidy_number


class TestBudgetHundredMillion:
    @pytest.mark.parametrize(
        ("text", "low", "high"),
        [
            ("5-6 trăm triệu", 500_000_000, 600_000_000),
            ("tầm 5 6 trăm gì đó chưa chắc, tùy", 500_000_000, 600_000_000),
        ],
    )
    def test_hundred_million_range(self, text: str, low: int, high: int) -> None:
        parsed = parse_budget_range(text)
        assert parsed.min_vnd == Decimal(low)
        assert parsed.max_vnd == Decimal(high)

    @pytest.mark.parametrize(("text", "ceiling"), [("khoảng 7 trăm", 700_000_000), ("tam 5 tram trieu", 500_000_000)])
    def test_hundred_million_single(self, text: str, ceiling: int) -> None:
        assert parse_budget_range(text).max_vnd == Decimal(ceiling)

    @pytest.mark.parametrize("text", ["2", "1", "9"])
    def test_single_bare_digit_is_ambiguous(self, text: str) -> None:
        parsed = parse_budget_range(text)
        assert parsed.max_vnd is None and parsed.min_vnd is None

    def test_bare_hundreds_still_means_million(self) -> None:
        assert parse_budget_range("500").max_vnd == Decimal(500_000_000)


class TestRestartCue:
    @pytest.mark.parametrize("text", ["bắt đầu lại", "Bắt đầu lại đi", "làm lại", "làm lại từ đầu"])
    def test_restart_phrases(self, text: str) -> None:
        assert is_restart_task_request(text, build_canonical_text(text))
        assert classify_conversation_control(text) is ConversationControlAction.SWITCH_TASK

    @pytest.mark.parametrize("text", ["bắt đầu từ 500 triệu", "làm lại giấy tờ mất bao lâu"])
    def test_not_restart(self, text: str) -> None:
        assert not is_restart_task_request(text, build_canonical_text(text))


class TestNegatedFeatures:
    def test_negated_codes_are_dropped(self) -> None:
        text = "không cần 7 chỗ, ghét xe to, không cần camera 360"
        mentioned = feature_codes_mentioned(text)
        negated = negated_feature_codes(text)
        assert mentioned <= negated | frozenset()
        assert not (mentioned - negated)

    def test_positive_mention_kept(self) -> None:
        text = "muốn có camera 360 và ghế da"
        assert negated_feature_codes(text) == frozenset()
        assert feature_codes_mentioned(text)

    def test_mixed_polarity(self) -> None:
        text = "cần camera 360 nhưng không cần ghế da"
        negated = negated_feature_codes(text)
        positive = feature_codes_mentioned(text) - negated
        assert positive and negated
        assert not (positive & negated)


class TestForeignBrand:
    def test_compare_with_tesla(self) -> None:
        brand = foreign_brand_named("so sánh VF 8 với Tesla Model Y")
        assert brand == "tesla"
        assert "VinFast" in foreign_brand_reply(brand)

    def test_price_of_foreign(self) -> None:
        assert foreign_brand_named("Toyota Corolla Cross giá bao nhiêu") == "toyota"

    @pytest.mark.parametrize(
        "text",
        ["đang đi Honda, muốn tư vấn xe điện", "tôi muốn đổi sang xe điện, xe cũ là Yamaha", "VF 8 giá bao nhiêu"],
    )
    def test_not_blocked(self, text: str) -> None:
        assert foreign_brand_named(text) is None


class TestSlotRecall:
    @pytest.mark.parametrize(
        "text",
        ["à mà ngân sách tôi là bao nhiêu nhỉ", "tôi vừa nói loại xe gì", "em ghi nhận gì rồi", "nhắc lại giúp tôi"],
    )
    def test_recall_cue(self, text: str) -> None:
        assert is_slot_recall_request(text)

    @pytest.mark.parametrize("text", ["700 triệu", "tôi muốn tư vấn", "xe nào tiết kiệm nhất"])
    def test_not_recall(self, text: str) -> None:
        assert not is_slot_recall_request(text)

    def test_reply_lists_known_slots(self) -> None:
        reply = recall_reply(
            {"vehicle_type": "CAR", "budget_max_vnd": 700_000_000, "budget_min_vnd": 700_000_000, "purpose": "đi làm"}
        )
        assert "ô tô điện" in reply and "700 triệu" in reply and "đi làm" in reply

    def test_reply_when_empty(self) -> None:
        assert "chưa ghi nhận" in recall_reply({})


class TestSynthesisFallbackProse:
    def test_tidy_number(self) -> None:
        assert _tidy_number("82.00") == "82"
        assert _tidy_number("310.50") == "310.5"
        assert _tidy_number("1348000000") == "1348000000"

    def test_fallback_has_no_and_chain(self) -> None:
        class _Claim:
            def __init__(self, placeholder: str) -> None:
                self.placeholder = placeholder
                self.slot = placeholder.lower()
                self.text = placeholder.lower()

        claims = {key: _Claim(key) for key in ("CLAIM_VEHICLE_TYPE", "CLAIM_BUDGET", "CLAIM_PURPOSE", "CLAIM_RANGE_KM")}
        draft = _deterministic_fallback_draft(
            vehicle_name="VinFast VF 6 Eco", fact_by_code={}, claim_by_key=claims, quote_by_key={}
        )
        assert draft.count(" và ") <= 1
        assert "{CLAIM_VEHICLE_TYPE}" not in draft
        assert draft.startswith("VinFast VF 6 Eco {")


class TestPendingBudgetSingleDigit:
    def test_single_digit_asks_unit(self) -> None:
        from datetime import UTC, datetime

        from src.agents.domain.pending_slot import PendingSlotRequest
        from src.agents.services.pending_slot import PendingSlotServiceImpl

        pending = PendingSlotRequest(intent="ADVISORY", missing_slot="budget_max_vnd", asked_at=datetime.now(UTC))
        resolution = PendingSlotServiceImpl().resolve(
            payload=pending.to_payload(), user_message="2", canonical=build_canonical_text("2")
        )
        assert resolution.handled and resolution.pending is not None
        assert "2 triệu hay 2 tỷ" in (resolution.reply or "")

    def test_number_with_unit_is_taken(self) -> None:
        from datetime import UTC, datetime

        from src.agents.domain.pending_slot import PendingSlotRequest
        from src.agents.services.pending_slot import PendingSlotServiceImpl

        pending = PendingSlotRequest(intent="ADVISORY", missing_slot="budget_max_vnd", asked_at=datetime.now(UTC))
        resolution = PendingSlotServiceImpl().resolve(
            payload=pending.to_payload(), user_message="2 tỉ", canonical=build_canonical_text("2 tỉ")
        )
        assert resolution.filled_form == {"budget_max_vnd": 2_000_000_000}
