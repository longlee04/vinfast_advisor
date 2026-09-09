"""seed_catalog phai phu du 11 bang, dung thu tu FK."""

from __future__ import annotations

import pytest

from src.products.domain.tco import KHU_VUC_I, KHU_VUC_II
from src.products.infrastructure.csv_import import load_all
from src.products.infrastructure.seed_catalog import _seed


class _RecordingSession:
    """Ghi lai ten bang cua moi INSERT, khong cham DB that."""

    def __init__(self) -> None:
        self.tables: list[str] = []

    async def execute(self, statement):  # noqa: ANN001
        self.tables.append(statement.table.name)
        return None


@pytest.mark.asyncio
async def test_seed_covers_all_eleven_tables() -> None:
    session = _RecordingSession()
    counts = await _seed(session)

    expected = {
        "vehicles",
        "cars",
        "motorbikes",
        "vehicle_prices",
        "promotions",
        "promotion_vehicles",
        "battery_policies",
        "feature_definitions",
        "vehicle_feature_flags",
        "feature_need_tags",
        "tco_assumptions",
    }
    assert expected.issubset(set(session.tables))
    assert counts["feature_need_tags"] > 0
    assert counts["tco_assumptions"] > 0


@pytest.mark.asyncio
async def test_feature_need_tags_seeded_after_feature_definitions() -> None:
    # FK feature_need_tags.feature_code -> feature_definitions.feature_code
    session = _RecordingSession()
    await _seed(session)

    assert session.tables.index("feature_definitions") < session.tables.index("feature_need_tags")


@pytest.mark.asyncio
async def test_seed_counts_match_csv_row_counts() -> None:
    session = _RecordingSession()
    counts = await _seed(session)
    dataset = load_all()

    assert counts["tco_assumptions"] == len(dataset.tco_assumptions)
    assert counts["feature_need_tags"] == len(dataset.feature_need_tags)


#: Lệ phí biển số ô tô theo Thông tư 155/2025/TT-BTC, chênh nhau 100 lần giữa
#: hai khu vực. Đây là con số đi THẲNG vào công thức giá lăn bánh, nên lấy nhầm
#: dòng là báo sai cho khách gần 14 triệu đồng.
_CAR_PLATE_FEE_BY_REGION = {KHU_VUC_I: 14_000_000, KHU_VUC_II: 140_000}


def _car_assumption(dataset, region_code: str):
    """Dòng ô tô của ĐÚNG một khu vực.

    Chọn theo `(vehicle_type, region_code)` chứ không phải `next(vehicle_type ==
    "CAR")`: từ migration `a1b2c3d4e5f6` bảng có HAI dòng ô tô, nên `next()` lấy
    dòng nào là tuỳ thứ tự CSV — test sẽ xanh hay đỏ theo một chi tiết không ai
    coi là hợp đồng.
    """

    return next(
        assumption
        for assumption in dataset.tco_assumptions
        if assumption.vehicle_type.value == "CAR" and assumption.region_code == region_code
    )


@pytest.mark.parametrize("region_code", [KHU_VUC_I, KHU_VUC_II])
def test_car_tco_assumption_matches_the_current_values(region_code: str) -> None:
    """Seed CSV phai tu mang gia tri hien hanh, khong phu thuoc migration UPDATE
    chay truoc/sau tren fresh DB (xem finding 1 cua dot review cuoi).

    Các con số dưới đây được CHỐT CỨNG có chủ đích — đó là toàn bộ giá trị của
    test này. Đổi `data-p150/catalog/tco_assumptions.csv` mà không đổi ở đây thì
    test phải đỏ, vì một thay đổi phí lặng lẽ chính là thứ cần chặn.
    """

    car = _car_assumption(load_all(), region_code)

    assert car.plate_fee_vnd == _CAR_PLATE_FEE_BY_REGION[region_code]
    assert car.inspection_fee_vnd == 290000
    assert car.assumption_version == 4
    assert car.inspection_first_month == 30
    assert car.inspection_interval_months == 18
    assert car.inspection_interval_months_after_7y == 12
    assert car.source_note is not None
    assert "GIẢ ĐỊNH" in car.source_note


def test_motorbike_source_note_does_not_claim_a_permanent_inspection_exemption() -> None:
    dataset = load_all()
    motorbike = next(
        assumption for assumption in dataset.tco_assumptions if assumption.vehicle_type.value == "ELECTRIC_MOTORBIKE"
    )

    assert motorbike.source_note is not None
    assert "không được diễn giải là xe máy luôn miễn kiểm định" in motorbike.source_note
