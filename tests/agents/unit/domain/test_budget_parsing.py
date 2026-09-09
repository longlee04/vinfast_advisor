"""Budget parsing follows real customer phrasing and never raises."""

from __future__ import annotations

import pytest

from src.agents.domain.budget_parsing import (
    NO_BUDGET_LIMIT_PATTERN,
    NO_BUDGET_LIMIT_VND,
    mentions_money,
    parse_budget_range,
    parse_budget_vnd,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("700 triệu", 700_000_000),
        ("1 tỷ 2", 1_200_000_000),
        ("1ty2", 1_200_000_000),
        ("700tr", 700_000_000),
        # "khoảng X" là ƯỚC LƯỢNG: trần nới đúng +100 triệu (xem `APPROX_BAND_VND`).
        ("khoảng 800 triệu", 800_000_000),
        ("dưới 1 tỷ", 1_000_000_000),
        ("nửa tỷ", 500_000_000),
        ("1,5 tỷ", 1_500_000_000),
        ("1.200.000.000", 1_200_000_000),
        ("700", 700_000_000),
        ("700 đến 900 triệu", 900_000_000),
    ],
)
def test_parse_budget_understands_customer_phrasings(raw: str, expected: int) -> None:
    assert parse_budget_vnd(raw) == expected


@pytest.mark.parametrize("raw", ["bao nhiêu cũng được", "chưa biết", "", "abc", -1, 1.5, float("nan"), True])
def test_parse_budget_returns_none_for_unsupported_values(raw: object) -> None:
    assert parse_budget_vnd(raw) is None  # type: ignore[arg-type]


def test_no_budget_sentinel_fits_the_slot_column_it_gets_written_to() -> None:
    """Sentinel phải vừa cột `conversation_slots.slot_value_number`.

    Cột là NUMERIC(14, 3) nên chặn ở absolute value < 10^11. Sentinel cũ đúng
    bằng 10^11: mọi lượt "bao nhiêu cũng được" vỡ ở INSERT, rồi handler
    `SQLAlchemyError` toàn cục nuốt traceback và trả 503 "auth_unavailable" —
    nhìn như lỗi Auth chứ không ai lần ra được ngân sách.
    """

    from decimal import Decimal

    from src.agents.models import ConversationSlotRow

    column = ConversationSlotRow.__table__.c.slot_value_number.type
    limit = Decimal(10) ** (column.precision - column.scale)

    assert Decimal(NO_BUDGET_LIMIT_VND) < limit


def test_no_budget_sentinel_still_exceeds_every_catalog_price() -> None:
    """Sentinel vẫn phải cao hơn mọi giá xe, nếu không nó thành bộ lọc thật."""

    assert NO_BUDGET_LIMIT_VND > 5_000_000_000


# ── Khoảng ngân sách theo cách khách thật gõ ──────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected_min", "expected_max"),
    [
        # Khoảng tường minh, có và không có khoảng trắng quanh dấu nối.
        ("300-500 triệu", 300_000_000, 500_000_000),
        ("khoảng 200 đến 300", 200_000_000, 300_000_000),
        ("200 -300", 200_000_000, 300_000_000),
        ("từ 300 đến 700 triệu", 300_000_000, 700_000_000),
        # Đơn vị lan từ đầu mút sau sang đầu mút trước trong cùng một khoảng.
        ("1-2 tỷ", 1_000_000_000, 2_000_000_000),
        # Một phía: sàn không trần, và trần không sàn.
        ("lớn hơn 500 triệu", 500_000_000, NO_BUDGET_LIMIT_VND),
        # "từ X" trần trụi cũng là một SÀN, không phải trần.
        ("từ 900 triệu", 900_000_000, NO_BUDGET_LIMIT_VND),
        ("ô tô điện từ 900 triệu", 900_000_000, NO_BUDGET_LIMIT_VND),
        ("trên 500 triệu", 500_000_000, NO_BUDGET_LIMIT_VND),
        ("từ 500 triệu trở lên", 500_000_000, NO_BUDGET_LIMIT_VND),
        ("nhỏ hơn 300 triệu", None, 300_000_000),
        ("dưới 300 triệu", None, 300_000_000),
        ("tối đa 300 triệu", None, 300_000_000),
        # Ước lượng: ±100 triệu quanh con số khách nói, cố định theo mọi mức giá.
        ("tầm 400 triệu", 300_000_000, 400_000_000),
        ("cỡ 400 triệu", 300_000_000, 400_000_000),
        ("ô tô điện khoảng 900 triệu", 800_000_000, 900_000_000),
        # Một con số trần trụi vẫn là TRẦN, không phải khoảng.
        ("700 triệu", None, 700_000_000),
    ],
)
def test_parse_budget_range_reads_the_direction_of_the_sentence(
    raw: str, expected_min: int | None, expected_max: int
) -> None:
    """Hướng của câu là thông tin. `max()` của mọi số trong câu bỏ mất nó."""

    budget = parse_budget_range(raw)

    assert budget.min_vnd == expected_min
    assert budget.max_vnd == expected_max


def test_a_lower_bound_only_sentence_is_not_read_as_a_ceiling() -> None:
    """Bug gốc: "lớn hơn 500 triệu" bị đọc thành trần 500 triệu — ngược hẳn ý khách."""

    budget = parse_budget_range("lớn hơn 500 triệu")

    assert budget.min_vnd == 500_000_000
    assert budget.has_upper_limit is False


def test_an_explicit_range_beats_the_approximation_word_in_the_same_sentence() -> None:
    """ "khoảng 200 đến 300" có hai đầu mút thật — không phải ước lượng quanh 200."""

    assert parse_budget_range("khoảng 200 đến 300") == parse_budget_range("200-300 triệu")


def test_a_separator_in_another_clause_does_not_invent_a_range() -> None:
    """Chữ "đến" ngoài phạm vi hai con số không được biến một số thành một khoảng."""

    budget = parse_budget_range("anh đến showroom xem xe, ngân sách 500 triệu")

    assert budget.min_vnd is None
    assert budget.max_vnd == 500_000_000


def test_a_number_that_is_not_the_budget_keeps_its_own_unit() -> None:
    """ "7 người" không được lấy đơn vị "tỷ" của con số ngân sách đứng sau nó."""

    budget = parse_budget_range("Ô tô cho 7 người, tầm 1ty2")

    # Trần là chính con số khách nói (Sếp 2026-08-26), không cộng thêm biên.
    assert budget.max_vnd == 1_200_000_000


def test_the_ceiling_helper_reads_the_same_range() -> None:
    """Chỉ một nguồn parse: luồng tư vấn và mọi chỗ gọi khác không được lệch nhau."""

    for raw in ("300-500 triệu", "lớn hơn 500 triệu", "tầm 400 triệu", "dưới 1 tỷ"):
        assert parse_budget_vnd(raw) == parse_budget_range(raw).max_vnd


def test_from_x_is_a_floor_not_a_ceiling() -> None:
    """Bug đã quan sát: "từ 900 triệu" bị đọc thành TRẦN 900 triệu.

    Hệ quả là nó cho ra kết quả y hệt "khoảng 900 triệu" — cùng một trần không
    sàn — và cả hai cùng trả về ba mẫu rẻ nhất catalog.
    """

    floor_only = parse_budget_range("ô tô điện từ 900 triệu")
    approximate = parse_budget_range("ô tô điện khoảng 900 triệu")

    assert floor_only.min_vnd == 900_000_000
    assert floor_only.has_upper_limit is False
    assert floor_only != approximate


def test_the_approximation_band_does_not_scale_with_the_amount() -> None:
    """±100 triệu là số tiền cố định: "khoảng 900" không được rộng gấp đôi "khoảng 400"."""

    small = parse_budget_range("khoảng 400 triệu")
    large = parse_budget_range("khoảng 900 triệu")

    assert large.max_vnd - large.min_vnd == small.max_vnd - small.min_vnd


def test_a_motorbike_sized_amount_does_not_get_the_car_sized_band() -> None:
    """ "tầm 30 triệu" là câu của người mua XE MÁY — ±100 triệu ở đây là vô nghĩa.

    Biên ±100 triệu áp thẳng vào đây sẽ nới trần lên 130 triệu, tức gợi ý cả những
    mẫu đắt gấp bốn lần mức khách nói.
    """

    budget = parse_budget_range("xe máy điện tầm 30 triệu")

    # Biên tỉ lệ vẫn áp cho xe máy, nhưng chỉ XUỐNG DƯỚI: trần đúng bằng con số
    # khách nói (Sếp 2026-08-26).
    assert budget.min_vnd == 24_000_000
    assert budget.max_vnd == 30_000_000


def test_a_word_containing_tu_is_not_read_as_a_floor() -> None:
    """ "tuần" chứa "tu" nhưng không phải "từ" — câu này vẫn là một trần."""

    budget = parse_budget_range("tuần này em cần xe giá 500 triệu")

    assert budget.min_vnd is None
    assert budget.max_vnd == 500_000_000


def test_an_approximation_word_in_another_clause_does_not_widen_the_budget() -> None:
    """ "quãng đường" là QUÃNG ĐƯỜNG, không phải "quãng" ước lượng.

    Câu này nêu một ngân sách CHÍNH XÁC 1,2 tỷ; chữ "quang" của mệnh đề quãng
    đường không được biến nó thành khoảng 1,1–1,3 tỷ.
    """

    budget = parse_budget_range("toi can xe 5 cho, ngan sach 1 ty 2, quang duong 300km, co sac tai nha")

    assert budget.min_vnd is None
    assert budget.max_vnd == 1_200_000_000


# ── Con số khách NÓI RA ───────────────────────────────────────────────────────


def test_an_approximate_amount_keeps_the_figure_the_customer_said() -> None:
    """Sếp 2026-08-25: khách gõ "khoảng 500 triệu" mà bot đáp "ngân sách khoảng
    600 triệu" là nói lại một con số họ không hề nói.

    Dải nới XUỐNG DƯỚI (400 triệu) để không giấu mẫu rẻ hơn mà vẫn hợp. Trần thì
    KHÔNG nới: Sếp 2026-08-26 — "nếu người dùng cung cấp tài chính thì đề xuất
    không được vượt quá tài chính".

    Bug thật cùng ngày: khách nói "khoảng 800 triệu", trần nới thành 900, và bot
    đề xuất VF 8 All New giá 899 triệu — vượt 12,4% mức khách nêu."""

    parsed = parse_budget_range("anh có khoảng 500 triệu")

    assert parsed.min_vnd == 400_000_000
    assert parsed.max_vnd == 500_000_000
    assert parsed.stated_vnd == 500_000_000


def test_a_range_the_customer_stated_has_no_separate_figure() -> None:
    """Khách tự nêu khoảng thì HAI BIÊN đã là lời họ — không có con số thứ ba.

    Quan trọng vì "khoảng 500 triệu" và "từ 400 đến 600 triệu" cho ra CÙNG một
    cặp biên. `stated_vnd` là thứ duy nhất tách được hai câu đó, nên câu nhắc lại
    không bao giờ gọi một khoảng khách tự nêu là "khoảng 500 triệu"."""

    parsed = parse_budget_range("từ 400 đến 600 triệu")

    assert (parsed.min_vnd, parsed.max_vnd) == (400_000_000, 600_000_000)
    assert parsed.stated_vnd is None


def test_a_single_bound_has_no_separate_figure() -> None:
    """"dưới 500 triệu" — biên đã là lời khách, không nới nên không cần giữ thêm."""

    assert parse_budget_range("dưới 500 triệu").stated_vnd is None


def test_the_salvage_path_also_keeps_the_figure_the_customer_said() -> None:
    """Có HAI đường điền ngân sách, và bản vá đầu chỉ chạm một.

    Khi khách trả lời đúng câu hỏi ngân sách bot vừa đặt — ca phổ biến nhất —
    slot đi qua `slot_salvage`, không qua `_slots_from_payload`. Đường đó dùng
    `parse_budget_vnd` (chỉ lấy trần) nên vẫn ghi 600 triệu. Đó là lý do bản vá
    đầu tiên không ăn trên prod (2026-08-25).
    """

    from src.agents.domain.slot_salvage import salvaged_budget_floor, salvaged_budget_stated

    assert salvaged_budget_stated("khoảng 500 triệu") == 500_000_000
    assert salvaged_budget_floor("khoảng 500 triệu") == 400_000_000
    # Khoảng khách tự nêu: hai biên đã là lời khách, không có con số thứ ba.
    assert salvaged_budget_stated("từ 400 đến 600 triệu") is None


def test_the_stated_figure_survives_the_vehicle_type_filter() -> None:
    """`_drop_unsupported_slots` xoá mọi slot không `is_applicable` — TRONG IM LẶNG.

    Bẫy này đã bắt Em một lần (2026-08-25): hai đường trích đều ghi đúng
    `budget_stated_vnd`, hàm parse trả đúng 500 triệu, mà bảng
    `conversation_slots` không bao giờ có hàng nào. Slot bị lọc ngay sau khi
    trích, không log, không lỗi.
    """

    from src.agents.domain.slot_tree import is_applicable
    from src.agents.domain.values import SlotName, VehicleType

    for vehicle_type in (None, VehicleType.CAR, VehicleType.ELECTRIC_MOTORBIKE):
        assert is_applicable(vehicle_type, SlotName.BUDGET_STATED_VND), vehicle_type


def test_a_refusal_is_recognised_however_the_customer_phrases_it() -> None:
    """Sếp 2026-08-25 nêu đúng hai cách nói mà bản cũ bỏ sót: "không nhé" và
    "không cần tính năng gì".

    Chiều ngược lại quan trọng hơn: bản nháp đầu để `k` làm viết tắt của "không"
    kèm một đuôi chữ tự do, nên MỌI câu bắt đầu bằng "k" thành lời từ chối —
    "khoá chống trộm", đúng một tính năng khách hay chọn, bị nuốt mất.
    """

    from src.agents.domain.slot_salvage import is_non_answer

    for refusal in ("không", "không nhé", "không cần tính năng gì", "thôi khỏi", "không cần gì thêm"):
        assert is_non_answer(refusal), refusal

    for real_answer in ("khoá chống trộm", "kích thước nhỏ gọn", "cảnh báo điểm mù", "khoang hành lý rộng"):
        assert not is_non_answer(real_answer), real_answer


# ── Câu này có NÓI VỀ TIỀN không (Sếp 2026-08-26) ────────────────────────────
#
# Bug thật, đọc từ `turn_traces` prod:
#
#     "1 tỷ, 5 người, đi làm, mỗi ngày 30km" -> budget_max_vnd = 1.000.000.000
#     "tôi chọn VF 8 All New"                -> budget_max_vnd = 1.100.000.000
#                                               budget_min_vnd =   900.000.000
#
# Lượt thứ hai không có một chữ nào về tiền. LLM nhắc lại ngân sách từ ngữ cảnh
# và tự thêm chữ "khoảng", nên bộ đọc nới biên ±100 triệu và ghi đè trần cũ.


@pytest.mark.parametrize(
    "message",
    ["1 tỷ", "khoảng 900 triệu", "tầm 500tr", "ngân sách 2 tỉ", "tầm 1ty2", "800 củ", "1000000000", "giá hơi cao"],
)
def test_cau_noi_ve_tien_thi_nhan_ra(message: str) -> None:
    assert mentions_money(message) is True


@pytest.mark.parametrize(
    "message",
    ["tôi chọn VF 8 All New", "VF 8", "xe 5 chỗ", "có tất cả", "3 trong số đó", "cho 7 người"],
)
def test_con_so_trong_ten_xe_khong_phai_tien(message: str) -> None:
    """`parse_budget_range` cố ý đọc LỎNG — nó chạy trên chuỗi ngân sách mà LLM
    đã tách sẵn ("500", "từ 300 đến 700"), nên số trần không đơn vị vẫn là tiền.

    Chạy nó trên nguyên câu thì "VF 8" ra 8.000.000đ và "xe 5 chỗ" ra 5.000.000đ
    — tức chính câu chọn xe tự cấp cho mình bằng chứng về tiền. Vị từ này là bản
    đọc CHẶT cho câu hỏi khác hẳn: khách có đang nói về tiền không.
    """

    assert mentions_money(message) is False


def test_don_vi_dinh_lien_so_van_doc_duoc() -> None:
    """"tầm 1ty2" — `\\b` giữa "y" và "2" không tồn tại, nên ranh giới phải là
    "không phải chữ cái" chứ không phải ranh giới từ.

    Vẫn phải chặn CHỮ CÁI theo sau, nếu không "tr" nuốt luôn "trong".
    """

    assert mentions_money("Ô tô cho 7 người, tầm 1ty2, chủ yếu đi du lịch") is True
    assert mentions_money("3 trong số đó") is False


@pytest.mark.parametrize(
    "message",
    ["không quan tâm giá", "không cần quan tâm giá cả", "không để ý tiền", "không đặt nặng ngân sách"],
)
def test_phu_dinh_dung_truoc_danh_tu_tien_cung_la_khong_dat_tran(message: str) -> None:
    """Hai chiều của cùng một ý, và bản trước chỉ bắt được một.

    Nhánh cũ đòi danh từ tiền đứng TRƯỚC ("tài chính không thành vấn đề"), nên
    "KHÔNG quan tâm GIÁ" — cách nói phổ biến hơn hẳn — rơi ra ngoài. Lượt đó
    không trích được slot nào, và agent hỏi lại đúng câu ngân sách mà khách vừa
    bảo đừng hỏi.
    """

    assert NO_BUDGET_LIMIT_PATTERN.search(message) is not None


@pytest.mark.parametrize("message", ["tôi quan tâm giá", "khoảng 500 triệu", "giá bao nhiêu"])
def test_cau_van_noi_ve_gia_thi_khong_phai_bo_tran(message: str) -> None:
    assert NO_BUDGET_LIMIT_PATTERN.search(message) is None
