"""[FIND_NEARBY_LOCATION] Luật thuần: nhận diện intent, loại địa điểm, deep link.

Đây là tầng quyết định lượt nào rẽ sang nhánh trạm sạc. Sai ở đây thì hoặc khách
hỏi đường bị đáp bằng câu hỏi ngân sách, hoặc khách đang khai nhu cầu tư vấn bị
kéo sang bản đồ — cả hai đều là hội thoại hỏng, và cả hai đều im lặng.
"""

from __future__ import annotations

import pytest

from src.agents.domain.nearby_location import (
    LocationKind,
    UserLocation,
    charger_type_of,
    detect_location_kinds,
    format_distance,
    is_nearby_location_request,
    location_kind_from,
    location_text_from,
    location_types_for,
    maps_directions_url,
    parse_location_kinds,
    round_distance_km,
)


@pytest.mark.parametrize(
    "message",
    [
        "gần đây có trạm sạc nào không",
        "tìm trạm sạc gần nhất",
        "trạm sạc ô tô ở đâu",
        "trạm đổi pin gần Cầu Giấy",
        "chỉ đường tới trụ sạc gần nhất",
        "quanh đây có điểm sạc nào không",
        "showroom xe máy điện gần nhất",
        "đại lý ô tô ở đâu",
        "tìm chỗ gần tôi",
        "chỉ đường tới showroom",
    ],
)
def test_location_questions_are_recognized(message: str) -> None:
    assert is_nearby_location_request(message) is True


@pytest.mark.parametrize(
    "message",
    [
        # Tiêu chí tư vấn, KHÔNG phải câu hỏi đường. Chữ "sạc" có mặt trong cả
        # hai loại câu, nên đây là ranh giới dễ vỡ nhất của bộ dò.
        "nhà em không có chỗ sạc, tư vấn xe giúp em",
        "nhà em có trạm sạc riêng rồi",
        "sạc tại nhà được không",
        # Câu hỏi thông số, có danh từ trạm nhưng không đi tìm địa điểm nào.
        "xe này sạc ở trạm mất bao lâu",
        # Không liên quan.
        "VF 5 giá bao nhiêu",
        "so sánh VF 3 và VF 5",
        "",
    ],
)
def test_non_location_questions_are_left_alone(message: str) -> None:
    assert is_nearby_location_request(message) is False


def test_vehicle_cue_narrows_the_kind() -> None:
    """Khách đi xe máy nhận về trụ sạc ô tô là một danh sách vô dụng với họ."""

    assert detect_location_kinds("trạm sạc xe máy điện gần đây") == (LocationKind.CHARGING_STATION_MOTORBIKE,)
    assert detect_location_kinds("trạm sạc ô tô gần đây") == (LocationKind.CHARGING_STATION_CAR,)
    assert detect_location_kinds("showroom ô tô gần nhất") == (LocationKind.SHOWROOM_CAR,)
    assert detect_location_kinds("tủ đổi pin gần đây") == (LocationKind.BATTERY_SWAP_CABINET,)


def test_group_without_a_vehicle_cue_returns_both_members() -> None:
    """ "trạm sạc" xác định về NHÓM nhưng chưa về phương tiện.

    Trả cả hai loại vẫn là câu trả lời đúng; hỏi lại ở đây là bắt khách phân loại
    hộ hệ thống một thứ họ không quan tâm.
    """

    assert detect_location_kinds("trạm sạc gần đây") == (
        LocationKind.CHARGING_STATION_CAR,
        LocationKind.CHARGING_STATION_MOTORBIKE,
    )
    assert detect_location_kinds("showroom gần nhất") == (
        LocationKind.SHOWROOM_CAR,
        LocationKind.SHOWROOM_MOTORBIKE,
    )


def test_typeless_question_yields_no_kind_instead_of_guessing() -> None:
    """RỖNG là tín hiệu để HỎI LẠI, không phải lỗi.

    Đoán "chắc khách tìm trạm sạc ô tô" cho câu "tìm chỗ gần tôi" trả về một danh
    sách trông rất thuyết phục và sai loại — khách chỉ phát hiện khi đã tới nơi.
    """

    assert detect_location_kinds("tìm chỗ gần tôi") == ()
    assert detect_location_kinds("địa điểm gần nhất ở đâu") == ()
    assert is_nearby_location_request("tìm chỗ gần tôi") is True


@pytest.mark.parametrize(
    "message",
    [
        # Câu hỏi DANH MỤC, không phải câu hỏi đường. "cửa hàng"/"showroom" mang
        # cả hai nghĩa, nên chúng đòi một dấu hiệu vị trí thật sự — nếu không,
        # `CATALOG_BROWSE` bị cướp mất đúng câu hỏi của nó.
        "cửa hàng có xe nào không",
        "showroom có xe nào không",
        "cửa hàng có những xe gì",
    ],
)
def test_catalog_questions_are_not_stolen_from_catalog_browse(message: str) -> None:
    assert is_nearby_location_request(message) is False


def test_battery_swap_wins_over_the_station_noun() -> None:
    """ "trạm đổi pin" khớp cả `_STATION_NOUN`; nó phải về tủ đổi pin, không phải trạm sạc."""

    assert detect_location_kinds("trạm đổi pin gần Cầu Giấy") == (LocationKind.BATTERY_SWAP_CABINET,)


def test_kind_maps_to_the_storage_string_the_table_actually_uses() -> None:
    """Enum công khai ↔ chuỗi `locations.location_type`.

    Lệch một chữ ở đây là một truy vấn luôn trả rỗng, và không test nào khác bắt
    được: bộ lọc vẫn chạy, chỉ là không khớp hàng nào.
    """

    assert location_types_for([LocationKind.SHOWROOM_MOTORBIKE]) == ("showroom_escooter",)
    assert location_types_for([LocationKind.CHARGING_STATION_CAR, LocationKind.BATTERY_SWAP_CABINET]) == (
        "car_charging_station",
        "battery_swap_station",
    )


def test_charger_type_only_applies_to_charging_kinds() -> None:
    """Showroom và tủ đổi pin không có khái niệm cổng sạc nào để nói."""

    assert charger_type_of("car_charging_station") == "CAR_CHARGER"
    assert charger_type_of("bike_charging_station") == "MOTORBIKE_CHARGER"
    assert charger_type_of("showroom_car") is None
    assert charger_type_of("battery_swap_station") is None
    # Loại lạ (năm loại xưởng dịch vụ còn nằm trong bảng) → `None`, không đoán.
    assert charger_type_of("service_gsm") is None


def test_kind_slot_round_trips_through_the_persisted_payload() -> None:
    """Bộ trích ↔ bộ dựng lại phải khớp nhau, kể cả khi có nhiều loại."""

    raw = location_kind_from("trạm sạc gần đây")
    assert raw == "CHARGING_STATION_CAR,CHARGING_STATION_MOTORBIKE"
    assert parse_location_kinds(raw) == (
        LocationKind.CHARGING_STATION_CAR,
        LocationKind.CHARGING_STATION_MOTORBIKE,
    )
    assert location_kind_from("không biết") is None
    # Payload hỏng → rỗng, không raise: một cột dữ liệu cũ không được giết lượt.
    assert parse_location_kinds("KHONG_TON_TAI") == ()
    assert parse_location_kinds(None) == ()


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Cầu Giấy", "Cầu Giấy"),
        ("tôi đang ở Cầu Giấy", "Cầu Giấy"),
        ("gần Cầu Giấy, Hà Nội", "Cầu Giấy, Hà Nội"),
        ("khu vực Thanh Xuân", "Thanh Xuân"),
        # Địa danh có thật bắt đầu bằng một từ trông như tiền tố. Cắt đi thì
        # geocode chắc chắn trượt, nên bộ tách phải để nguyên.
        ("cho lon", "cho lon"),
        ("o mon", "o mon"),
        # Không mang địa danh nào → `None`, để không đem "không biết" đi geocode.
        ("không biết", None),
        ("thôi", None),
        ("123", None),
        ("", None),
    ],
)
def test_location_text_extraction(answer: str, expected: str | None) -> None:
    assert location_text_from(answer) == expected


def test_maps_url_includes_origin_when_the_customer_location_is_known() -> None:
    url = maps_directions_url(
        destination_latitude=21.0123,
        destination_longitude=105.8456,
        origin=UserLocation(latitude=21.0285, longitude=105.8542),
    )

    assert url == ("https://www.google.com/maps/dir/?api=1&origin=21.0285,105.8542&destination=21.0123,105.8456")


def test_maps_url_without_origin_still_builds_a_valid_link() -> None:
    url = maps_directions_url(destination_latitude=21.0123, destination_longitude=105.8456)

    assert "origin=" not in url
    assert url.endswith("destination=21.0123,105.8456")


def test_distance_is_rounded_to_one_decimal_and_read_aloud_sensibly() -> None:
    assert round_distance_km(1.24) == 1.2
    assert round_distance_km(7.08) == 7.1
    assert round_distance_km(None) is None
    assert format_distance(1.24) == "1.2 km"
    # Dưới 1 km đổi sang mét: "0.4 km" đọc chậm hơn "khoảng 400 m", và đây là con
    # số khách quyết định dựa vào.
    assert format_distance(0.42) == "khoảng 420 m"
    assert format_distance(None) == "chưa rõ khoảng cách"


def test_user_location_payload_round_trips_and_rejects_corrupt_rows() -> None:
    """Payload hỏng → `None`, không raise: một cột dữ liệu cũ không được giết lượt."""

    original = UserLocation(latitude=21.03, longitude=105.85, source="geocode", label="Hà Nội")

    assert UserLocation.from_payload(original.to_payload()) == original
    assert UserLocation.from_payload(None) is None
    assert UserLocation.from_payload({"latitude": "hai mươi mốt"}) is None
    assert UserLocation.from_payload({"latitude": 999.0, "longitude": 105.0}) is None
    # `bool` là subclass của `int` trong Python — không loại nó ra thì
    # `{"latitude": True}` trở thành toạ độ 1.0 độ Bắc, giữa Đại Tây Dương.
    assert UserLocation.from_payload({"latitude": True, "longitude": True}) is None
