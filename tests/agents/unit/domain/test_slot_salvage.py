"""Fallback parsing for the exact slot the agent just asked about."""

from __future__ import annotations

import pytest

from src.agents.domain.budget_parsing import NO_BUDGET_LIMIT_VND
from src.agents.domain.slot_salvage import (
    is_non_answer,
    salvage_slot,
    salvaged_vehicle_type,
)
from src.agents.domain.values import SlotName, VehicleType


def test_free_text_purpose_keeps_the_customer_sentence() -> None:
    assert salvage_slot(SlotName.PURPOSE, "Chủ yếu đi làm hàng ngày") == "Chủ yếu đi làm hàng ngày"


@pytest.mark.parametrize(
    ("message", "expected"),
    [("4 chỗ", 4), ("nhà em năm người", 5), ("xe 7 chỗ", 7)],
)
def test_passenger_count_reads_digits_and_words(message: str, expected: int) -> None:
    assert salvage_slot(SlotName.PASSENGER_COUNT, message, VehicleType.CAR) == expected


def test_no_budget_limit_has_a_non_filtering_numeric_sentinel() -> None:
    assert salvage_slot(SlotName.BUDGET_MAX_VND, "bao nhiêu cũng được") == NO_BUDGET_LIMIT_VND


def test_question_is_not_swallowed_into_a_free_text_slot() -> None:
    assert salvage_slot(SlotName.PURPOSE, "VF 5 giá bao nhiêu ạ?") is None


@pytest.mark.parametrize(
    "message",
    ["chưa biết", "không biết nữa", "tùy em", "anh không", "không ạ", "thôi"],
)
def test_evasive_or_bare_refusal_is_a_non_answer(message: str) -> None:
    assert is_non_answer(message)


@pytest.mark.parametrize(
    "message",
    ["không thích xe màu đỏ", "không cần đi xa, chỉ đi làm quanh nhà"],
)
def test_qualified_negative_is_a_real_answer(message: str) -> None:
    assert not is_non_answer(message)
    assert salvage_slot(SlotName.PURPOSE, message) == message


@pytest.mark.parametrize(
    "message",
    [
        "tiền không thành vấn đề",
        "tài chính không thành vấn đề",
        "tien khong thanh van de",
        "giá nào cũng được",
        "tầm nào cũng được",
        "ngân sách mở",
        "kinh phí không quan trọng",
    ],
)
def test_unbounded_budget_phrases_resolve_to_the_sentinel(message: str) -> None:
    """Khách nói không đặt trần giá bằng rất nhiều cách ngoài "bao nhiêu cũng được".

    Cụm nào không khớp thì lượt đó không trích được slot nào, và agent hỏi lại
    đúng câu ngân sách nó vừa hỏi — vòng lặp khách không có cách nào thoát trừ
    khi tự nghĩ ra một con số.
    """

    assert salvage_slot(SlotName.BUDGET_MAX_VND, message) == NO_BUDGET_LIMIT_VND


@pytest.mark.parametrize("message", ["800 triệu", "khoảng 500 triệu", "dưới 1 tỷ"])
def test_real_budget_numbers_are_not_swallowed_by_the_unbounded_phrases(message: str) -> None:
    value = salvage_slot(SlotName.BUDGET_MAX_VND, message)
    assert value is not None and value != NO_BUDGET_LIMIT_VND


# ── Nhánh xe khách chọn khi được hỏi thẳng loại xe ────────────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # Cách người Việt thường gõ cho nhánh ô tô.
        ("xe ô tô điện", VehicleType.CAR),
        ("ô tô điện", VehicleType.CAR),
        ("ôtô", VehicleType.CAR),
        ("oto", VehicleType.CAR),
        ("xe hơi", VehicleType.CAR),
        ("xe điện 4 bánh", VehicleType.CAR),
        ("xe dien bon banh", VehicleType.CAR),
        ("cho em xin loại ô tô nhé", VehicleType.CAR),
        # ... và cho nhánh xe máy.
        ("xe máy điện", VehicleType.ELECTRIC_MOTORBIKE),
        ("xe may dien", VehicleType.ELECTRIC_MOTORBIKE),
        ("xe tay ga điện", VehicleType.ELECTRIC_MOTORBIKE),
        ("xe điện 2 bánh", VehicleType.ELECTRIC_MOTORBIKE),
        ("xe hai bánh", VehicleType.ELECTRIC_MOTORBIKE),
        ("mô tô điện", VehicleType.ELECTRIC_MOTORBIKE),
    ],
)
def test_salvaged_vehicle_type_maps_common_phrasings(message: str, expected: VehicleType) -> None:
    assert salvaged_vehicle_type(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "",
        "   ",
        # "xe điện" đúng cho CẢ HAI dòng xe VinFast — chọn một là bịa.
        "xe điện",
        "tôi muốn tư vấn xe",
        # Nêu cả hai loại thì khách vẫn chưa chọn.
        "cho tôi xem cả ô tô và xe máy điện",
        # Câu lạc đề hẳn. Khớp theo RANH GIỚI TỪ nên "o tô" trong "cho tôi" không
        # biến câu này thành một lựa chọn ô tô — đây chính là chỗ
        # `vehicle_type_lock.explicit_vehicle_type` trả sai vì nó tìm chuỗi con.
        "cho tôi hỏi giờ mở cửa showroom",
        "cho toi biet chinh sach bao hanh",
    ],
)
def test_salvaged_vehicle_type_refuses_to_guess(message: str) -> None:
    assert salvaged_vehicle_type(message) is None


# ── "thôi không" và họ hàng (Sếp 2026-08-26) ─────────────────────────────────


@pytest.mark.parametrize(
    "message",
    ["thôi không", "thôi không cần", "không thôi", "thôi không cần gì", "không cần thôi"],
)
def test_ghep_hai_tu_tu_choi_van_la_tu_choi(message: str) -> None:
    """Bug thật đo trên prod: `"thôi không"` trượt và khách nhận lời từ chối phạm
    vi. Mẫu nhận `"thôi"` ở đầu rồi đòi đuôi thuộc tập từ đệm, mà `"không"` lại
    không có trong tập đó — nên đúng cách ghép tự nhiên nhất lại rơi ra ngoài.
    """

    assert is_non_answer(message)


@pytest.mark.parametrize(
    "message",
    [
        # Đuôi vẫn phải là tập ĐÓNG. Mỗi câu dưới đây mang thông tin thật, và
        # đọc chúng thành "khách không cần gì" là ăn mất câu trả lời — đúng kiểu
        # sai của bản nháp để `k` làm viết tắt và nuốt "khoá chống trộm".
        "thôi tôi muốn xem xe khác",
        "không, cho tôi xem xe khác",
        "khoá chống trộm",
        "không gian rộng rãi",
        "thôi để tôi hỏi giá trước",
    ],
)
def test_cau_mang_thong_tin_that_khong_bi_doc_thanh_tu_choi(message: str) -> None:
    assert not is_non_answer(message)


# ── Loại xe: câu trả lời rõ ràng nhất mà LLM vẫn bỏ sót ──────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Ô tô điện", "CAR"),
        ("ô tô", "CAR"),
        ("oto dien", "CAR"),
        ("xe hơi", "CAR"),
        ("Xe máy điện", "ELECTRIC_MOTORBIKE"),
        ("xe máy", "ELECTRIC_MOTORBIKE"),
        ("xe tay ga", "ELECTRIC_MOTORBIKE"),
        ("2 bánh", "ELECTRIC_MOTORBIKE"),
    ],
)
def test_cuu_duoc_loai_xe_tu_chinh_chu_tren_nut(message: str, expected: str) -> None:
    """Đo trên `turn_traces` prod 2026-08-26: lượt "Ô tô điện" — chính chữ in
    trên cái nút bot vừa đưa ra — trả về `slots_gained={}`.

    Bộ trích LLM không lấy được loại xe từ câu trả lời rõ ràng nhất có thể, mà
    `salvage_slot` lại không có nhánh nào cho slot này. Phiên đi tiếp KHÔNG biết
    khách chọn gì, chỉ sống nhờ `inferred_vehicle_type` đoán lại từ ngân sách ở
    lượt sau — một phép đoán thay cho một câu trả lời.
    """

    assert salvage_slot(SlotName.VEHICLE_TYPE, message) == expected


def test_xe_may_xet_truoc_o_to() -> None:
    """"xe máy điện" chứa cả "xe" lẫn "điện" — mẫu ô tô lỏng tay sẽ nuốt nó."""

    assert salvage_slot(SlotName.VEHICLE_TYPE, "xe máy điện") == "ELECTRIC_MOTORBIKE"


@pytest.mark.parametrize("message", ["tôi chưa biết", "500 triệu", "không", "tuỳ em"])
def test_cau_khong_noi_loai_xe_thi_khong_doan(message: str) -> None:
    """Đoán hộ ở đây là chọn thay khách cả một nhánh catalog."""

    assert salvage_slot(SlotName.VEHICLE_TYPE, message) is None
