"""Cách khách DIỄN ĐẠT ngân sách phải đổi được danh sách xe gợi ý.

Bug đã quan sát, trên đúng dữ liệu giá của catalog:

    "ô tô điện khoảng 900 triệu" → VF 2 (188tr), VF 3 (278tr), VF 5 (496tr)
    "ô tô điện từ 900 triệu"     → VF 2 (188tr), VF 3 (278tr), VF 5 (496tr)

Hai câu mang hai ý hoàn toàn khác nhau mà nhận về cùng một danh sách, và danh
sách đó là ba mẫu RẺ NHẤT hệ thống — không mẫu nào liên quan tới mức tiền khách
vừa nêu. Chuỗi nhân quả: cả hai câu đều bị đọc thành một TRẦN 900 triệu không
sàn, rồi `_budget_reasons` thưởng điểm theo độ dư ngân sách nên xe càng rẻ càng
lên cao.

Test này đi từ CÂU của khách tới DANH SÁCH xe, qua đúng hai module thật
(`budget_parsing` → `scoring`), trên giá thật đọc từ `data-p150/catalog`.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from src.agents.domain.budget_parsing import parse_budget_range
from src.agents.domain.scoring import ScoringCandidate, ScoringProfile, rank_candidates
from src.agents.domain.values import VehicleType

_CATALOG_DIR = Path(__file__).parents[4] / "data-p150" / "catalog"


def _catalog_cars() -> dict[str, int]:
    """Giá khởi điểm của từng biến thể ô tô đang bán, đọc từ CSV nguồn."""

    names = {
        row["vehicle_id"]: f"{row['model_name']} {row['variant_name']}".strip()
        for row in csv.DictReader((_CATALOG_DIR / "vehicles.csv").open(encoding="utf-8"))
        if row["vehicle_type"] == "CAR" and row["status"] == "ACTIVE"
    }
    prices: dict[str, int] = {}
    for row in csv.DictReader((_CATALOG_DIR / "vehicle_prices.csv").open(encoding="utf-8")):
        name = names.get(row["vehicle_id"])
        if name is None or row["price_type"] != "STARTING_PRICE" or row["status"] != "ACTIVE":
            continue
        prices[name] = int(row["amount_vnd"])
    return prices


CARS = _catalog_cars()
IDS = {name: UUID(int=index + 1) for index, name in enumerate(sorted(CARS))}
NAMES = {vehicle_id: name for name, vehicle_id in IDS.items()}


def _candidate(name: str) -> ScoringCandidate:
    return ScoringCandidate(
        vehicle_id=IDS[name],
        vehicle_type=VehicleType.CAR,
        price_vnd=Decimal(CARS[name]),
        range_km=Decimal(400),
        seat_count=5,
        max_load_kg=None,
        cargo_volume_l=None,
        energy_consumption_per_100km=None,
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=None,
        assertions=(),
        need_tag_links=(),
    )


def _advised_prices(user_message: str) -> list[int]:
    """Giá của những xe được gợi ý cho đúng câu này, theo triệu đồng."""

    budget = parse_budget_range(user_message)
    profile = ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=None if budget.max_vnd is None else Decimal(budget.max_vnd),
        budget_min_vnd=None if budget.min_vnd is None else Decimal(budget.min_vnd),
        passenger_count=None,
        required_range_km=None,
        home_charging=None,
        purpose=None,
        max_load_kg=None,
        habit_need_tags=(),
    )
    ranked = rank_candidates(profile, [_candidate(name) for name in CARS])
    return [CARS[NAMES[item.vehicle_id]] // 1_000_000 for item in ranked]


def test_the_catalog_fixture_matches_the_prices_this_bug_was_reported_with() -> None:
    """Ba mẫu rẻ nhất và hai mẫu quanh 900 triệu phải đúng như báo cáo."""

    assert CARS["VF 2 All New"] == 188_000_000
    assert CARS["VF 3 All New"] == 278_000_000
    assert CARS["VF 5 All New"] == 496_000_000
    assert 898_000_000 in CARS.values()


def test_approximate_budget_advises_models_around_that_amount() -> None:
    """ "khoảng 900 triệu" → chỉ xe trong 800–1.000 triệu, không một xe rẻ hơn."""

    advised = _advised_prices("ô tô điện khoảng 900 triệu")

    assert advised != []
    assert all(800 <= price <= 1_000 for price in advised), advised
    assert 188 not in advised
    assert 278 not in advised
    assert 496 not in advised


def test_a_floor_only_budget_advises_models_at_or_above_that_amount() -> None:
    """ "từ 900 triệu" → chỉ xe từ 900 triệu trở lên, không có trần trên."""

    advised = _advised_prices("ô tô điện từ 900 triệu")

    assert advised != []
    assert all(price >= 900 for price in advised), advised


def test_the_two_phrasings_do_not_produce_the_same_list() -> None:
    """Chính là bug: hai cách nói khác nghĩa mà cho ra cùng một danh sách."""

    assert _advised_prices("ô tô điện khoảng 900 triệu") != _advised_prices("ô tô điện từ 900 triệu")


def test_a_ceiling_only_budget_advises_models_under_that_amount() -> None:
    """ "dưới 300 triệu" → không xe nào vượt 300 triệu."""

    advised = _advised_prices("ô tô điện dưới 300 triệu")

    assert advised != []
    assert all(price <= 300 for price in advised), advised


def test_an_explicit_two_ended_range_still_works() -> None:
    """Ca đã đúng từ lần sửa trước không được vỡ."""

    advised = _advised_prices("ô tô điện 300-700 triệu")

    assert advised != []
    assert all(300 <= price <= 700 for price in advised), advised


@pytest.mark.parametrize(
    "user_message",
    ["ô tô điện khoảng 900 triệu", "ô tô điện từ 900 triệu", "ô tô điện dưới 300 triệu"],
)
def test_no_phrasing_falls_back_to_the_three_cheapest_models(user_message: str) -> None:
    """Không cách diễn đạt nào được lặng lẽ trả về ba mẫu rẻ nhất catalog."""

    assert _advised_prices(user_message) != [188, 278, 496]
