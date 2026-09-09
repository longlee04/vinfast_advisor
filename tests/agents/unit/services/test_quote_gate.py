"""[A7-4] Cổng rủi ro ở tầng use case: audit, shadow-mode, feature flag."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import QuoteAuditRecord, VehicleFacts
from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.quote_risk import DeliveryAction, QuoteRiskTier
from src.agents.domain.values import VehicleType
from src.agents.services.quote_gate import QuoteGateConfig, QuoteGateServiceImpl

SESSION = "11111111-1111-1111-1111-111111111111"
VF3 = UUID("30000000-0000-0000-0000-000000000003")


class RecordingAudit:
    def __init__(self) -> None:
        self.entries: list[QuoteAuditRecord] = []

    async def record(self, entry: QuoteAuditRecord) -> None:
        self.entries.append(entry)


class ExplodingAudit:
    async def record(self, entry: QuoteAuditRecord) -> None:
        raise RuntimeError("sink down")


def _priced_fact(price: Decimal | None = Decimal(322_000_000)) -> VehicleFacts:
    return VehicleFacts(
        vehicle_id=VF3,
        display_name="VF 3",
        vehicle_type=VehicleType.CAR,
        starting_price_vnd=price,
        specs={"seat_count": 4},
    )


def _gate(audit=None, **config) -> QuoteGateServiceImpl:
    return QuoteGateServiceImpl(
        audit=audit,
        config=QuoteGateConfig(**config),
        # Sampler tất định: test về sampling phải kiểm đúng ngưỡng, không phải
        # cầu may với `random.random`.
        sampler=lambda: 0.0,
    )


@pytest.mark.asyncio
async def test_listed_price_lookup_is_released_without_human_review() -> None:
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
    )

    assert decision.requires_hitl is False
    assert decision.tier == QuoteRiskTier.DETERMINISTIC_AUTO.value
    # Chính lượt này là thứ luồng cũ đang chặn — đó là toàn bộ lý do của A7-4.
    assert decision.legacy_requires_hitl is True


@pytest.mark.asyncio
async def test_price_cut_request_is_blocked_and_carries_a_reviewable_note() -> None:
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="anh giảm cho em 20 triệu được không",
        canonical=build_canonical_text("anh giảm cho em 20 triệu được không"),
    )

    assert decision.requires_hitl is True
    assert decision.evaluation["is_negotiated"] is True
    assert "is_negotiated" in decision.reasons
    # Không có bản nháp thì hàng đợi phải nhận được thứ khác rỗng, nếu không
    # `review_queue.enqueue` từ chối và mục duyệt biến mất.
    assert decision.escalation_note is not None
    assert "20 triệu" in decision.escalation_note


@pytest.mark.asyncio
async def test_explicit_human_request_is_direct_advisor_handoff() -> None:
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="Cho tôi gặp tư vấn viên ngay",
        canonical=build_canonical_text("Cho tôi gặp tư vấn viên ngay"),
    )

    assert decision.requires_hitl is True
    assert decision.delivery_action == DeliveryAction.ADVISOR_HANDOFF.value
    assert decision.tier == QuoteRiskTier.ADVISOR_HANDOFF.value
    assert decision.reasons == ("CUSTOMER_REQUESTED_HUMAN",)
    assert decision.escalation_note


@pytest.mark.asyncio
async def test_spec_only_lookup_never_reaches_the_quote_policy() -> None:
    """Tra thông số (không giá) là Tier tự động thuần, không phải báo giá."""

    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="VF 3 có mấy chỗ ngồi",
        canonical=build_canonical_text("VF 3 có mấy chỗ ngồi"),
        lookup_facts=[_priced_fact(price=None)],
    )

    assert decision.tier == QuoteRiskTier.NON_QUOTE.value
    assert decision.requires_hitl is False
    assert decision.evaluation == {}


@pytest.mark.asyncio
async def test_ambiguous_model_in_a_priced_answer_drops_below_threshold() -> None:
    """Báo giá kèm một mẫu xe chưa xác định là báo NHẦM giá — chặn."""

    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="VF 3 với VF e34 giá bao nhiêu",
        canonical=build_canonical_text("VF 3 với VF e34 giá bao nhiêu"),
        lookup_facts=[_priced_fact()],
        unresolved_mentions=["VF e34"],
    )

    assert decision.requires_hitl is True
    assert "confidence_below_threshold" in decision.reasons


@pytest.mark.asyncio
async def test_verified_recommendation_draft_is_delivered_with_audit() -> None:
    """LLM chỉ viết lời trên snapshot đã kiểm chứng thì không cần chờ duyệt."""

    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="tư vấn giúp em xe 7 chỗ",
        canonical=build_canonical_text("tư vấn giúp em xe 7 chỗ"),
        draft_answer="VF 9 phù hợp nhu cầu của anh/chị.",
        recommendation_count=1,
        facts_verified=True,
    )

    assert decision.requires_hitl is False
    assert decision.delivery_action == DeliveryAction.DELIVER_WITH_AUDIT.value
    assert decision.tier == QuoteRiskTier.EVIDENCE_BACKED_AUTO.value


@pytest.mark.asyncio
async def test_unverified_llm_draft_still_needs_human_review() -> None:
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="tư vấn giúp em xe 7 chỗ",
        canonical=build_canonical_text("tư vấn giúp em xe 7 chỗ"),
        draft_answer="VF 9 phù hợp nhu cầu của anh/chị.",
        recommendation_count=1,
        facts_verified=None,
    )

    assert decision.requires_hitl is True
    assert decision.delivery_action == DeliveryAction.SYNC_REVIEW.value
    assert "facts_not_verified" in decision.reasons


@pytest.mark.asyncio
async def test_commercial_claim_in_the_output_forces_advisor_handoff() -> None:
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message="tư vấn giúp em xe gia đình",
        canonical=build_canonical_text("tư vấn giúp em xe gia đình"),
        draft_answer="VF 9 phù hợp và bên em giảm giá thêm cho anh/chị.",
        recommendation_count=1,
        facts_verified=True,
    )

    assert decision.delivery_action == DeliveryAction.ADVISOR_HANDOFF.value
    assert decision.requires_hitl is True
    assert "is_negotiated" in decision.reasons


@pytest.mark.asyncio
async def test_acknowledgment_remembers_that_a_safe_recommendation_was_delivered() -> None:
    gate = _gate()
    delivered = await gate.evaluate(
        session_id=SESSION,
        user_message="tư vấn xe cho gia đình bảy người",
        canonical=build_canonical_text("tư vấn xe cho gia đình bảy người"),
        draft_answer="VF 9 phù hợp nhu cầu của anh/chị.",
        recommendation_count=1,
        facts_verified=True,
    )

    acknowledged = await gate.evaluate(
        session_id=SESSION,
        user_message="ok",
        canonical=build_canonical_text("ok"),
        slots_before={},
        slots_after={},
        last_quote_evaluation=delivered.evaluation_to_remember,
    )

    assert delivered.evaluation_to_remember is not None
    assert acknowledged.requires_hitl is False
    assert "đang chờ" not in (acknowledged.reply or "").casefold()


# ── Audit bất đồng bộ ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_approved_quotes_are_still_logged_in_full() -> None:
    audit = RecordingAudit()
    await _gate(audit).evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
        rendered_answer="VF 3: giá niêm yết từ 322.000.000 đồng.",
    )

    [entry] = audit.entries
    assert entry.requires_hitl is False
    assert entry.user_message == "giá xe VF3 bao nhiêu"
    assert entry.output_content.startswith("VF 3")
    assert entry.evaluation["is_deterministic_standard"] is True


@pytest.mark.asyncio
async def test_sampling_only_marks_auto_approved_cases_for_periodic_review() -> None:
    audit = RecordingAudit()
    gate = _gate(audit, audit_sample_rate=1.0)

    await gate.evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
    )
    await gate.evaluate(
        session_id=SESSION,
        user_message="anh giảm cho em 20 triệu nhé",
        canonical=build_canonical_text("anh giảm cho em 20 triệu nhé"),
    )

    auto, blocked = audit.entries
    assert auto.sampled_for_review is True
    # Case bị chặn đã có người đọc ở hàng đợi duyệt; gắn cờ sample nữa là đếm hai lần.
    assert blocked.sampled_for_review is False


@pytest.mark.asyncio
async def test_near_threshold_cases_are_flagged_even_when_blocked() -> None:
    """Dải cận ngưỡng là tập dữ liệu để tune `CONFIDENCE_THRESHOLD` về sau.

    Case dùng ở đây có confidence 0.70. Với margin mặc định 0.10 nó nằm NGOÀI
    dải `[0.75, 0.85)`; nới margin lên 0.20 thì lọt vào — hai lần chạy dưới đây
    khoá đúng biên đó, vì một dải luôn-đúng thì không nói lên điều gì về ngưỡng.
    """

    audit = RecordingAudit()
    for margin in (0.10, 0.20):
        await _gate(audit, near_threshold_margin=margin).evaluate(
            session_id=SESSION,
            user_message="VF 3 với VF e34 giá bao nhiêu",
            canonical=build_canonical_text("VF 3 với VF e34 giá bao nhiêu"),
            lookup_facts=[_priced_fact()],
            unresolved_mentions=["VF e34"],
        )

    outside, inside = audit.entries
    assert outside.requires_hitl is True and inside.requires_hitl is True
    assert outside.near_threshold is False
    assert inside.near_threshold is True
    assert inside.evaluation["confidence_score"] == pytest.approx(0.70)


@pytest.mark.asyncio
async def test_a_broken_audit_sink_never_breaks_the_customer_turn() -> None:
    decision = await QuoteGateServiceImpl(audit=ExplodingAudit()).evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
    )

    assert decision.requires_hitl is False


# ── Shadow-mode & feature flag ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_counters_measure_what_the_new_policy_released() -> None:
    gate = _gate()

    await gate.evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
    )
    await gate.evaluate(
        session_id=SESSION,
        user_message="giảm giá cho em đi anh",
        canonical=build_canonical_text("giảm giá cho em đi anh"),
        lookup_facts=[_priced_fact()],
    )

    assert gate.shadow.total == 2
    assert gate.shadow.legacy_blocked == 2  # luồng cũ chặn cả hai
    assert gate.shadow.new_blocked == 1  # luồng mới chỉ chặn câu mặc cả
    assert gate.shadow.released_by_new_policy == 1
    assert gate.shadow.release_rate == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_lowering_the_policy_flag_restores_the_old_blocking_behaviour() -> None:
    """Nút lùi một bước: tắt cờ là quay về "chạm dữ liệu thì chặn"."""

    decision = await _gate(risk_policy_enabled=False).evaluate(
        session_id=SESSION,
        user_message="giá xe VF3 bao nhiêu",
        canonical=build_canonical_text("giá xe VF3 bao nhiêu"),
        lookup_facts=[_priced_fact()],
    )

    assert decision.requires_hitl is True
    assert decision.reasons == ("legacy_policy_flag",)


def test_config_from_env_reads_every_tunable() -> None:
    config = QuoteGateConfig.from_env(
        {
            "QUOTE_HITL_CONFIDENCE_THRESHOLD": "0.9",
            "QUOTE_AUDIT_SAMPLE_RATE": "0.25",
            "QUOTE_STANDARD_PROMOTIONS": "ưu đãi tháng vàng, quà tặng khai xuân",
            "QUOTE_RISK_POLICY_ENABLED": "false",
            "QUOTE_HITL_SHADOW_MODE": "0",
        }
    )

    assert config.confidence_threshold == pytest.approx(0.9)
    assert config.audit_sample_rate == pytest.approx(0.25)
    assert config.standard_promotions == frozenset({"ưu đãi tháng vàng", "quà tặng khai xuân"})
    assert config.risk_policy_enabled is False
    assert config.shadow_mode_enabled is False


@pytest.mark.parametrize("broken", ["", "abc", "1.7", "-2"])
def test_a_broken_threshold_env_var_keeps_the_safe_default(broken: str) -> None:
    """Gõ sai biến môi trường không được lặng lẽ hạ ngưỡng an toàn về 0."""

    config = QuoteGateConfig.from_env({"QUOTE_HITL_CONFIDENCE_THRESHOLD": broken})

    assert config.confidence_threshold == QuoteGateConfig().confidence_threshold


# --- T8: bảng ưu đãi chuẩn cấu hình từ env ------------------------------------


@pytest.mark.parametrize(
    ("promotion_env", "expected_off_policy"),
    [
        ("ưu đãi tháng vàng", False),
        ("quà tặng khai xuân", True),
    ],
    ids=["trong-bang-duyet", "ngoai-bang-duyet"],
)
@pytest.mark.asyncio
async def test_env_promotion_list_reaches_the_running_gate(promotion_env: str, expected_off_policy: bool) -> None:
    """Đổi bảng ưu đãi bằng biến môi trường, không sửa code.

    Bài test cấu hình sẵn có chỉ chứng minh chuỗi env được PHÂN TÍCH đúng. Nó
    không nói gì về việc giá trị đó có đi tới chỗ ra quyết định hay không — mà
    đó mới là điều khiến `STANDARD_PROMOTIONS` rỗng trong `domain/` trở thành vô
    hại thay vì thành một mặc định chặn mọi ưu đãi.
    """

    service = QuoteGateServiceImpl(
        config=QuoteGateConfig.from_env({"QUOTE_STANDARD_PROMOTIONS": promotion_env}),
    )
    message = "cho em hỏi ưu đãi tháng vàng còn không"

    decision = await service.evaluate(
        session_id="11111111-1111-1111-1111-111111111111",
        user_message=message,
        canonical=build_canonical_text(message),
        lookup_facts=[
            VehicleFacts(
                vehicle_id=UUID("20000000-0000-0000-0000-000000000101"),
                display_name="VF 8",
                vehicle_type=VehicleType.CAR,
                starting_price_vnd=Decimal("1090000000"),
                specs={"seat_count": 5},
            )
        ],
    )

    assert decision is not None
    assert decision.evaluation["has_non_standard_offer"] is expected_off_policy


def test_the_domain_default_promotion_list_stays_empty() -> None:
    """Mặc định RỖNG là chiều an toàn — và phải ở nguyên đó.

    Đổ tên chương trình thẳng vào hằng số `domain/` sẽ tạo nguồn sự thật thứ
    hai, im lặng thắng env ở mọi nơi không đi qua `QuoteGateConfig.from_env`.
    """

    from src.agents.domain.quote_risk import STANDARD_PROMOTIONS

    assert STANDARD_PROMOTIONS == frozenset()


@pytest.mark.asyncio
async def test_session_scoped_offer_in_allowlist_is_not_non_standard() -> None:
    """[T6] Offer TVV đã duyệt cho chính phiên này nằm trong allowlist → không chặn."""
    message = "cho em xin voucher 5 triệu"
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message=message,
        canonical=build_canonical_text(message),
        active_offers=[{"display_name": "voucher 5 triệu", "promotion_code": "VF3_VOUCHER"}],
    )

    assert decision.requires_hitl is False


@pytest.mark.asyncio
async def test_offer_outside_allowlist_is_still_blocked() -> None:
    """[T6] Không có record ACTIVE thì lời nhắc ưu đãi vẫn là "ngoài chính sách" → chặn."""
    message = "cho em xin voucher 5 triệu"
    decision = await _gate().evaluate(
        session_id=SESSION,
        user_message=message,
        canonical=build_canonical_text(message),
        active_offers=[],
    )

    assert decision.requires_hitl is True
    assert decision.evaluation["has_non_standard_offer"] is True


# ── Xin lái thử KHÔNG phải một tiếng "ok" ────────────────────────────────────


async def _after_a_delivered_quote(gate) -> dict:
    delivered = await gate.evaluate(
        session_id=SESSION,
        user_message="tư vấn xe cho gia đình bảy người",
        canonical=build_canonical_text("tư vấn xe cho gia đình bảy người"),
        draft_answer="VF 9 phù hợp nhu cầu của anh/chị.",
        recommendation_count=1,
        facts_verified=True,
    )
    assert delivered.evaluation_to_remember is not None
    return delivered.evaluation_to_remember


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["đăng ký lái thử", "đặt lịch lái thử", "dat lich lai thu"])
async def test_xin_lai_thu_khong_bi_doc_thanh_loi_xac_nhan_bao_gia(message: str) -> None:
    """BUG THẬT trên prod 2026-08-28, tìm ra bằng test tích hợp chạy trọn lượt.

    Sau bản đề xuất, khách gõ *"đăng ký lái thử"* và nhận lại `NEXT_STEP_REPLY`:

        "Em có thể đặt lịch lái thử …, hoặc gửi thêm thông tin về màu sắc,
         phiên bản và chính sách bàn giao. Anh/chị muốn xem phần nào trước ạ?"

    Tức hệ mời khách làm đúng cái việc họ VỪA xin. `classify_turn` đọc câu đó
    thành `ACKNOWLEDGMENT` — nó không mang slot mới nào, nên trông giống một
    tiếng "ok". Nhưng một lời XIN VIỆC không phải một lời xác nhận.

    Trả `None` ở nhánh tắt KHÔNG phải là bỏ qua cổng: lượt chảy tiếp vào
    `_build`, tức vẫn được chấm rủi ro đầy đủ. Chỉ là nó không còn được trả lời
    bằng một câu template soạn cho tiếng "ok".
    """

    gate = _gate()
    remembered = await _after_a_delivered_quote(gate)

    decision = await gate.evaluate(
        session_id=SESSION,
        user_message=message,
        canonical=build_canonical_text(message),
        slots_before={},
        slots_after={},
        last_quote_evaluation=remembered,
    )

    assert (decision.turn_type or "").upper() != "ACKNOWLEDGMENT"
    assert "muốn xem phần nào" not in (decision.reply or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ["đăng ký lái thử và giảm 20 triệu", "đặt lịch lái thử trả góp", "cho lái thử rồi bớt cho anh ít"],
)
async def test_xin_lai_thu_kem_mac_ca_van_phai_qua_nguoi(message: str) -> None:
    """Cửa mới KHÔNG được thành đường thả mặc cả.

    Câu vừa xin lái thử vừa xin giảm giá là một câu MẶC CẢ. Bỏ qua nhánh xác
    nhận chỉ có nghĩa "chấm đầy đủ", nên phần mặc cả phải bị chính phép chấm đó
    bắt lại.
    """

    gate = _gate()
    remembered = await _after_a_delivered_quote(gate)

    decision = await gate.evaluate(
        session_id=SESSION,
        user_message=message,
        canonical=build_canonical_text(message),
        slots_before={},
        slots_after={},
        last_quote_evaluation=remembered,
    )

    assert decision.requires_hitl is True, f"câu mặc cả phải qua người: {message!r}"


@pytest.mark.asyncio
async def test_mot_tieng_ok_van_di_duong_cu() -> None:
    """Đường tắt A7-5 vẫn phải sống cho đúng ca nó sinh ra."""

    gate = _gate()
    remembered = await _after_a_delivered_quote(gate)

    decision = await gate.evaluate(
        session_id=SESSION,
        user_message="ok",
        canonical=build_canonical_text("ok"),
        slots_before={},
        slots_after={},
        last_quote_evaluation=remembered,
    )

    assert (decision.turn_type or "").upper() == "ACKNOWLEDGMENT"
    assert decision.requires_hitl is False
