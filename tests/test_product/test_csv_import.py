"""Tests cho CSV import utilities — bám schema mới trong entities.py."""

from __future__ import annotations

import json
from pathlib import Path

from src.products.domain.entities import (
    BatteryPolicy,
    Car,
    FeatureDefinition,
    FeatureNeedTag,
    Motorbike,
    Promotion,
    PromotionVehicle,
    TcoAssumption,
    Vehicle,
    VehicleFeatureFlag,
    VehiclePrice,
    VehicleShowcaseItem,
)
from src.products.domain.tco import KHU_VUC_I, KHU_VUC_II
from src.products.infrastructure.csv_import import (
    CatalogDataset,
    load_all,
    load_battery_policies,
    load_cars,
    load_feature_definitions,
    load_feature_need_tags,
    load_motorbikes,
    load_promotion_vehicles,
    load_promotions,
    load_tco_assumptions,
    load_vehicle_feature_flags,
    load_vehicle_prices,
    load_vehicle_showcase_items,
    load_vehicles,
)

# ---------------------------------------------------------------------------
# Top-level shape
# ---------------------------------------------------------------------------


def test_load_all_returns_full_dataset() -> None:
    dataset = load_all()
    assert isinstance(dataset, CatalogDataset)
    assert len(dataset.vehicles) >= 1
    assert len(dataset.cars) >= 1
    assert len(dataset.motorbikes) >= 1
    assert len(dataset.prices) >= 1
    assert len(dataset.feature_definitions) >= 1
    assert len(dataset.feature_flags) >= 1
    assert len(dataset.tco_assumptions) >= 1
    assert len(dataset.feature_need_tags) >= 1
    assert len(dataset.showcase_items) >= 1


# ---------------------------------------------------------------------------
# Per-table
# ---------------------------------------------------------------------------


def test_load_vehicles_returns_correct_entity() -> None:
    items = list(load_vehicles())
    assert items, "vehicles.csv phải có dữ liệu"
    for v in items:
        assert isinstance(v, Vehicle)
        assert v.vehicle_id
        assert v.brand == "VinFast"
        assert v.status.value in {"DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED"}
        assert v.vehicle_type.value in {"CAR", "ELECTRIC_MOTORBIKE"}


def test_load_cars_has_required_specifics() -> None:
    items = list(load_cars())
    assert items
    for c in items:
        assert isinstance(c, Car)
        assert c.vehicle_id
        assert c.specs_version >= 1


def test_load_motorbikes_has_required_specifics() -> None:
    items = list(load_motorbikes())
    assert items
    for m in items:
        assert isinstance(m, Motorbike)
        assert m.vehicle_id


def test_load_vehicle_prices_uses_vnd() -> None:
    items = list(load_vehicle_prices())
    assert items
    for p in items:
        assert isinstance(p, VehiclePrice)
        assert p.currency.value == "VND"
        assert p.amount_vnd >= 0


def test_load_promotions_have_required_codes() -> None:
    items = list(load_promotions())
    assert items
    for promo in items:
        assert isinstance(promo, Promotion)
        assert promo.promotion_code
        assert promo.region_code == "VN"


def test_load_promotions_preserves_eligibility_rules_json(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "promotions.csv"
    source = Path("data-p150/catalog/promotions.csv")
    header = source.read_text(encoding="utf-8").splitlines()[0]
    rules = {"source_url": "https://vinfastauto.com/policy.pdf", "member": True}
    row = (
        "00000000-0000-0000-0000-000000000001,TEST,Test promotion,Test,"
        'OTHER,,,VN,"' + json.dumps(rules).replace('"', '""') + '",ACTIVE,'
        "2026-08-01T00:00:00Z,2026-09-01T00:00:00Z,test,test,"
        "2026-08-01T00:00:00Z,2026-08-01T00:00:00Z,2026-08-01T00:00:00Z"
    )
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")

    [promotion] = list(load_promotions(path))

    assert promotion.eligibility_rules == rules


def test_load_promotion_vehicles_keys() -> None:
    items = list(load_promotion_vehicles())
    assert items
    for pv in items:
        assert isinstance(pv, PromotionVehicle)
        assert pv.promotion_id and pv.vehicle_id


def test_load_battery_policies_have_ownership() -> None:
    items = list(load_battery_policies())
    assert items
    for bp in items:
        assert isinstance(bp, BatteryPolicy)
        assert bp.ownership_model.value in {
            "INCLUDED",
            "PURCHASE",
            "SUBSCRIPTION",
            "SWAP",
            "NOT_APPLICABLE",
        }


def test_load_feature_definitions_active() -> None:
    items = list(load_feature_definitions())
    assert items
    for fd in items:
        assert isinstance(fd, FeatureDefinition)
        assert fd.status.value in {"ACTIVE", "ARCHIVED"}


def test_load_vehicle_feature_flags_have_status() -> None:
    items = list(load_vehicle_feature_flags())
    assert items
    for f in items:
        assert isinstance(f, VehicleFeatureFlag)
        assert f.status.value in {"YES", "NO", "UNKNOWN"}
        assert f.verification_status.value in {"PENDING", "APPROVED", "REJECTED"}


def test_load_tco_assumptions_returns_entities() -> None:
    """Mỗi dòng phải mang một MÃ KHU VỰC hợp lệ, không phải một mã toàn quốc.

    Trước đây test chốt cứng `"VN"`. Migration `a1b2c3d4e5f6` đã tách bảng thành
    hai khu vực vì lệ phí biển số ô tô chênh nhau 100 lần giữa Hà Nội/TP.HCM
    (14.000.000) và các tỉnh còn lại (140.000) — một mã dùng chung không diễn tả
    được điều đó. Chốt theo hằng số của `domain/tco` thay vì gõ lại chuỗi: đổi
    tên khu vực ở đó thì test đi theo, không lệch âm thầm.
    """

    items = list(load_tco_assumptions())
    assert items
    for t in items:
        assert isinstance(t, TcoAssumption)
        assert t.electricity_vnd_per_kwh > 0
        assert t.region_code in {KHU_VUC_I, KHU_VUC_II}


def test_every_vehicle_type_has_a_row_for_both_regions() -> None:
    """Thiếu một dòng thì repository lọc chặt theo vùng chỉ khớp được nửa số
    truy vấn — khách ở khu vực còn lại nhận `tco_unavailable` dù dữ liệu thực ra
    có sẵn (xem chú thích trong migration `a1b2c3d4e5f6`)."""

    items = list(load_tco_assumptions())
    pairs = {(t.vehicle_type.value, t.region_code) for t in items}
    vehicle_types = {vehicle_type for vehicle_type, _ in pairs}

    assert vehicle_types
    for vehicle_type in vehicle_types:
        assert (vehicle_type, KHU_VUC_I) in pairs
        assert (vehicle_type, KHU_VUC_II) in pairs


def test_load_feature_need_tags_returns_entities() -> None:
    items = list(load_feature_need_tags())
    assert items
    for tag in items:
        assert isinstance(tag, FeatureNeedTag)
        assert tag.feature_code
        assert tag.need_tag


def test_load_vehicle_showcase_items_preserves_source_provenance() -> None:
    items = list(load_vehicle_showcase_items())
    assert items
    assert all(isinstance(item, VehicleShowcaseItem) for item in items)
    assert {item.section_key for item in items} >= {
        "overview",
        "colors",
        "exterior",
        "interior",
        "technology",
        "performance",
        "safety",
        "versions",
    }
    assert all(item.source_url.startswith("https://shop.vinfastauto.com/") for item in items)
    assert all(item.source_retrieved_at.tzinfo is not None for item in items)


# ---------------------------------------------------------------------------
# Data integrity (FK check)
# ---------------------------------------------------------------------------


def test_dataset_integrity_no_orphan_prices() -> None:
    dataset = load_all()
    valid_ids = {v.vehicle_id for v in dataset.vehicles}
    for p in dataset.prices:
        assert p.vehicle_id in valid_ids, f"Price {p.price_id} has orphan vehicle_id={p.vehicle_id}"


def test_dataset_integrity_no_orphan_promotion_links() -> None:
    dataset = load_all()
    valid_promos = {p.promotion_id for p in dataset.promotions}
    valid_vehicles = {v.vehicle_id for v in dataset.vehicles}
    for pv in dataset.promotion_vehicles:
        assert pv.promotion_id in valid_promos
        assert pv.vehicle_id in valid_vehicles


def test_dataset_integrity_no_orphan_battery_policies() -> None:
    dataset = load_all()
    valid_ids = {v.vehicle_id for v in dataset.vehicles}
    for bp in dataset.battery_policies:
        assert bp.vehicle_id in valid_ids


def test_dataset_integrity_no_orphan_feature_flags() -> None:
    dataset = load_all()
    valid_features = {f.feature_code for f in dataset.feature_definitions}
    valid_vehicles = {v.vehicle_id for v in dataset.vehicles}
    for f in dataset.feature_flags:
        assert f.feature_code in valid_features
        assert f.vehicle_id in valid_vehicles


def test_dataset_integrity_no_orphan_showcase_items() -> None:
    dataset = load_all()
    valid_ids = {vehicle.vehicle_id for vehicle in dataset.vehicles}
    for item in dataset.showcase_items:
        assert item.vehicle_id in valid_ids


def test_dataset_no_duplicate_vehicle_id() -> None:
    dataset = load_all()
    ids = [v.vehicle_id for v in dataset.vehicles]
    assert len(set(ids)) == len(ids), "vehicle_id bị trùng"


def test_dataset_no_duplicate_slug() -> None:
    dataset = load_all()
    slugs = [v.slug for v in dataset.vehicles]
    assert len(set(slugs)) == len(slugs), "slug bị trùng"


def test_dataset_cars_and_motorbikes_disjoint() -> None:
    dataset = load_all()
    car_ids = {c.vehicle_id for c in dataset.cars}
    mb_ids = {m.vehicle_id for m in dataset.motorbikes}
    assert car_ids.isdisjoint(mb_ids), "Một vehicle không thể vừa là Car vừa là Motorbike"


def test_dataset_total_vehicles_equals_sum() -> None:
    dataset = load_all()
    total = len(dataset.cars) + len(dataset.motorbikes)
    # Có thể có vehicle không có specs (DRAFT) → chỉ check total >= sum.
    assert len(dataset.vehicles) >= total
