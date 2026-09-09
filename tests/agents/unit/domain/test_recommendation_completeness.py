"""Số lượng xe gợi ý phải khớp số xe THOẢ ĐIỀU KIỆN, không phải một con số cố định.

Bug đã quan sát trên hội thoại thật:

    khách: xe từ 200 - 900 triệu  → VF 8 (899tr), VF 3 (278tr), VF 6 Plus (699tr)
    khách: xe dưới 900 triệu      → NGUYÊN VẸN ba xe đó

Hai câu hỏi khác nhau, cùng một câu trả lời ba xe — và cả hai đều thiếu VF 2,
VF 5, VF 6 Eco, VF 7 dù bốn mẫu đó cũng nằm trong khoảng. Không tiêu chí nào loại
chúng: `rank_candidates` cắt `[:3]`, nên mẫu thứ tư trở đi biến mất vì THỨ HẠNG.
Thứ hạng không phải điều kiện lọc.

Đo ở `rank_candidates` vì đó là điểm nghẽn DUY NHẤT của số lượng trong cả
pipeline: `catalog_reader.hard_filter` không có `LIMIT` nào, `route_after_layer1`
bỏ qua nhánh `narrow` cho hồ sơ giá-trước, và `chain._recommended_vehicles` dựng
đúng một thẻ cho mỗi pitch.

Các test dưới đây KHÔNG hardcode số xe: chúng đếm trên chính `CATALOG` của file
để một mẫu mới thêm vào danh mục cũng phải xuất hiện trong kết quả.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.scoring import (
    MAX_RECOMMENDATIONS,
    ScoringCandidate,
    ScoringProfile,
    rank_candidates,
)
from src.agents.domain.values import VehicleType

#: Giá thật của danh mục ô tô, triệu đồng — cùng bộ số đã xuất hiện trong hội
#: thoại tái hiện bug.
CATALOG: dict[str, int] = {
    "VF 2": 188,
    "VF 3": 278,
    "VF 5": 496,
    "VF 6 Eco": 646,
    "VF 6 Plus": 699,
    "VF 7": 740,
    "VF 8": 899,
    "VF 9": 1_499,
}
IDS = {name: UUID(int=index + 1) for index, name in enumerate(CATALOG)}
NAMES = {vehicle_id: name for name, vehicle_id in IDS.items()}


def _candidate(name: str) -> ScoringCandidate:
    return ScoringCandidate(
        vehicle_id=IDS[name],
        vehicle_type=VehicleType.CAR,
        price_vnd=Decimal(CATALOG[name] * 1_000_000),
        seat_count=5,
        range_km=Decimal(300),
        max_load_kg=None,
        cargo_volume_l=None,
        energy_consumption_per_100km=None,
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        need_tag_links=(),
        assertions=(),
        over_budget_percent=None,
    )


def _profile(minimum: int | None, maximum: int) -> ScoringProfile:
    return ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal(maximum * 1_000_000),
        budget_min_vnd=None if minimum is None else Decimal(minimum * 1_000_000),
        passenger_count=None,
        required_range_km=None,
        home_charging=None,
        purpose=None,
        max_load_kg=None,
        habit_need_tags=(),
    )


def _advised(minimum: int | None, maximum: int) -> set[str]:
    """Tên xe được gợi ý. Đầu vào là những xe Lớp 1 trả — nó chỉ lọc theo TRẦN."""

    candidates = [_candidate(name) for name, price in CATALOG.items() if price <= maximum]
    return {NAMES[item.vehicle_id] for item in rank_candidates(_profile(minimum, maximum), candidates)}


def _eligible(minimum: int | None, maximum: int) -> set[str]:
    """Xe thực sự thoả khoảng giá, tính thẳng từ `CATALOG` — không chép tay."""

    floor = 0 if minimum is None else minimum
    return {name for name, price in CATALOG.items() if floor <= price <= maximum}


# ── Hai truy vấn của kịch bản bug ─────────────────────────────────────────────


def test_a_budget_range_returns_every_model_inside_it() -> None:
    """ "xe từ 200 - 900 triệu" — sáu mẫu thoả, trước đây chỉ ba mẫu ra."""

    advised = _advised(200, 900)

    assert advised == _eligible(200, 900)
    assert len(advised) > 3, "khong duoc cat theo thu hang nua"


def test_a_ceiling_only_query_returns_every_model_under_it() -> None:
    """ "xe dưới 900 triệu" — không có sàn nên VF 2 cũng phải có mặt."""

    advised = _advised(None, 900)

    assert advised == _eligible(None, 900)
    assert "VF 2" in advised


def test_the_two_queries_no_longer_collapse_to_the_same_answer() -> None:
    """Bằng chứng trực tiếp nhất của bug: hai câu hỏi khác nhau, cùng một đáp án.

    Chúng khác nhau đúng ở phần dưới sàn 200 triệu, tức ở VF 2 (188tr).
    """

    assert _advised(None, 900) - _advised(200, 900) == {"VF 2"}


# ── Mốc giá khác hẳn: bản sửa phải đúng tổng quát ─────────────────────────────


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        (None, 300),  # "xe dưới 300 triệu"
        (600, 1_499),  # "xe từ 600 triệu trở lên"
        (400, 700),
        (None, 1_499),  # cả danh mục
    ],
)
def test_every_budget_band_returns_exactly_the_models_that_qualify(minimum: int | None, maximum: int) -> None:
    """Bản sửa nằm ở tầng chung, nên nó phải đúng với MỌI khoảng, không riêng 900tr."""

    assert _advised(minimum, maximum) == _eligible(minimum, maximum)


# ── Trần an toàn ─────────────────────────────────────────────────────────────


def test_the_remaining_cap_is_far_above_the_current_catalog() -> None:
    """Trần còn lại chỉ để chặn danh mục rất lớn, không được chạm tới catalog hiện tại."""

    assert MAX_RECOMMENDATIONS > len(CATALOG)
    assert len(_advised(None, 1_499)) == len(CATALOG)
