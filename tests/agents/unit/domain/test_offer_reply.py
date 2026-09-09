"""Cấp ưu đãi xong phải BÁO khách, rồi HỎI mới tính lại — không tự trừ.

Sếp 2026-08-27: *"khi cấp thì không phải trừ thẳng rồi tính TCO mà sau khi duyệt
xong phải có thông báo cho khách… nếu về giá thì phải có hiện từ đi còn bao
nhiêu… rồi hỏi thêm anh/chị có để em tính giá TCO cho mình không"*.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.offer_reply import (
    CostConsent,
    classify_cost_consent,
    discount_amount,
    offer_announcement,
)


def test_a_money_offer_shows_both_the_cut_and_what_is_left() -> None:
    """Chỉ nói mức giảm là bắt khách tự trừ — mà con số họ tự trừ ra là con số
    họ đem đi so với đại lý."""

    text = offer_announcement(
        {"display_name": "UU-DAI-T8", "amount_vnd": 50_000_000},
        vehicle_name="VF 6 Eco",
        base_price_vnd=Decimal("646000000"),
    )

    assert "giảm 50.000.000 đồng" in text
    assert "giá VF 6 Eco còn 596.000.000 đồng" in text


def test_a_percent_offer_is_turned_into_money() -> None:
    """ "Giảm 5%" chưa nói gì cho tới khi biết 5% của bao nhiêu."""

    text = offer_announcement({"percent": "5"}, base_price_vnd=Decimal("899000000"))

    assert "giảm 44.950.000 đồng" in text


def test_a_percent_offer_without_a_base_price_says_no_number() -> None:
    """Thiếu giá gốc thì KHÔNG đoán: một con số đoán ra là một lời hứa sai."""

    assert discount_amount({"percent": "5"}, base_price_vnd=None) is None


def test_a_gift_offer_names_the_gift() -> None:
    text = offer_announcement({"gift_code": "Bộ sạc treo tường"})

    assert "Quà tặng" in text
    assert "Bộ sạc treo tường" in text


def test_a_valueless_offer_promises_no_number() -> None:
    """Ca THẬT: cả hai bản ghi `session_offers` trên prod đều rỗng giá trị.

    Nói "được giảm" ở đây là hứa một con số không tồn tại.
    """

    text = offer_announcement(
        {"display_name": "KHUYEN-MAI-EVO-THUE-PIN", "percent": None, "amount_vnd": None, "new_value": ""}
    )

    assert "giảm" not in text.split("Anh/chị")[0]
    assert "tư vấn viên trao đổi thêm" in text


def test_every_announcement_ends_by_asking_before_recalculating() -> None:
    """KHÔNG tự trừ rồi thay số. Một cái tổng lặng lẽ đổi giữa cuộc nói chuyện là
    chỗ mất niềm tin nhanh nhất."""

    for offer in ({"amount_vnd": 10_000_000}, {"gift_code": "Sạc"}, {"display_name": "X"}):
        text = offer_announcement(offer, base_price_vnd=Decimal("600000000"))
        assert text.rstrip().endswith("không ạ?")


@pytest.mark.parametrize(
    "user_message, expected",
    [
        ("có em", CostConsent.AGREE),
        ("vâng ạ", CostConsent.AGREE),
        ("ok em tính đi", CostConsent.AGREE),
        ("tính giúp anh", CostConsent.AGREE),
        ("thôi khỏi em", CostConsent.DECLINE),
        ("không cần đâu", CostConsent.DECLINE),
        ("để sau nhé", CostConsent.DECLINE),
    ],
)
def test_the_consent_reader_handles_the_common_replies(user_message: str, expected: CostConsent) -> None:
    assert classify_cost_consent(build_canonical_text(user_message)) is expected


@pytest.mark.parametrize("user_message", ["anh xem lại đã", "anh suy nghĩ thêm đã", "anh muốn xem xe khác"])
def test_a_postponement_is_never_read_as_consent(user_message: str) -> None:
    """Bỏ dấu thì "đã" và "dạ" TRÙNG NHAU.

    Không neo tiếng ừ hử vào đầu câu thì "anh xem lại đã" thành lời đồng ý, và ta
    thay một con số khách chưa xin. Cùng họ bẫy với "đặt"/"đắt" ở `concern_reply`.
    """

    assert classify_cost_consent(build_canonical_text(user_message)) is CostConsent.UNCLEAR


# ── Giá khuyến mãi của catalog ───────────────────────────────────────────────


def test_a_catalog_promotion_price_beats_the_list_price() -> None:
    """Đo trên prod 2026-08-27: 8 dòng `PROMOTION_PRICE` ACTIVE chưa từng tới khách.

    Klara Neo niêm yết 36.000.000 mà đang bán 28.800.000 — khách vẫn nhận con số
    cũ, vì danh sách ưu tiên giá không có mã này.
    """

    from src.agents.domain.values import VehicleType
    from src.agents.tools.tco import BatteryPolicyInput, VehicleTcoInput, _purchase_price

    data = VehicleTcoInput(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        prices_vnd={"STARTING_PRICE": Decimal("36000000"), "PROMOTION_PRICE": Decimal("28800000")},
        assumptions=(),
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
    )

    assert _purchase_price(data) == (Decimal("28800000"), None)


def test_a_promotion_price_above_the_list_price_is_ignored() -> None:
    """Một "khuyến mãi" đắt hơn giá niêm yết là dữ liệu hỏng.

    Không chốt lại thì khách phải trả NHIỀU HƠN vì có khuyến mãi.
    """

    from src.agents.domain.values import VehicleType
    from src.agents.tools.tco import BatteryPolicyInput, VehicleTcoInput, _purchase_price

    data = VehicleTcoInput(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        prices_vnd={"STARTING_PRICE": Decimal("30000000"), "PROMOTION_PRICE": Decimal("35000000")},
        assumptions=(),
        battery_policy=BatteryPolicyInput(ownership_model="NOT_APPLICABLE"),
    )

    assert _purchase_price(data) == (Decimal("30000000"), None)


def test_the_no_offer_notice_does_not_mention_a_discount_that_does_not_exist() -> None:
    """Tư vấn viên vừa TỪ CHỐI — nhắc "theo ưu đãi này" là nhắc thứ vừa bị từ chối.

    Sếp 2026-08-27: vẫn phải báo khách việc đang chạy và mở tiếp một lối đi được
    ngay. Im lặng ở đây là bỏ rơi khách đúng lúc họ đang chờ.
    """

    from src.agents.domain.offer_reply import advisor_still_looking_notice

    text = advisor_still_looking_notice()

    assert "đang tìm" in text
    assert "ưu đãi này" not in text
    assert "chi phí lăn bánh" in text
    assert text.rstrip().endswith("không ạ?")


def test_the_no_offer_notice_promises_nothing() -> None:
    """Hứa một thứ tư vấn viên vừa từ chối là đặt vào miệng người khác lời cam kết."""

    from src.agents.domain.offer_reply import advisor_still_looking_notice

    text = advisor_still_looking_notice().casefold()

    assert "sẽ giảm" not in text
    assert "chắc chắn" not in text
