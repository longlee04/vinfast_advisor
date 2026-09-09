"""[A4-7] Prompt phân loại intent phải DẠY được ranh giới ba chiều.

Phần còn lại của hệ thống chỉ chạy đúng khi classifier gán đúng nhãn
(`tests/agents/integration/test_catalog_browse_flow.py` giả định điều đó). Ranh
giới ấy sống trong đúng một chuỗi mô tả gửi kèm function calling, nên nó là thứ
duy nhất ở đây kiểm được mà không phải gọi LLM thật.

Kiểm nội dung prompt, không kiểm hành vi LLM: một nhãn bị bỏ khỏi enum hoặc một
ví dụ ranh giới bị xoá là hỏng câm — không test nào khác trong repo đỏ lên, còn
khách thì nhận lại đúng câu "Em chưa tìm thấy 'xe máy điện'".
"""

from __future__ import annotations

import pytest

from src.agents.domain.values import Intent, VehicleType
from src.agents.prompts.intent_prompts import INTENT_FIELD_DESCRIPTION
from src.agents.prompts.slot_extraction_prompts import build_tool_schema

DESCRIPTION: str = str(INTENT_FIELD_DESCRIPTION["description"])


def test_every_intent_is_offered_to_the_model() -> None:
    """Nhãn không có trong enum thì LLM không có cách nào trả về nó."""

    items = INTENT_FIELD_DESCRIPTION["items"]
    assert isinstance(items, dict)
    assert set(items["enum"]) == {member.value for member in Intent}


def test_the_new_intent_reaches_the_runtime_tool_schema() -> None:
    """Enum phải đi được tới schema thật, không chỉ nằm trong hằng số."""

    schema = build_tool_schema(VehicleType.ELECTRIC_MOTORBIKE, [("GPS", "Định vị")])
    parameters = schema["parameters"]
    assert isinstance(parameters, dict)
    intents = parameters["properties"]["intents"]["items"]["enum"]

    assert Intent.CATALOG_BROWSE.value in intents


@pytest.mark.parametrize(
    "example",
    [
        "các xe máy điện có trong cửa hàng",
        "cửa hàng có những xe gì",
        "có xe nào không",
        "gợi ý cho tôi các xe máy điện và ô tô điện có trong cửa hàng",
    ],
)
def test_browse_examples_are_taught_with_their_label(example: str) -> None:
    assert example in DESCRIPTION


def test_the_boundary_against_a_named_model_is_taught() -> None:
    """ "VF5 giá bao nhiêu" phải ở lại CATALOG_LOOKUP — regression của luồng cũ."""

    assert "VF5 giá bao nhiêu" in DESCRIPTION
    assert "Klara giá bao nhiêu" in DESCRIPTION
    assert "TÊN MẪU" in DESCRIPTION


def test_short_named_model_followup_is_taught_as_lookup() -> None:
    assert "VF9 đi" in DESCRIPTION
    assert "VF 9 nhé" in DESCRIPTION


def test_named_model_listing_is_taught_as_lookup_not_browse() -> None:
    """Listing words must not hide an explicitly named vehicle family."""

    assert "tất cả các mẫu VF8 hiện tại" in DESCRIPTION
    assert "CATALOG_LOOKUP" in DESCRIPTION


def test_the_boundary_against_personal_criteria_is_taught() -> None:
    """Câu có ngân sách/số người vẫn là ADVISORY, không phải liệt kê danh mục."""

    assert "ngân sách 700 triệu" in DESCRIPTION
    assert "tiêu chí cá nhân" in DESCRIPTION


def test_the_ambiguous_goi_y_case_is_resolved_explicitly() -> None:
    """ "gợi ý xe máy điện cho tôi" trần: đã chọn BROWSE, và lựa chọn đó phải ghi rõ.

    Bỏ ví dụ này thì LLM nghiêng về ADVISORY vì chữ "gợi ý", và khách nhận một
    loạt câu hỏi nhu cầu thay cho danh sách họ vừa xin.
    """

    assert "gợi ý xe máy điện cho tôi" in DESCRIPTION
    assert Intent.CATALOG_BROWSE.value in DESCRIPTION


def test_vehicle_selection_and_elimination_are_taught_as_advisory() -> None:
    assert "cân nhắc VF 5 và VF 7" in DESCRIPTION
    assert "loại VF 5" in DESCRIPTION
    assert Intent.ADVISORY.value in DESCRIPTION
