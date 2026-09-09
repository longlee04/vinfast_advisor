"""[A7-9] Giá lăn bánh chạy tự động; TCO, mặc cả và trả góp tự chọn qua người duyệt.

Hướng nguy hiểm của module này là cho một câu MẶC CẢ lọt vào nhánh tự động — khi
đó agent tự thương lượng giá với khách. Hướng nguy hiểm thứ hai là tính phí theo
một tỉnh khách không hề nêu.

`TCO_ESTIMATE_LOOKUP` cố ý nằm ở nhánh HITL: `docs/vinfast-agent-mvp.md` §A7 xếp
TCO vào bốn loại câu trả lời bắt buộc có người duyệt, và tiêu chí hoàn thành 3
ghi cam kết đó "không có ngoại lệ".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.pricing_intent import (
    PricingIntent,
    PricingRoute,
    RiskTier,
    classify_pricing_intent,
    detect_province,
    route_pricing_question,
)
from src.agents.prompts.pricing_reply import (
    MISSING_PROVINCE_QUESTION,
    render_on_road_price,
)
from src.agents.tools.on_road_price import (
    OnRoadFeeAssumptions,
    vinfast_on_road_price_v1,
)

CAR_FEES = OnRoadFeeAssumptions(
    region_code="VN",
    registration_fee_percent=Decimal("0.00"),
    registration_fee_flat_vnd=Decimal(0),
    plate_fee_vnd=Decimal(20_000_000),
    mandatory_insurance_vnd_per_year=Decimal(480_000),
)


def _decide(message: str, *, variant: object | None = "VF 5 All New"):
    """Phân loại rồi route — đúng hai bước mà graph chạy."""

    canonical = build_canonical_text(message)
    return route_pricing_question(
        intent=classify_pricing_intent(message, canonical),
        vehicle_variant=variant,
        province=detect_province(message, canonical),
    )


# ── Các case bắt buộc của đặc tả ──────────────────────────────────────────────


def test_on_road_price_with_variant_and_province_runs_the_tool_without_hitl() -> None:
    decision = _decide("giá lăn bánh vf5 ở hà nội bao nhiêu")

    assert decision.intent is PricingIntent.ON_ROAD_PRICE_LOOKUP
    assert decision.route is PricingRoute.AUTO_TOOL_CALL
    assert decision.risk_tier is RiskTier.LOW
    assert decision.missing_slots == ()


def test_on_road_price_without_a_province_asks_instead_of_guessing() -> None:
    """Phí trước bạ và phí biển số khác nhau theo tỉnh.

    Lấy đại một tỉnh mặc định là gửi cho khách con số của địa phương khác — SAI,
    chứ không phải thiếu. Vì vậy thiếu tỉnh thì hỏi, và tuyệt đối không gọi tool.
    """

    decision = _decide("giá lăn bánh vf5 bao nhiêu")

    assert decision.route is PricingRoute.SLOT_FILLING
    assert decision.missing_slots == ("province",)
    assert decision.resolved_slots is None
    assert "tỉnh/thành nào" in MISSING_PROVINCE_QUESTION


def test_asking_for_a_discount_alongside_the_on_road_price_still_needs_a_human() -> None:
    """Một câu vừa hỏi vừa mặc cả thì phần mặc cả quyết định."""

    decision = _decide("giá lăn bánh vf5 ở hà nội, giảm cho em được không")

    assert decision.intent is PricingIntent.PRICE_NEGOTIATION
    assert decision.route is PricingRoute.HITL_REQUIRED
    assert decision.risk_tier is RiskTier.HIGH


def test_a_tco_question_stays_on_the_human_review_path() -> None:
    """Quyết định đã cân nhắc, không phải bỏ sót.

    TCO là ước tính chồng nhiều tầng giả định (giá điện, chu kỳ bảo dưỡng, số km),
    và PRD xếp nó vào bốn loại bắt buộc có tư vấn viên duyệt hoặc hiệu chỉnh
    trước khi con số tới khách.
    """

    decision = _decide("chi phí sở hữu vf5 thế nào")

    assert decision.intent is PricingIntent.TCO_ESTIMATE_LOOKUP
    assert decision.route is PricingRoute.HITL_REQUIRED
    assert decision.risk_tier is RiskTier.HIGH


def test_a_custom_financing_question_stays_on_the_human_review_path() -> None:
    decision = _decide("mua vf5 trả góp lãi suất bao nhiêu")

    assert decision.intent is PricingIntent.CUSTOM_FINANCING
    assert decision.route is PricingRoute.HITL_REQUIRED
    assert decision.risk_tier is RiskTier.HIGH


def test_missing_variant_blocks_the_on_road_calculation() -> None:
    decision = _decide("giá lăn bánh ở hà nội bao nhiêu", variant=None)

    assert decision.route is PricingRoute.SLOT_FILLING
    assert "vehicle_variant" in decision.missing_slots


# ── Biên dễ sai ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("giá lăn bánh vf5 tại tphcm", "HCM"),
        ("mua ở sài gòn thì lăn bánh bao nhiêu", "HCM"),
        ("em ở đà nẵng", "DN"),
        ("em nhìn xe thấy đẹp", None),
    ],
)
def test_province_detection_matches_on_word_boundaries(message: str, expected) -> None:
    """ "hn" tìm theo chuỗi con sẽ khớp vào "nhìn" và gán nhầm tỉnh cho khách."""

    assert detect_province(message, build_canonical_text(message)) is expected


def test_a_plain_listed_price_question_is_left_alone() -> None:
    """Không nuốt câu hỏi giá niêm yết vốn đã chạy đúng (A7-8)."""

    assert classify_pricing_intent("vf5 giá bao nhiêu", build_canonical_text("vf5 giá bao nhiêu")) is PricingIntent.NONE


def test_a_default_instalment_question_is_not_custom_financing() -> None:
    """ "trả góp" trần là tra cứu gói mặc định; chỉ lãi suất/kỳ hạn tự chọn mới chặn."""

    assert (
        classify_pricing_intent("vf5 có hỗ trợ trả góp không", build_canonical_text("vf5 có hỗ trợ trả góp không"))
        is PricingIntent.NONE
    )


# ── Công thức giá lăn bánh ────────────────────────────────────────────────────


def test_the_on_road_total_is_the_sum_of_its_own_breakdown() -> None:
    """Bảng cộng lại phải đúng bằng tổng — khách sẽ tự cộng lại."""

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=CAR_FEES)

    assert (
        breakdown.listed_price_vnd
        + breakdown.registration_fee_vnd
        + breakdown.plate_fee_vnd
        + breakdown.mandatory_insurance_vnd
    ) == breakdown.total_vnd
    assert breakdown.total_vnd == Decimal(456_480_000)


def test_mandatory_insurance_counts_exactly_one_year() -> None:
    """TNDS là khoản để xe ra biển; các năm sau thuộc chi phí sở hữu (tool TCO).

    Cộng cả chu kỳ vào đây sẽ đội giá lăn bánh bằng khoản khách chưa phải trả.
    """

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=CAR_FEES)

    assert breakdown.mandatory_insurance_vnd == CAR_FEES.mandatory_insurance_vnd_per_year


def test_a_percentage_registration_fee_applies_to_the_listed_price() -> None:
    fees = OnRoadFeeAssumptions(
        region_code="VN",
        registration_fee_percent=Decimal("2.00"),
        registration_fee_flat_vnd=Decimal(0),
        plate_fee_vnd=Decimal(2_000_000),
        mandatory_insurance_vnd_per_year=Decimal(66_000),
    )

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(50_000_000), province="HN", fees=fees)

    assert breakdown.registration_fee_vnd == Decimal(1_000_000)


def test_a_national_fee_table_is_declared_as_such_in_the_answer() -> None:
    """`tco_assumptions` hiện CHỈ có dòng `region_code='VN'`.

    Để khách tưởng con số đã tính theo tỉnh mình trong khi đang dùng biểu toàn
    quốc là hiểu sai một khoản tiền thật.
    """

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=CAR_FEES)

    assert breakdown.province_specific is False
    answer = render_on_road_price(breakdown, "VF 5 All New")
    assert "mức chung toàn quốc" in answer
    assert "436.000.000" in answer and "456.480.000" in answer


def test_the_on_road_answer_follows_the_shared_markdown_format() -> None:
    """Cùng bố cục với nhánh tra cứu xe: bullet `* `, tên khoản phí in đậm.

    Câu trả lời giá lăn bánh có bốn khoản phí — đúng loại nội dung mà format
    chung sinh ra để phục vụ. Trước đây nó tự viết bullet `- ` không in đậm, và
    tầng hiển thị (chỉ hiểu MỘT bộ quy tắc) đổ cả bảng phí về một dòng chữ.
    """

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=CAR_FEES)

    answer = render_on_road_price(breakdown, "VF 5 All New")
    bullets = [line for line in answer.splitlines() if line.startswith("* ")]

    assert len(bullets) == 4
    assert bullets[0] == "* **Giá niêm yết**: 436.000.000 đồng"
    assert all(bullet.startswith("* **") and "**: " in bullet for bullet in bullets)
    assert "**Tổng giá lăn bánh**: " in answer
    assert answer.startswith("Dạ, giá lăn bánh **VF 5 All New** tại **Hà Nội**:")
    # Bố cục sống bằng dòng trống giữa các khối — dồn lại là đúng lỗi gốc.
    assert "\n\n" in answer


def test_the_on_road_answer_carries_no_estimate_disclaimer() -> None:
    """Số tính từ công thức cố định, không phải ước tính như TCO."""

    breakdown = vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=CAR_FEES)

    assert "ước tính" not in render_on_road_price(breakdown, "VF 5 All New")


def test_negative_fees_are_rejected_instead_of_silently_lowering_the_total() -> None:
    fees = OnRoadFeeAssumptions(
        region_code="VN",
        registration_fee_percent=Decimal("0"),
        registration_fee_flat_vnd=Decimal(0),
        plate_fee_vnd=Decimal(-1),
        mandatory_insurance_vnd_per_year=Decimal(0),
    )

    with pytest.raises(ValueError):
        vinfast_on_road_price_v1(listed_price_vnd=Decimal(436_000_000), province="HN", fees=fees)
