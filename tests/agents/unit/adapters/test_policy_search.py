"""Pure scope parsing rules used before policy ranking."""

from datetime import date

from src.agents.adapters.policy_search import (
    _eligibility_date,
    _ownership_for_query,
    _topics_for_query,
    _usage_for_query,
)


def test_policy_query_extracts_customer_eligibility_date() -> None:
    assert _eligibility_date("Xe xuất hóa đơn 14/08/2025") == date(2025, 8, 14)
    assert _eligibility_date("ngày 31/02/2025") is None


def test_warranty_topic_cannot_fall_through_to_charging_or_promotion() -> None:
    assert _topics_for_query("Pin VF5 bảo hành bao lâu?") == ("battery_warranty",)
    assert _topics_for_query("Bảo hành xe VF5") == ("vehicle_warranty",)
    assert _topics_for_query("ưu đãi sạc pin") == ("battery_charging",)


def test_battery_swap_and_rental_are_separate_from_warranty() -> None:
    assert _topics_for_query("Đổi pin MAX thế nào?") == ("battery_swap", "battery_replacement")
    assert _topics_for_query("Thuê pin Vento S") == ("battery_rental", "battery_contract")


def test_usage_and_battery_ownership_are_explicit_applicability_dimensions() -> None:
    assert _usage_for_query("VF5 chạy Grab thì bảo hành sao?") == "COMMERCIAL"
    assert _usage_for_query("xe dùng cho gia đình") == "STANDARD"
    assert _usage_for_query("bảo hành VF5") is None
    assert _ownership_for_query("Tôi thuê pin Vento S") == "SUBSCRIPTION"
    assert _ownership_for_query("mua pin rời") == "PURCHASE"
    assert _ownership_for_query("pin kèm xe") == "INCLUDED"
