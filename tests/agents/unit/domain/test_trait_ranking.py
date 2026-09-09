"""Khách xin "cốp rộng hơn" thì danh sách phải xếp theo dung tích cốp.

Sếp 2026-08-27 ("sửa luôn đi"): bản trước chỉ ĐỌC được cảm quan mà không xếp
hạng theo nó, nên `REVISE_RESULTS` chỉ loại mấy chiếc vừa xem rồi bốc tiếp theo
đúng bộ lọc cũ — ra ba chiếc khác, cốp cũng bé y như vậy.

Đây là trục XẾP HẠNG, không phải bộ lọc. Ngưỡng của `perceptual_traits`
(376 lít) đo cho việc khác — quyết định pitch có được PHÉP NÓI "cốp rộng" hay
không — và dùng nó để lọc là dựng một tiêu chí chia đôi tập ứng viên mà khách
chưa hề nêu.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.agents.domain.scoring import ScoringCandidate, ScoringProfile, rank_candidates
from src.agents.domain.values import VehicleType

SMALL = UUID("20000000-0000-0000-0000-000000000001")
MEDIUM = UUID("20000000-0000-0000-0000-000000000002")
LARGE = UUID("20000000-0000-0000-0000-000000000003")


def _candidate(vehicle_id: UUID, cargo: str | None) -> ScoringCandidate:
    return ScoringCandidate(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.CAR,
        price_vnd=Decimal("500000000"),
        range_km=Decimal("300"),
        seat_count=5,
        max_load_kg=None,
        cargo_volume_l=Decimal(cargo) if cargo is not None else None,
        energy_consumption_per_100km=None,
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=None,
        assertions=(),
        need_tag_links=(),
    )


def _profile(**overrides: object) -> ScoringProfile:
    base = {
        "vehicle_type": VehicleType.CAR,
        "budget_max_vnd": Decimal("900000000"),
        "passenger_count": None,
        "required_range_km": None,
        "home_charging": None,
        "purpose": None,
        "max_load_kg": None,
        "habit_need_tags": (),
    }
    return ScoringProfile(**{**base, **overrides})


def test_a_cargo_request_puts_the_biggest_boot_first() -> None:
    candidates = [_candidate(SMALL, "212"), _candidate(LARGE, "446"), _candidate(MEDIUM, "376")]

    ranked = rank_candidates(_profile(preferred_traits=("TRAIT_LARGE_CARGO",)), candidates)

    assert [item.vehicle_id for item in ranked] == [LARGE, MEDIUM, SMALL]


def test_nothing_is_filtered_out_by_the_trait_axis() -> None:
    """Xe cốp bé vẫn còn trong danh sách, chỉ đứng sau.

    Lọc theo ngưỡng 376 lít sẽ vứt luôn chiếc 212 lít — trong khi khách chỉ nói
    họ muốn cốp to HƠN, không nói họ từ chối mọi xe dưới một con số.
    """

    candidates = [_candidate(SMALL, "212"), _candidate(LARGE, "446")]

    ranked = rank_candidates(_profile(preferred_traits=("TRAIT_LARGE_CARGO",)), candidates)

    assert {item.vehicle_id for item in ranked} == {SMALL, LARGE}


def test_a_vehicle_without_the_number_goes_last_not_zero() -> None:
    """Thiếu dữ liệu không phải là kém — nhưng cũng không được lên đầu."""

    candidates = [_candidate(SMALL, None), _candidate(MEDIUM, "376")]

    ranked = rank_candidates(_profile(preferred_traits=("TRAIT_LARGE_CARGO",)), candidates)

    assert [item.vehicle_id for item in ranked] == [MEDIUM, SMALL]


def test_a_trait_without_a_ranking_field_changes_nothing() -> None:
    """`TRAIT_SUV_STANCE` không phân biệt được xe (10/11 mẫu là SUV).

    `perceptual_traits` đã ghi rõ điều đó; xếp hạng theo nó là xếp theo hằng số.
    """

    candidates = [_candidate(SMALL, "212"), _candidate(LARGE, "446")]

    with_trait = rank_candidates(_profile(preferred_traits=("TRAIT_SUV_STANCE",)), candidates)
    without = rank_candidates(_profile(), candidates)

    assert [item.vehicle_id for item in with_trait] == [item.vehicle_id for item in without]


def test_no_requested_trait_leaves_the_old_order_untouched() -> None:
    candidates = [_candidate(SMALL, "212"), _candidate(LARGE, "446")]

    assert [item.vehicle_id for item in rank_candidates(_profile(), candidates)] == [
        item.vehicle_id for item in rank_candidates(_profile(preferred_traits=()), candidates)
    ]
