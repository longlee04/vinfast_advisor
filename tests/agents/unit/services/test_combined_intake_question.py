"""Danh sách câu hỏi gộp được dựng từ SLOT CÒN THIẾU, không phải ba câu cố định.

Đo trực tiếp trên bộ dựng câu chữ: ở tầng `run_turn` không quan sát được ca "còn
đúng hai tiêu chí thiếu", vì bỏ ngân sách ra khỏi danh sách thiếu cũng đồng thời
làm lượt đó đủ slot bắt buộc và đi thẳng tới bộ lọc.
"""

from __future__ import annotations

import pytest

from src.agents.domain.values import SlotName, VehicleType
from src.agents.prompts.combined_intake import (
    INTAKE_TOPICS,
    build_combined_intake_question,
)


def _items(text: str) -> list[str]:
    return [line for line in text.splitlines() if line[:3] in {"1. ", "2. ", "3. "}]


def test_muc_nhu_cau_mang_vi_du_co_so_km() -> None:
    """Ví dụ mẫu PHẢI giữ con số trong đó.

    Nó là cách duy nhất còn lại để lấy quãng đường/ngày mà không hỏi thành một
    mục riêng: khách bắt chước dạng của ví dụ. Bỏ số đi ("đi làm hằng ngày")
    thì khách cũng trả lời không số, và bảng chi phí lại chạy trên mặc định.
    """

    for vehicle_type in VehicleType:
        text = build_combined_intake_question(vehicle_type=vehicle_type, unanswered=INTAKE_TOPICS)
        assert text is not None
        assert "km mỗi ngày" in text


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_hai_chu_de_deu_thieu_thi_danh_so_1_va_2(vehicle_type: VehicleType) -> None:
    """Danh sách dựng từ slot CÒN THIẾU và đánh số liên tục.

    Từ 2026-08-26 chỉ còn hai chủ đề (ngân sách, nhu cầu) nên đây cũng là danh
    sách dài nhất có thể — mọi trường khác không hỏi nữa, chỉ nhặt khi khách tự
    nhắc tới.
    """

    text = build_combined_intake_question(vehicle_type=vehicle_type, unanswered=INTAKE_TOPICS)
    assert text is not None
    items = _items(text)

    assert [line[:3] for line in items] == ["1. ", "2. "]
    assert "**Ngân sách**" in text


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_khach_da_neu_ngan_sach_thi_khong_con_du_chu_de_de_gop(
    vehicle_type: VehicleType,
) -> None:
    """Còn đúng một chủ đề thiếu → `None`, để `slot_planning` hỏi câu đơn.

    Trước 2026-08-26 ca này còn hai mục (mục đích + yêu cầu đặc biệt) nên vẫn
    gộp được. Bỏ mục "yêu cầu đặc biệt" thì nó rơi xuống ngưỡng `MIN_TOPICS` —
    đúng ý định của ngưỡng đó, không phải hồi quy.
    """

    text = build_combined_intake_question(vehicle_type=vehicle_type, unanswered=[SlotName.PURPOSE])

    assert text is None


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_a_single_missing_criterion_is_not_dressed_up_as_a_list(
    vehicle_type: VehicleType,
) -> None:
    """Danh sách một phần tử nói rằng còn mục 2 ở đâu đó — mà không có.

    `None` là tín hiệu cho `slot_planning` quay về câu hỏi đơn.
    """

    assert build_combined_intake_question(vehicle_type=vehicle_type, unanswered=[SlotName.BUDGET_MAX_VND]) is None


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_every_topic_has_a_bold_label_and_a_question(vehicle_type: VehicleType) -> None:
    text = build_combined_intake_question(vehicle_type=vehicle_type, unanswered=INTAKE_TOPICS)
    assert text is not None

    for line in _items(text):
        assert line[3:].startswith("**") and "**: " in line
        # Câu hỏi phải KẾT hoặc phải có dấu hỏi trước phần ví dụ. Mục "nhu cầu &
        # thói quen đi lại" cố ý mang một ví dụ mẫu trong ngoặc sau dấu hỏi —
        # đó là thứ dạy khách kiểu trả lời gộp ("đi làm khoảng 30 km mỗi ngày"),
        # và một câu hỏi kết thúc bằng ")" vẫn là một câu hỏi.
        assert "?" in line
        tail = line.rstrip()
        assert tail.endswith("?") or (tail.endswith(")") and "(ví dụ:" in tail)
