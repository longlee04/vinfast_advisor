"""Deterministic safeguards for raw LLM intent classification."""

import pytest

from src.agents.domain.canonical_text import build_canonical_text
from src.agents.domain.intent_reconciliation import is_test_drive_request, reconcile_intents
from src.agents.domain.pricing_intent import PricingIntent, classify_pricing_intent
from src.agents.domain.turn_understanding import reconcile_scope
from src.agents.domain.values import Intent, ScopeLabel, SlotName


@pytest.mark.parametrize(
    ("message", "raw", "slots", "mentions", "expected"),
    [
        (
            "Tôi cần xe 5 chỗ.",
            [],
            {SlotName.VEHICLE_TYPE: "CAR", SlotName.PASSENGER_COUNT: 5},
            [],
            [Intent.ADVISORY],
        ),
        (
            "Tư vấn giúp mẫu ô tô phù hợp.",
            [],
            {SlotName.VEHICLE_TYPE: "CAR"},
            [],
            [Intent.CATALOG_BROWSE],
        ),
        (
            "Nhà tôi bốn người, khoảng 500 triệu; VF 5 có hợp không?",
            [Intent.CATALOG_LOOKUP],
            {
                SlotName.VEHICLE_TYPE: "CAR",
                SlotName.PASSENGER_COUNT: 4,
                SlotName.BUDGET_MAX_VND: 500_000_000,
            },
            ["VF 5"],
            [Intent.ADVISORY, Intent.CATALOG_LOOKUP],
        ),
        (
            # [COMPARE_VEHICLES] Nhãn cũ ở đây là `CATALOG_LOOKUP`. Đổi có chủ
            # đích: hai mẫu xe kèm "khác nhau thế nào" là một lượt SO SÁNH, không
            # phải hai lượt tra cứu ghép lại. Điều bài test canh vẫn giữ nguyên —
            # một slot cũ trong phiên không được kéo lượt này về `ADVISORY`.
            "VF 5 và VF 7 khác nhau như thế nào?",
            [Intent.CATALOG_LOOKUP],
            {SlotName.PASSENGER_COUNT: 5},
            ["VF 5", "VF 7"],
            [Intent.COMPARE_VEHICLES],
        ),
        (
            "VF 5 của tôi pin tụt 9% sau 10 km, xe bị sao?",
            [Intent.CATALOG_LOOKUP],
            {
                SlotName.VEHICLE_TYPE: "CAR",
                SlotName.PASSENGER_COUNT: 5,
                SlotName.REQUIRED_RANGE_KM: 10,
            },
            ["VF 5"],
            [Intent.CATALOG_LOOKUP],
        ),
        (
            "VF 8 giá bao nhiêu?",
            [],
            {},
            ["VF 8"],
            [Intent.CATALOG_LOOKUP],
        ),
        (
            "VF 8 phí lăn bánh ở Hà Nội bao nhiêu?",
            [Intent.CATALOG_LOOKUP],
            {},
            ["VF 8"],
            [Intent.CATALOG_LOOKUP],
        ),
        (
            "VF 8 tính TCO thế nào?",
            [Intent.CATALOG_LOOKUP],
            {},
            ["VF 8"],
            [Intent.CATALOG_LOOKUP],
        ),
        (
            "Hôm nay thời tiết thế nào?",
            [],
            {},
            [],
            [],
        ),
    ],
)
def test_reconcile_intents_only_adds_labels_from_strong_customer_signals(
    message: str,
    raw: list[Intent],
    slots: dict[SlotName, object],
    mentions: list[str],
    expected: list[Intent],
) -> None:
    assert (
        reconcile_intents(
            user_message=message,
            raw_intents=raw,
            normalized_slots=slots,
            vehicle_mentions=mentions,
        )
        == expected
    )


@pytest.mark.parametrize(
    "message",
    [
        "VF 5 tính giá lăn bánh ở Hà Nội",
        "VF 5 phí lăn bánh ở Hà Nội",
        "VF 5 giá ra biển ở Hà Nội",
        "VF 5 chi phí ra biển ở Hà Nội",
        "VF 5 chi phí đăng ký ở Hà Nội",
        "VF 5 on-road price ở Hà Nội",
        "VF 5 tính TCO",
        "VF 5 chi phí sở hữu trong 5 năm",
    ],
)
def test_clear_pricing_request_keeps_the_lookup_route_and_drops_browse(message: str) -> None:
    """Câu định giá CÓ tên xe: giữ đường tra cứu, bỏ đường duyệt danh mục.

    Bản trước bỏ CẢ HAI nhãn. `intents` rỗng thì `nodes/route_intent` trả `{}`
    ngay, nên câu giá lăn bánh không bao giờ tới `_on_road_answer` — mà đó lại
    là chỗ DUY NHẤT tính được phí trước bạ, biển số, bảo hiểm. Điều nhánh định
    giá thật sự cần là không bị `CATALOG_BROWSE` cướp lượt, không phải mất luôn
    đường đi của chính mình.
    """

    result = reconcile_intents(
        user_message=message,
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=["VF 5"],
    )

    assert Intent.CATALOG_LOOKUP in result
    assert Intent.CATALOG_BROWSE not in result


def test_explicit_registration_request_keeps_pricing_route_with_vehicle_context() -> None:
    result = reconcile_intents(
        user_message="VF 5 phí đăng ký ở Hà Nội bao nhiêu?",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=["VF 5"],
    )

    assert Intent.CATALOG_LOOKUP in result
    assert Intent.CATALOG_BROWSE not in result


def test_a_pricing_request_without_a_named_model_stays_out_of_the_lookup_branch() -> None:
    """Không tên xe thì nhánh tra cứu không có gì để tra — chặng sau đề xuất trả lời."""

    result = reconcile_intents(
        user_message="tính giá lăn bánh đi",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=[],
    )

    assert Intent.CATALOG_LOOKUP not in result


def test_plain_price_question_remains_catalog_lookup() -> None:
    result = reconcile_intents(
        user_message="VF 5 giá bao nhiêu?",
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=["VF 5"],
    )

    assert result == [Intent.CATALOG_LOOKUP]


def test_pricing_classifier_keeps_semantic_variant_for_llm_fallback() -> None:
    message = "VF 5 tổng tiền sở hữu trong 5 năm là bao nhiêu?"

    assert classify_pricing_intent(message, build_canonical_text(message)) is PricingIntent.NONE


def test_short_vehicle_answer_keeps_active_advisory_context() -> None:
    assert reconcile_intents(
        user_message="ô tô nhé",
        raw_intents=[],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        known_slots={SlotName.BUDGET_MAX_VND: 500_000_000},
        expected_slot=SlotName.VEHICLE_TYPE,
        vehicle_mentions=[],
    ) == [Intent.ADVISORY]


def test_catalog_browse_request_wins_over_stale_advisory_context() -> None:
    assert reconcile_intents(
        user_message="tất cả các xe",
        raw_intents=[],
        normalized_slots={},
        known_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
        },
        expected_slot=None,
        vehicle_mentions=[],
    ) == [Intent.CATALOG_BROWSE]


@pytest.mark.parametrize(
    "message",
    [
        "Tôi muốn tư vấn xe",
        "Tôi muốn mua xe",
        "Tôi muốn xem xe khác",
        "Tư vấn giúp tôi mẫu xe khác",
    ],
)
def test_generic_vehicle_discovery_browses_catalog_instead_of_reusing_old_needs(
    message: str,
) -> None:
    assert reconcile_intents(
        user_message=message,
        raw_intents=[Intent.ADVISORY],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        known_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
            SlotName.PASSENGER_COUNT: 4,
        },
        expected_slot=None,
        vehicle_mentions=[],
    ) == [Intent.CATALOG_BROWSE]


def test_new_personal_criteria_still_use_advisory_scoring() -> None:
    assert reconcile_intents(
        user_message="Tôi muốn xe khác tầm 700 triệu cho 5 người",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 700_000_000,
            SlotName.PASSENGER_COUNT: 5,
        },
        known_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
            SlotName.PASSENGER_COUNT: 4,
        },
        vehicle_mentions=[],
    ) == [Intent.ADVISORY]


def test_named_family_listing_wins_over_stale_advisory_context() -> None:
    assert reconcile_intents(
        user_message="tất cả các mẫu VF6",
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={},
        known_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
            SlotName.PASSENGER_COUNT: 4,
        },
        expected_slot=None,
        vehicle_mentions=["VF 6"],
    ) == [Intent.CATALOG_LOOKUP]


def test_named_model_consultation_without_personal_need_is_targeted_lookup() -> None:
    """Naming one model must not silently reuse old criteria to rank other models."""

    assert reconcile_intents(
        user_message="Tôi muốn tư vấn xe VF5",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        known_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.BUDGET_MAX_VND: 500_000_000,
            SlotName.PASSENGER_COUNT: 4,
        },
        expected_slot=None,
        vehicle_mentions=["VF 5"],
    ) == [Intent.CATALOG_LOOKUP]


@pytest.mark.parametrize("message", ["VF9 đi", "VF 9 nhé", "xem VF9 đi"])
def test_short_named_model_followup_is_lookup_even_when_raw_intent_is_missing(
    message: str,
) -> None:
    assert reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        known_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=["VF 9"],
    ) == [Intent.CATALOG_LOOKUP]


def test_named_model_consultation_with_current_need_remains_advisory() -> None:
    """Current-turn criteria make a named model part of a real suitability request."""

    assert reconcile_intents(
        user_message="Tư vấn VF5 cho nhà 5 người, ngân sách 500 triệu",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={
            SlotName.VEHICLE_TYPE: "CAR",
            SlotName.PASSENGER_COUNT: 5,
            SlotName.BUDGET_MAX_VND: 500_000_000,
        },
        vehicle_mentions=["VF 5"],
    ) == [Intent.ADVISORY]


def test_pure_comparison_removes_false_positive_advisory_label() -> None:
    """[COMPARE_VEHICLES] Nhãn cũ ở đây là `CATALOG_LOOKUP`.

    Đổi có chủ đích: một câu nêu HAI mẫu xe kèm "khác nhau thế nào" không được
    trả về hai bảng thông số nối đuôi nhau. Điều bài test này canh — nhãn
    `ADVISORY` sai bị gỡ — vẫn giữ nguyên.
    """

    assert reconcile_intents(
        user_message="VF 5 và VF 7 khác nhau thế nào?",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={},
        vehicle_mentions=["VF 5", "VF 7"],
    ) == [Intent.COMPARE_VEHICLES]


def test_pure_price_lookup_resolved_from_memory_removes_false_advisory() -> None:
    assert reconcile_intents(
        user_message="Mẫu còn lại giá bao nhiêu?",
        raw_intents=[Intent.ADVISORY, Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=["VF 7"],
    ) == [Intent.CATALOG_LOOKUP]


@pytest.mark.parametrize(
    ("message", "mentions"),
    [
        (
            "Tôi đang cân nhắc VF 5 và VF 7, nhưng loại VF 5 vì hơi chật.",
            ["VF 5", "VF 7"],
        ),
        ("Tôi phân vân VF 6 với VF 7, chắc bỏ VF 6.", ["VF 6", "VF 7"]),
        ("VF 8 thì loại, tôi giữ lại VF 7.", ["VF 8", "VF 7"]),
        ("Tôi không chọn VF 5 nữa, đang xem VF 7.", ["VF 5", "VF 7"]),
    ],
)
def test_vehicle_selection_language_is_advisory_even_when_raw_intent_is_empty(
    message: str,
    mentions: list[str],
) -> None:
    assert reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=mentions,
    ) == [Intent.ADVISORY]


@pytest.mark.parametrize(
    "message",
    [
        "tất cả các mẫu vf8 hiện tại",
        "Cho tôi danh sách VF 8 đang bán",
        "Show toàn bộ phiên bản VF8",
    ],
)
def test_named_model_listing_overrides_false_catalog_browse_label(
    message: str,
) -> None:
    """A concrete model is a lookup target even when the LLM focuses on listing words."""

    assert reconcile_intents(
        user_message=message,
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={},
        vehicle_mentions=["VF 8"],
    ) == [Intent.CATALOG_LOOKUP]


def test_vehicle_selection_removes_false_catalog_label_without_a_catalog_question() -> None:
    assert reconcile_intents(
        user_message="Tôi đang cân nhắc VF 5 và VF 7, nhưng loại VF 5 vì hơi chật.",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=["VF 5", "VF 7"],
    ) == [Intent.ADVISORY]


def test_vehicle_selection_keeps_catalog_label_when_price_is_also_requested() -> None:
    assert reconcile_intents(
        user_message="Tôi loại VF 5; VF 7 giá bao nhiêu?",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=["VF 5", "VF 7"],
    ) == [Intent.ADVISORY, Intent.CATALOG_LOOKUP]


def test_vehicle_attribute_word_loai_is_not_a_selection_signal() -> None:
    assert reconcile_intents(
        user_message="VF 5 dùng loại pin gì?",
        raw_intents=[Intent.CATALOG_LOOKUP],
        normalized_slots={},
        vehicle_mentions=["VF 5"],
    ) == [Intent.CATALOG_LOOKUP]


@pytest.mark.parametrize(
    "message",
    [
        "Tôi đang xem VF 7, giá bao nhiêu?",
        "Tôi quan tâm VF 5, dùng loại pin gì?",
    ],
)
def test_consideration_word_does_not_override_a_specific_catalog_question(
    message: str,
) -> None:
    assert reconcile_intents(
        user_message=message,
        raw_intents=[Intent.ADVISORY],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=["VF 7" if "VF 7" in message else "VF 5"],
    ) == [Intent.CATALOG_LOOKUP]


@pytest.mark.parametrize(
    "message",
    [
        "tôi chốt mẫu evo grand, cho tôi lái thử",
        "tôi chốt mẫu evo grand",
        "chốt con vf 5",
    ],
)
def test_commit_to_named_model_is_lookup_not_advisory(message: str) -> None:
    mention = "VF 5" if "vf 5" in message.casefold() else "Evo Grand"
    assert reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=[mention],
    ) == [Intent.CATALOG_LOOKUP]


def test_commit_to_named_model_drops_false_advisory_label() -> None:
    assert reconcile_intents(
        user_message="tôi chốt mẫu evo grand",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={},
        vehicle_mentions=["Evo Grand"],
    ) == [Intent.CATALOG_LOOKUP]


@pytest.mark.parametrize(
    "message",
    ["cho tôi lái thử", "tôi muốn đặt lịch lái thử", "ok đặt lịch lái thứ", "test drive vf5"],
)
def test_test_drive_request_detection(message: str) -> None:
    assert is_test_drive_request(message) is True


@pytest.mark.parametrize("message", ["xe này giá bao nhiêu", "tư vấn xe vf5"])
def test_non_test_drive_request(message: str) -> None:
    assert is_test_drive_request(message) is False


# ── Bấm nút chọn loại xe KHÔNG phải yêu cầu duyệt danh mục ───────────────────
#
# Bug thật, đọc từ `turn_traces` prod 2026-08-26 — lặp ở MỌI phiên tư vấn:
#
#     "tôi cần tư vấn xe"  -> bot hỏi "ô tô điện hay xe máy điện ạ?"
#     "Ô tô điện"          -> intents=["CATALOG_BROWSE"], slots_gained={}
#
# Khách bấm đúng cái nút bot vừa đưa ra, mà lượt đó bị đọc thành "cho tôi xem
# danh mục ô tô điện" và `vehicle_type` không được ghi nhận. Luồng chỉ chạy tiếp
# nhờ `inferred_vehicle_type` đoán lại từ ngân sách ở lượt sau — sống bằng một
# phép đoán thay vì bằng câu trả lời khách vừa đưa.


@pytest.mark.parametrize(
    ("message", "vehicle_type"),
    [("Ô tô điện", "CAR"), ("Xe máy điện", "ELECTRIC_MOTORBIKE"), ("ô tô", "CAR")],
)
@pytest.mark.parametrize("raw", [[], [Intent.CATALOG_BROWSE], [Intent.ADVISORY]])
def test_tra_loi_cau_hoi_loai_xe_la_luot_tu_van(message: str, vehicle_type: str, raw: list) -> None:
    """Nhãn của LLM phải bị BỎ, không chỉ bị bỏ qua.

    `intents` khởi tạo từ `raw_intents`, nên để nguyên thì câu đó vẫn rời hàm
    mang nhãn `CATALOG_BROWSE` và graph vẫn đi liệt kê danh mục.
    """

    result = reconcile_intents(
        user_message=message,
        raw_intents=raw,
        normalized_slots={SlotName.VEHICLE_TYPE: vehicle_type},
        vehicle_mentions=[],
        known_slots={},
        expected_slot=SlotName.VEHICLE_TYPE,
    )

    assert result == [Intent.ADVISORY]


def test_cau_tran_chi_noi_loai_xe_luon_la_loi_dap() -> None:
    """Bất biến này ĐẢO CHIỀU 2026-08-26, sau khi chạy thật trên prod:

        bot  : "Anh/chị cho em xin loại xe nhé — ô tô điện hay xe máy điện ạ?"
        khách: "Ô tô điện"
        bot  : "VinFast hiện có dải sản phẩm… Dưới đây là 7 dòng ô tô điện…"

    Khách bấm đúng cái nút bot vừa đưa ra và nhận về một bảng danh mục.

    Bản vá đầu dựa vào `expected_slot`, và KHÔNG cứu được: chain suy
    `inferred_vehicle_type` TRƯỚC bước trích, nên `expected_slot` đã nhảy sang
    slot kế tiếp đúng ở cái lượt cần nó. Tín hiệu bền là hình dạng CÂU: một câu
    không mang gì ngoài tên loại xe chính là chuỗi mà nút gửi đi.
    """

    result = reconcile_intents(
        user_message="ô tô điện",
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={},
        vehicle_mentions=[],
        known_slots={},
        expected_slot=None,
    )

    assert result == [Intent.ADVISORY]


@pytest.mark.parametrize(
    "message",
    ["ô tô điện gồm những xe nào", "tất cả các mẫu xe", "cho tôi xem danh sách xe", "các mẫu xe hiện có"],
)
def test_cau_xin_danh_muc_that_van_la_duyet(message: str) -> None:
    """Chiều ÂM, và là lý do vị từ mới khớp TOÀN CHUỖI.

    Nới thành "hễ có chữ ô tô là lời đáp" thì mọi câu xin danh mục cũng thành
    lời đáp, và `CATALOG_BROWSE` mất sạch việc của nó.
    """

    result = reconcile_intents(
        user_message=message,
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={},
        vehicle_mentions=[],
        known_slots={},
        expected_slot=None,
    )

    assert Intent.CATALOG_BROWSE in result


def test_cau_neu_ten_mau_khong_bao_gio_la_loi_dap_loai_xe() -> None:
    """Vế thứ ba của điều kiện, và nó bắt buộc.

    "tất cả các mẫu vf8 hiện tại" cũng trích ra `vehicle_type` khi phiên chưa
    biết loại xe, nên hai vế đầu khớp — nhưng câu đó nêu TÊN MỘT MẪU, tức là tra
    cứu. Một câu trả lời loại xe không bao giờ kèm tên mẫu.
    """

    result = reconcile_intents(
        user_message="tất cả các mẫu vf8 hiện tại",
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=["VF 8"],
        known_slots={},
        expected_slot=SlotName.VEHICLE_TYPE,
    )

    assert Intent.ADVISORY not in result
    assert Intent.CATALOG_LOOKUP in result


def test_loi_go_thieu_chu_van_la_xin_lai_thu() -> None:
    """Đọc từ `turn_traces` prod 2026-08-26: "tôi muốn đặt lịch lái hử" bị đóng
    lượt vì lạc đề.

    Khách đang xin đúng cái việc cả luồng dẫn tới, mà mất vì một chữ "t". Cụm
    "lái hử" không mang nghĩa nào khác trong tiếng Việt nên nhận nó là an toàn.
    """

    assert is_test_drive_request("tôi muốn đặt lịch lái hử") is True
    assert is_test_drive_request("lai hu") is True
    assert is_test_drive_request("tôi muốn đặt lịch lái thử") is True
    assert is_test_drive_request("lái xe cẩn thận") is False


@pytest.mark.parametrize(
    "message",
    [
        "đăng ký lái thử",
        "đặt lịch lái thử",
        "tôi muốn tới lái thử xe",
        "cho anh đặt lịch",
    ],
)
def test_test_drive_request_is_never_out_of_scope(message: str) -> None:
    """Xin lái thử là dịch vụ hệ thống CÓ — nhãn ngoài phạm vi của LLM không thắng.

    Đo trên prod 2026-08-27: *"đăng ký lái thử"* về với `scope_label:
    OUT_OF_SCOPE` và `intents: []`. Bằng chứng tất định đã tính sẵn
    (`is_test_drive_request`), chỉ thiếu chỗ nối vào quyết định phạm vi.
    """

    assert is_test_drive_request(message) is True
    assert (
        reconcile_scope(
            raw_scope=ScopeLabel.OUT_OF_SCOPE,
            intents=[],
            user_message=message,
            vehicle_mentions=[],
        )
        is ScopeLabel.IN_SCOPE
    )


def test_scope_rescue_does_not_swallow_a_real_rejection() -> None:
    """Câu ngoài phạm vi THẬT vẫn giữ nhãn — cửa lái thử không nới danh sách."""

    assert (
        reconcile_scope(
            raw_scope=ScopeLabel.OUT_OF_SCOPE,
            intents=[],
            user_message="tư vấn giúp tôi cách nấu phở",
            vehicle_mentions=[],
        )
        is ScopeLabel.OUT_OF_SCOPE
    )


@pytest.mark.parametrize(
    "message",
    ["giá lăn bánh VF 5", "gia lan banh vf 5", "tính giá lăn bánh VF 5 ở Hà Nội"],
)
def test_a_named_on_road_price_question_keeps_a_route_to_the_lookup_branch(message: str) -> None:
    """Hỏi giá lăn bánh CÓ tên xe phải còn đường tới `_on_road_answer`.

    BUG THẬT: bản vá 2026-08-27 cho nhánh định giá `discard` cả
    `CATALOG_LOOKUP` lẫn `CATALOG_BROWSE` mà không thêm nhãn nào thay — `intents`
    rỗng thì `nodes/route_intent` trả `{}` và câu giá lăn bánh chết im, kể cả
    khi khách đã nêu đúng tên xe.
    """

    assert classify_pricing_intent(message, build_canonical_text(message)) is not PricingIntent.NONE
    assert Intent.CATALOG_LOOKUP in reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=["VF 5"],
    )


@pytest.mark.parametrize(
    "message",
    [
        "tính giá lăn bánh đi",
        "tinh gia lan banh",
        "giá ra biển bao nhiêu",
        "phí trước bạ tính thế nào",
        "truoc ba bao nhieu",
    ],
)
def test_a_pricing_question_is_never_out_of_scope(message: str) -> None:
    """Câu hỏi định giá không bao giờ là câu ngoài phạm vi.

    Đo trên prod 2026-08-27: *"tính giá lăn bánh"* nhận `scope_label:
    OUT_OF_SCOPE`. Cue ngân sách cũ không có "lăn bánh", "ra biển", "trước bạ".
    """

    assert (
        reconcile_scope(
            raw_scope=ScopeLabel.OUT_OF_SCOPE,
            intents=[],
            user_message=message,
            vehicle_mentions=[],
        )
        is ScopeLabel.IN_SCOPE
    )
