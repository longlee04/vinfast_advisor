"""[A7-8] Hỏi field nào thì trả đúng field đó.

Trước đây chỉ "giá" có nhánh riêng. Mọi câu hỏi field khác rơi về `UNKNOWN` và
nhận nguyên bảng thông số: khách hỏi "vf5 có mấy chỗ ngồi" được trả cả động cơ,
pin, màn hình, an toàn lẫn giá — câu trả lời đúng vẫn nằm đâu đó trong đó, nhưng
chính khách phải đi tìm.

Hai lớp test: phân loại câu hỏi, và nội dung câu trả lời tương ứng.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import VehicleFacts
from src.agents.domain.catalog_reply import CLOSING_NOTE, SPEC_HEADING
from src.agents.domain.values import VehicleType
from src.agents.domain.vehicle_overview import VehicleAttribute, classify_query_attribute
from src.agents.services.intent_routing import render_catalog_answer

VF5 = UUID("50000000-0000-0000-0000-000000000005")

FACTS = VehicleFacts(
    vehicle_id=VF5,
    display_name="VinFast VF 5 All New",
    vehicle_type=VehicleType.CAR,
    starting_price_vnd=Decimal(436_000_000),
    specs={
        "body_type": "SUV",
        "seat_count": 5,
        "range_km": "326.00",
        "motor_power_kw": "100.000",
        "torque_nm": "135.000",
        "battery_capacity_kwh": "37.230",
        "charging_port": "CCS2",
    },
    features={
        "PANORAMIC_ROOF": "Cửa sổ trời toàn cảnh",
        "ADAS_SUITE": "Hỗ trợ lái nâng cao ADAS",
        "GPS": "GPS",
    },
)


def _answer(question: str, facts: VehicleFacts = FACTS) -> str:
    answer = render_catalog_answer([facts], [], [], question)
    assert answer is not None
    return answer


def _body(question: str, facts: VehicleFacts = FACTS) -> str:
    """Phần nội dung, bỏ lời chào và hai câu kết."""

    return _answer(question, facts).split("\n\n")[1]


# ── Phân loại câu hỏi ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("vf5 giá bao nhiêu", VehicleAttribute.PRICE),
        ("vf5 có mấy chỗ ngồi", VehicleAttribute.SEAT_COUNT),
        ("vf5 chở được bao nhiêu người", VehicleAttribute.SEAT_COUNT),
        ("vf5 có túi khí không", VehicleAttribute.AIRBAG),
        ("vf5 có cửa sổ trời không", VehicleAttribute.SUNROOF),
        ("vf5 màu gì", VehicleAttribute.COLOR),
        ("nội thất màu gì", VehicleAttribute.INTERIOR_COLOR),
        ("sạc đầy vf5 đi được bao xa", VehicleAttribute.RANGE),
        ("vf5 công suất bao nhiêu", VehicleAttribute.POWERTRAIN),
        ("vf5 điều hòa loại gì", VehicleAttribute.AIR_CONDITIONING),
        ("vf5 hệ thống treo gì", VehicleAttribute.SUSPENSION),
        ("vf5 màn hình bao nhiêu inch", VehicleAttribute.INFOTAINMENT),
        ("vf5 kích thước thế nào", VehicleAttribute.DIMENSIONS),
        ("vf5 có abs không", VehicleAttribute.SAFETY),
        ("chính sách bảo hành vf5", VehicleAttribute.WARRANTY),
        ("thông tin xe vf5", VehicleAttribute.OVERVIEW),
        ("tư vấn chi tiết về vf5", VehicleAttribute.OVERVIEW),
        ("vf5", VehicleAttribute.UNKNOWN),
    ],
)
def test_each_way_of_asking_maps_to_its_own_field(question: str, expected: VehicleAttribute) -> None:
    assert classify_query_attribute(question) is expected


@pytest.mark.parametrize(
    "question",
    ["vf5 chở được bao nhiêu người", "vf5 công suất bao nhiêu", "vf5 màn hình bao nhiêu inch"],
)
def test_bao_nhieu_alone_no_longer_means_a_price_question(question: str) -> None:
    """ "bao nhiêu" từng là từ khoá của PRICE và đặt trước mọi field khác.

    Hậu quả: ba câu dưới đây đều bị đọc thành hỏi giá. Field cụ thể phải xét
    trước, và PRICE chỉ nhận các cụm thật sự nói về tiền.
    """

    assert classify_query_attribute(question) is not VehicleAttribute.PRICE


# ── Nội dung trả lời ──────────────────────────────────────────────────────────


def test_a_price_question_still_answers_only_the_price() -> None:
    """Hành vi vốn ĐÚNG, không được đổi khi mở rộng các field khác."""

    body = _body("vf5 giá bao nhiêu")

    assert body == "**Giá bán**: từ 436.000.000 đồng (đã bao gồm VAT)."


def test_a_seat_question_answers_only_the_seat_count() -> None:
    """Bug gốc: câu này trả về nguyên bảng thông số cộng giá."""

    answer = _answer("vf5 có mấy chỗ ngồi")

    assert "VinFast VF 5 All New có 5 chỗ ngồi." in answer
    assert SPEC_HEADING not in answer
    for absent in ("436.000.000", "100 kW", "37.23 kWh", "GPS", "ADAS"):
        assert absent not in answer


def test_an_airbag_question_is_not_answered_with_brakes_and_stability_control() -> None:
    """Khách hỏi túi khí mà nhận ABS/ESC là bị lái sang chuyện khác.

    Catalog chưa có cột số túi khí lẫn feature code nào cho nó → nói thẳng.
    """

    answer = _answer("vf5 có túi khí không")

    assert "chưa có dữ liệu đã xác minh về túi khí" in answer
    assert "ADAS" not in answer
    assert "An toàn:" not in answer


def test_a_sunroof_question_uses_the_verified_feature_flag() -> None:
    answer = _answer("vf5 có cửa sổ trời không")

    assert "có cửa sổ trời toàn cảnh." in answer
    assert SPEC_HEADING not in answer


def test_a_missing_feature_flag_is_never_read_as_the_vehicle_lacking_it() -> None:
    """Vắng mặt trong `features` có thể chỉ là CHƯA AI XÁC MINH.

    `features` chỉ chứa tính năng `status='YES'` đã duyệt. Nói "xe không có cửa
    sổ trời" khi thực ra chưa xác minh là một khẳng định sai về sản phẩm.
    """

    without_roof = replace(FACTS, features={})

    answer = _answer("vf5 có cửa sổ trời không", without_roof)

    assert "chưa có dữ liệu đã xác minh về cửa sổ trời" in answer
    assert "không có" not in answer


def test_a_range_question_answers_only_the_range() -> None:
    answer = _answer("sạc đầy vf5 đi được bao xa")

    assert "đi được khoảng 326 km cho mỗi lần sạc đầy." in answer
    assert "436.000.000" not in answer


def test_a_powertrain_question_answers_only_the_powertrain() -> None:
    answer = _answer("vf5 công suất bao nhiêu")

    assert "công suất 100 kW" in answer
    assert "Giá bán" not in answer


@pytest.mark.parametrize(
    ("question", "label"),
    [
        ("vf5 hệ thống treo gì", "hệ thống treo"),
        ("vf5 điều hòa loại gì", "hệ thống điều hòa"),
        ("nội thất màu gì", "màu nội thất"),
        ("chính sách bảo hành vf5", "chính sách bảo hành"),
    ],
)
def test_a_field_without_catalog_data_says_so_by_name(question: str, label: str) -> None:
    """Báo thiếu ĐÚNG field được hỏi, không đắp bằng field khác."""

    answer = _answer(question)

    assert f"chưa có dữ liệu đã xác minh về {label}" in answer
    assert SPEC_HEADING not in answer
    assert "436.000.000" not in answer


# ── Câu hỏi mở vẫn nhận bảng đầy đủ ───────────────────────────────────────────


@pytest.mark.parametrize("question", ["thông tin xe vf5", "tư vấn chi tiết về vf5", "vf5"])
def test_an_open_question_still_gets_the_full_sheet(question: str) -> None:
    """Không được sửa quá tay: câu hỏi chung chung vẫn dùng format đầy đủ."""

    answer = _answer(question)

    assert answer.startswith("Dạ, VinFast VF 5 All New là mẫu xe thuần điện")
    assert SPEC_HEADING in answer
    assert "**Giá bán**: từ 436.000.000 đồng" in answer


def test_every_answer_keeps_the_same_closing_note() -> None:
    """Trải nghiệm đồng nhất: câu kết áp dụng cho cả field lẻ lẫn bảng đầy đủ."""

    for question in ("vf5 giá bao nhiêu", "vf5 có mấy chỗ ngồi", "thông tin xe vf5"):
        assert _answer(question).endswith(CLOSING_NOTE)


def test_a_field_answer_stays_short() -> None:
    """1-2 câu, không kéo theo cả khối thông số."""

    body = _body("vf5 có mấy chỗ ngồi")

    assert "\n" not in body
    assert len(body) < 120
