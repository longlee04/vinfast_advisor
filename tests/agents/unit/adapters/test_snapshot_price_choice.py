"""Hồ sơ gửi tư vấn viên phải mang ĐÚNG giá mà bảng chi phí dùng."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src.agents.adapters.snapshot_source import _price_fact

PRICE_ID = uuid4()
OTHER_ID = uuid4()


def _price(price_type: str, amount: int, price_id=PRICE_ID) -> SimpleNamespace:
    return SimpleNamespace(price_type=price_type, amount_vnd=amount, price_id=price_id)


def test_battery_included_wins_over_the_rent_battery_price() -> None:
    """`STARTING_PRICE` của xe máy là giá THUÊ PIN — hình thức ngừng 1/3/2025.

    Prod 2026-08-27: `Flazz Max` pitch 12.500.000đ, bảng chi phí tính trên
    17.300.000đ. Bảy dòng xe máy lệch như vậy.
    """

    fact = _price_fact([_price("STARTING_PRICE", 12_500_000, OTHER_ID), _price("BATTERY_INCLUDED", 17_300_000)])

    assert fact is not None
    assert fact.value_text == "17300000"
    assert fact.source_id == PRICE_ID


def test_rent_price_is_used_when_no_battery_included_row_exists() -> None:
    fact = _price_fact([_price("STARTING_PRICE", 14_200_000)])

    assert fact is not None
    assert fact.value_text == "14200000"


def test_no_supported_price_returns_nothing() -> None:
    assert _price_fact([_price("PROMOTION_PRICE", 9_000_000)]) is None
