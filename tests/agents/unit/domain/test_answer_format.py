"""[A7-6] Format chuẩn của câu trả lời thông tin xe.

Test mẫu là câu "thông tin xe vf5". Mỗi test dưới đây khoá một điều đã từng sai,
để nó không quay lại một cách im lặng — và nay khoá thêm bố cục Markdown chung
(`domain/reply_format`): mục lớn đánh số, bullet `* `, tên trường in đậm.

Một mình việc backend trả về `\n` KHÔNG đủ để khách nhìn thấy bố cục: HTML gộp
mọi khoảng trắng liên tiếp, nên nửa còn lại của format nằm ở
`frontend/src/components/common/rich-text.tsx`. Các test ở đây chỉ nói được nửa
backend; nửa kia có test riêng bên frontend.
"""

from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import VehicleFacts
from src.agents.domain.catalog_reply import (
    CLOSING_NOTE,
    SHEET_INVITATION,
    SPEC_HEADING,
    render_lookup_answer,
)
from src.agents.domain.values import VehicleType

VF5 = UUID("50000000-0000-0000-0000-000000000005")


def _vf5(**overrides) -> VehicleFacts:
    """VF 5 All New với đúng dữ liệu catalog thật đang có."""

    base = {
        "vehicle_id": VF5,
        "display_name": "VinFast VF 5 All New",
        "vehicle_type": VehicleType.CAR,
        "starting_price_vnd": Decimal(436_000_000),
        "specs": {
            "body_type": "SUV",
            "seat_count": 5,
            "range_km": "326.00",
            "motor_power_kw": "100.000",
            "torque_nm": "135.000",
            "battery_capacity_kwh": "37.230",
            "max_speed_kmh": "130.00",
            "charging_port": "CCS2",
        },
        "features": {
            "ADAS_SUITE": "Hỗ trợ lái nâng cao ADAS",
            "BLUETOOTH": "Bluetooth",
            "GPS": "GPS",
            "MOBILE_APP": "Mobile App",
        },
    }
    base.update(overrides)
    return VehicleFacts(**base)


def _answer(**overrides) -> str:
    answer = render_lookup_answer([_vf5(**overrides)])
    assert answer is not None
    return answer


def _bullets(answer: str) -> list[str]:
    return [line for line in answer.splitlines() if line.startswith("* ")]


def _sections(answer: str) -> list[str]:
    """Các dòng tiêu đề mục lớn, kèm cả số thứ tự."""

    return [line for line in answer.splitlines() if _SECTION_HEADING.match(line)]


_SECTION_HEADING = re.compile(r"^\d+\. \*\*")


# ── Cấu trúc tổng thể ─────────────────────────────────────────────────────────


def test_the_answer_follows_the_standard_block_structure() -> None:
    """Mở đầu → các mục lớn → giá → đoạn mời → hai câu kết, đúng thứ tự đó."""

    blocks = _answer().split("\n\n")

    assert blocks[0].startswith("Dạ, VinFast VF 5 All New")
    assert blocks[1].startswith(f"1. **{SPEC_HEADING}**:")
    assert blocks[-3].endswith("(đã bao gồm VAT).")
    assert blocks[-2] == SHEET_INVITATION
    assert blocks[-1] == CLOSING_NOTE


def test_every_block_is_separated_by_a_blank_line() -> None:
    """Cái sai gốc: cả câu trả lời dồn thành một đoạn văn không chỗ ngắt."""

    answer = _answer()

    assert answer.count("\n\n") >= 4
    assert "\n\n\n" not in answer


def test_the_opening_is_a_paragraph_of_two_or_three_sentences() -> None:
    """Đoạn mở đầu KHÔNG có bullet — đó là chỗ format cũ bắt đầu liệt kê."""

    opening = _answer().split("\n\n")[0]

    assert "- " not in opening
    assert 2 <= opening.count(".") <= 3
    assert "phân khúc SUV" in opening


def test_the_answer_ends_with_the_exact_required_two_sentences() -> None:
    answer = _answer()

    assert answer.endswith(CLOSING_NOTE)
    assert answer.count(CLOSING_NOTE) == 1


# ── Ràng buộc đã bị format cũ vi phạm ─────────────────────────────────────────


def test_no_evidence_id_reaches_the_customer() -> None:
    assert "evidence_id" not in _answer()


def test_section_headings_are_numbered_and_bold() -> None:
    """Từ hai nhóm thông tin trở lên → mục lớn đánh số, tiêu đề in đậm."""

    answer = _answer()
    headings = _sections(answer)

    assert len(headings) >= 2
    assert headings[0] == f"1. **{SPEC_HEADING}**:"
    assert [line.split(".")[0] for line in headings] == [str(index) for index in range(1, len(headings) + 1)]
    # Nhãn cũ của format trước đó, không được quay lại.
    assert "Giá niêm yết" not in answer


def test_each_group_appears_exactly_once() -> None:
    """Format cũ nhắc lại cùng một nội dung ở hai ba mục khác nhau."""

    labels = [bullet.split("**")[1] for bullet in _bullets(_answer())]

    assert len(labels) == len(set(labels))


def test_each_bullet_is_one_single_line_group_with_a_bold_label() -> None:
    """Mỗi bullet là "* **Tên trường**: giá trị", không phải một đoạn văn."""

    bullets = _bullets(_answer())

    assert bullets
    for bullet in bullets:
        assert "\n" not in bullet
        assert re.fullmatch(r"\* \*\*[^*]+\*\*: .+", bullet), bullet


def test_the_price_line_states_the_vat_position() -> None:
    price = [line for line in _answer().splitlines() if "**Giá bán**" in line]

    assert price == ["4. **Giá bán**: từ 436.000.000 đồng (đã bao gồm VAT)."]


# ── Không bịa dữ liệu ─────────────────────────────────────────────────────────


def test_groups_without_catalog_data_are_dropped_entirely() -> None:
    """Bốn nhóm chưa có nguồn nào trong catalog phải VẮNG MẶT.

    Không ghi "chưa có thông tin" cho đủ mục: một dòng như thế làm bảng dài ra mà
    không thêm dữ kiện nào, và đọc như thể hệ thống có biết nhưng không nói.
    """

    answer = _answer()

    for absent in (
        "**Kích thước**",
        "**Hệ thống treo**",
        "**Hệ thống điều hòa**",
        "**Màu nội thất**",
    ):
        assert absent not in answer
    assert "chưa có thông tin" not in answer.casefold()


def test_only_verified_numbers_appear() -> None:
    """Mọi con số trong câu trả lời phải truy được về một trường catalog."""

    answer = _answer()

    assert "100 kW" in answer
    assert "135 Nm" in answer
    assert "326 km" in answer
    assert "436.000.000 đồng" in answer


def test_a_vehicle_without_an_effective_price_says_so_plainly() -> None:
    """Thiếu giá thì nói thiếu, tuyệt đối không suy ra từ mẫu khác."""

    answer = _answer(starting_price_vnd=None)

    assert "**Giá bán**: hiện chưa có giá công bố hiệu lực." in answer
    assert "VAT" not in answer


def test_missing_specs_shrink_the_table_instead_of_breaking_it() -> None:
    answer = _answer(specs={}, features={})

    assert f"**{SPEC_HEADING}**" not in answer
    assert answer.startswith("Dạ, VinFast VF 5 All New")
    assert answer.endswith(CLOSING_NOTE)


# ── Phân nhóm đúng chỗ ────────────────────────────────────────────────────────


def test_safety_features_carry_a_short_expansion_of_the_abbreviation() -> None:
    """Viết tắt + tên đầy đủ NGẮN GỌN, không giải thích dài từng tính năng."""

    # Tên trong catalog đã chứa sẵn nghĩa đầy đủ → KHÔNG chú giải thêm lần nữa.
    already_expanded = _group(_answer(), "Trang bị an toàn")
    assert already_expanded == "* **Trang bị an toàn**: Hỗ trợ lái nâng cao ADAS"

    # Tên chỉ là viết tắt trần → thêm nghĩa ngắn gọn trong ngoặc.
    bare = _group(_answer(features={"ADAS_SUITE": "ADAS"}), "Trang bị an toàn")
    assert bare == "* **Trang bị an toàn**: ADAS (hỗ trợ lái nâng cao)"
    assert len(bare) < 120


def test_a_security_feature_is_not_filed_under_infotainment() -> None:
    """`ANTI_THEFT` mang category SMART_FEATURE trong catalog nhưng không phải
    giải trí — đổ nguyên category vào dòng "Màn hình & Giải trí" là dán nhãn sai."""

    answer = _answer(
        features={"ANTI_THEFT": "Anti Theft", "GPS": "GPS"},
    )

    assert "Anti Theft" in _group(answer, "Trang bị an toàn")
    assert "Anti Theft" not in _group(answer, "Màn hình & Giải trí")


def test_an_unmapped_feature_code_is_omitted_rather_than_mislabelled() -> None:
    answer = _answer(features={"BATTERY_SWAPPABLE": "Battery Swappable"})

    assert "Battery Swappable" not in answer


@pytest.mark.parametrize("value", ["326.00", "326.0", "326"])
def test_trailing_decimal_zeros_are_trimmed(value: str) -> None:
    answer = _answer(specs={"range_km": value})

    assert "326 km" in answer
    assert "326.00" not in answer


def _group(answer: str, label: str) -> str:
    """Nội dung của một dòng nhóm, hoặc chuỗi rỗng khi nhóm đó vắng mặt."""

    for line in answer.splitlines():
        if line.startswith(f"* **{label}**:"):
            return line
    return ""
