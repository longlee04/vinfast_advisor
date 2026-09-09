"""Khoảng ngân sách phải chi phối CẢ danh sách gợi ý lẫn câu chữ trên thẻ xe.

Bug đã quan sát — khách gõ "giá từ 400 đến 600 triệu" và nhận về:

    VinFast VF 5 All New — 496.000.000 đ — "có giá nằm trong ngân sách..."
    VinFast VF 3 All New — 278.000.000 đ — "có giá nằm trong ngân sách..."
    VinFast VF 2 All New — 188.000.000 đ — "có giá nằm trong ngân sách..."

Hai mẫu cuối nằm dưới đáy khoảng, và tệ hơn: chúng nói với khách rằng giá của chúng
nằm TRONG ngân sách. Sai theo chiều khó phát hiện nhất, vì câu đó nghe bình thường.

Nguyên nhân: bộ lọc Lớp 1 chỉ có TRẦN, nên xe dưới sàn vẫn lọt vào; và
`claim_policy` chỉ biết một cực lệch ngân sách (vượt trần), nên lý do "thấp hơn
khoảng ngân sách" rơi về đúng câu claim của xe đúng ngân sách.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.domain.claim_policy import (
    OVER_BUDGET_NOTE,
    UNDER_BUDGET_NOTE,
    budget_fit_note,
    plan_claims,
)
from src.agents.domain.scoring import ScoringCandidate, ScoringProfile, rank_candidates
from src.agents.domain.values import VehicleType

CATALOG = {"VF 2": 188, "VF 3": 278, "VF 5": 496, "VF 6 Eco": 646, "VF 7": 799}
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


def _advised(minimum: int | None, maximum: int) -> list[str]:
    """Tên xe được gợi ý. Đầu vào là những xe Lớp 1 trả — nó chỉ lọc theo TRẦN."""

    candidates = [_candidate(name) for name, price in CATALOG.items() if price <= maximum]
    return [NAMES[item.vehicle_id] for item in rank_candidates(_profile(minimum, maximum), candidates)]


def _claims(name: str, minimum: int | None, maximum: int) -> list[str]:
    candidates = [_candidate(other) for other, price in CATALOG.items() if price <= maximum]
    ranked = rank_candidates(_profile(minimum, maximum), candidates)
    item = next(one for one in ranked if NAMES[one.vehicle_id] == name)
    return [claim.text for claim in plan_claims([r.render() for r in item.reasons])]


# ── Bug gốc ───────────────────────────────────────────────────────────────────


def test_a_budget_range_does_not_advise_models_far_below_its_floor() -> None:
    """ "Từ 400 đến 600 triệu" — một mẫu 188 triệu không phải câu trả lời."""

    advised = _advised(400, 600)

    assert advised == ["VF 5"]
    assert "VF 2" not in advised
    assert "VF 3" not in advised


def test_a_model_below_the_floor_never_claims_to_be_inside_the_budget() -> None:
    """Câu claim phải giữ đúng cực của lý do chấm điểm.

    Khoảng 850–1.000 triệu không có mẫu nào trong catalog thử nghiệm, nên VF 7
    (799 triệu) lọt vào theo lớp dự phòng — đúng lúc cần soi câu chữ của một mẫu
    dưới sàn.
    """

    claims = _claims("VF 7", 850, 1000)

    assert "có mức giá dưới khoảng ngân sách anh/chị dự tính" in claims
    assert "có giá nằm trong ngân sách anh/chị dự tính" not in claims


def test_a_model_inside_the_range_leaves_no_room_for_one_below_the_floor() -> None:
    """Còn mẫu ĐÚNG trong khoảng thì mẫu dưới sàn không được chiếm suất nào.

    Bug đã quan sát: "khoảng 900 triệu" (tức 800–1.000) vẫn nhặt về một mẫu 646
    triệu cho suất thứ ba, vì biên ±20% của nhãn hiển thị bị dùng luôn làm bộ lọc
    danh sách — nới hai lần trên một khoảng vốn đã là biên ±100 triệu.
    """

    advised = _advised(300, 650)

    assert advised == ["VF 5", "VF 6 Eco"]
    assert "VF 3" not in advised


def test_a_model_inside_the_range_still_claims_it_is_inside() -> None:
    claims = _claims("VF 5", 400, 600)

    assert "có giá nằm trong ngân sách anh/chị dự tính" in claims


# ── Không có sàn thì không đổi gì ─────────────────────────────────────────────


def test_a_ceiling_only_budget_lists_every_model_under_the_ceiling() -> None:
    """Phần lớn khách chỉ nói trần — và họ phải thấy ĐỦ xe dưới trần đó.

    Trước đây câu này khoá đúng ba tên (`["VF 2", "VF 3", "VF 5"]`) vì
    `rank_candidates` cắt `[:3]`. VF 6 Eco (646tr) cũng dưới trần 700tr và không
    bị tiêu chí nào loại — nó biến mất chỉ vì đứng thứ tư.
    """

    # So sánh theo TẬP, không theo thứ tự: câu này khoá tính ĐẦY ĐỦ. Thứ tự do
    # `closeness` quyết định (xe gần trần lên trước — bug Sếp báo 2026-08-21:
    # trần 500tr mà xe dưới 200tr xếp đầu), và đó là hợp đồng của test khác.
    assert sorted(_advised(None, 700)) == ["VF 2", "VF 3", "VF 5", "VF 6 Eco"]


# ── Không bỏ trắng danh sách ─────────────────────────────────────────────────


def test_an_empty_band_still_returns_what_the_catalog_has() -> None:
    """Hết mẫu trong biên thì trả những gì có, kèm nhãn — không trả danh sách rỗng."""

    advised = _advised(900, 1000)

    assert advised != []


# ── Nhãn hiển thị ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("price", "minimum", "maximum", "expected"),
    [
        # Trong khoảng → không nhãn.
        (496, 400, 600, None),
        # Lệch trong biên 20% → "một chút".
        (699, 300, 650, OVER_BUDGET_NOTE),
        (278, 300, 650, UNDER_BUDGET_NOTE),
        # Lệch quá biên → vẫn có nhãn, nhưng không gọi là "một chút".
        (188, 400, 600, "(thấp hơn ngân sách)"),
        (1348, 400, 600, "(cao hơn ngân sách)"),
    ],
)
def test_every_out_of_range_price_gets_a_label(price: int, minimum: int, maximum: int, expected: str | None) -> None:
    """Bản đầu im lặng khi lệch NHIỀU — đúng chiều ngược với việc cần cảnh báo."""

    note = budget_fit_note(
        price_vnd=Decimal(price * 1_000_000),
        budget_min_vnd=Decimal(minimum * 1_000_000),
        budget_max_vnd=Decimal(maximum * 1_000_000),
    )

    assert note == expected
