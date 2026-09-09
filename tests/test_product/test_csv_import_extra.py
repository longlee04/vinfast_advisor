"""Loader cho 2 bảng còn thiếu: tco_assumptions, feature_need_tags."""

from __future__ import annotations

from decimal import Decimal

from src.products.domain.values import RecordLifecycleStatus, VehicleType
from src.products.infrastructure.csv_import import (
    load_all,
    load_feature_need_tags,
    load_tco_assumptions,
)


def test_load_tco_assumptions_returns_rows() -> None:
    rows = list(load_tco_assumptions())
    assert rows, "tco_assumptions.csv phai co it nhat mot dong"


def test_tco_assumptions_have_valid_vehicle_type_and_status() -> None:
    for row in load_tco_assumptions():
        assert isinstance(row.vehicle_type, VehicleType)
        assert isinstance(row.status, RecordLifecycleStatus)


def test_tco_assumptions_electricity_price_is_positive() -> None:
    for row in load_tco_assumptions():
        assert row.electricity_vnd_per_kwh > 0


def test_tco_assumptions_horizon_months_is_positive() -> None:
    # CHECK ck_tco_assumptions_horizon o DB — bat som o tang doc CSV.
    for row in load_tco_assumptions():
        assert row.horizon_months > 0


def test_load_feature_need_tags_returns_rows() -> None:
    rows = list(load_feature_need_tags())
    assert rows, "feature_need_tags.csv phai co it nhat mot dong"


def test_feature_need_tags_relevance_in_open_closed_range() -> None:
    # CHECK ck_feature_need_tags_relevance: relevance > 0 AND relevance <= 1
    for row in load_feature_need_tags():
        assert Decimal("0") < row.relevance <= Decimal("1")


def test_feature_need_tags_are_uppercase_identifiers() -> None:
    # CHECK ck_feature_need_tags_tag_format: need_tag = upper(need_tag)
    for row in load_feature_need_tags():
        assert row.need_tag == row.need_tag.upper()
        assert row.need_tag[0].isalpha()


def test_feature_need_tags_reference_existing_feature_definitions() -> None:
    dataset = load_all()
    known = {fd.feature_code for fd in dataset.feature_definitions}
    orphans = [t.need_tag for t in dataset.feature_need_tags if t.feature_code not in known]
    assert orphans == [], f"need_tag tro toi feature_code khong ton tai: {orphans}"


def test_load_all_includes_both_new_collections() -> None:
    dataset = load_all()
    assert dataset.tco_assumptions
    assert dataset.feature_need_tags
