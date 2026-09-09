"""Tách city/district từ địa chỉ, khớp hành vi frontend đang dùng."""

from scripts.seed_locations_data import split_address


def test_full_address_gives_city_and_district() -> None:
    city, district = split_address("123 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh", "79")

    assert city == "TP Hồ Chí Minh"
    assert district == "Quận 1"


def test_two_part_address_still_gives_both() -> None:
    city, district = split_address("Quận Ba Đình, Hà Nội", "01")

    assert city == "Hà Nội"
    assert district == "Quận Ba Đình"


def test_single_part_address_falls_back_to_province_code() -> None:
    city, district = split_address("Hà Nội", "01")

    assert city == "Hà Nội"
    assert district is None


def test_empty_address_uses_the_province_code_label() -> None:
    city, district = split_address("", "01")

    assert city == "Mã tỉnh/thành 01"
    assert district is None


def test_empty_address_without_province_says_so() -> None:
    city, district = split_address("", None)

    assert city == "Mã tỉnh/thành chưa xác định"
    assert district is None


def test_trailing_separators_are_ignored() -> None:
    city, district = split_address("Quận 1, TP Hồ Chí Minh, , ", "79")

    assert city == "TP Hồ Chí Minh"
    assert district == "Quận 1"
