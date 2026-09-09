"""[A4-7] Nhận diện LOẠI xe và dựng danh sách danh mục — domain thuần.

Bug gốc được đo ở đây trước khi đo qua graph: "xe máy điện" là tên MỘT LOẠI, và
mọi thứ hỏng phía sau đều bắt nguồn từ việc hệ thống đọc nó như tên MỘT MẪU.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from src.agents.domain.catalog_browse import (
    BrowseEntry,
    render_browse_answer,
    requested_vehicle_types,
)
from src.agents.domain.values import VehicleType

MOTORBIKE = VehicleType.ELECTRIC_MOTORBIKE
CAR = VehicleType.CAR


# ── Nhận diện loại xe ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("các xe máy điện có trong cửa hàng", (MOTORBIKE,)),
        ("xe máy điện nào đang bán", (MOTORBIKE,)),
        ("danh sách xe máy điện", (MOTORBIKE,)),
        ("các ô tô điện có trong cửa hàng", (CAR,)),
        ("có những mẫu ô tô nào", (CAR,)),
        ("shop mình có xe hơi không", (CAR,)),
    ],
)
def test_one_named_type_is_read_as_that_type(message: str, expected: tuple[VehicleType, ...]) -> None:
    assert requested_vehicle_types(message) == expected


def test_two_types_in_one_sentence_stay_in_one_turn() -> None:
    """Câu hỏi gộp không được tách thành hai lượt hỏi riêng.

    Khách nêu cả hai loại trong một câu thì họ muốn thấy cả hai, không phải muốn
    được hỏi lại "anh/chị quan tâm loại nào trước ạ".
    """

    types = requested_vehicle_types("gợi ý cho tôi các xe máy điện và ô tô điện có trong cửa hàng")

    assert types == (MOTORBIKE, CAR)


@pytest.mark.parametrize(
    "message",
    ["có xe nào không", "cửa hàng có những xe gì", "show tất cả xe", "xe điện nào đang bán"],
)
def test_no_named_type_shows_the_whole_catalog(message: str) -> None:
    """Không nêu loại → cả hai loại, không đoán bừa một loại rồi giấu nửa còn lại."""

    assert set(requested_vehicle_types(message)) == {MOTORBIKE, CAR}


def test_unaccented_typing_does_not_invent_a_car_question() -> None:
    """ "cho toi" chứa chuỗi con "o to" — khớp chuỗi con sẽ bịa ra một câu hỏi ô tô.

    Đây là lý do việc nhận diện dùng ranh giới TỪ chứ không phải `in`.
    """

    assert requested_vehicle_types("goi y cho toi cac xe may dien") == (MOTORBIKE,)


def _variant(
    model_name: str,
    variant_name: str | None = None,
    *,
    price: int | None = None,
    vehicle_type: VehicleType = MOTORBIKE,
    body_type: str | None = None,
    seat_count: int | None = None,
    range_km: int | None = None,
    max_speed_kmh: int | None = None,
    license_requirement: str | None = None,
    slug: str = "",
) -> BrowseEntry:
    """Một BIẾN THỂ như adapter dựng: có tên dòng riêng, tên biến thể riêng."""

    display_name = " ".join(part for part in ("VinFast", model_name, variant_name) if part)
    return BrowseEntry(
        # `vehicle_id` ổn định theo tên: hai lần dựng cùng một biến thể cho cùng
        # một id, nên test so sánh entry không phụ thuộc thứ tự sinh UUID.
        vehicle_id=uuid5(NAMESPACE_URL, display_name),
        display_name=display_name,
        vehicle_type=vehicle_type,
        starting_price_vnd=None if price is None else Decimal(price),
        model_name=model_name,
        variant_name=variant_name,
        body_type=body_type,
        seat_count=seat_count,
        range_km=None if range_km is None else Decimal(range_km),
        max_speed_kmh=None if max_speed_kmh is None else Decimal(max_speed_kmh),
        license_requirement=license_requirement,
        slug=slug,
    )


def _model_lines(answer: str) -> list[str]:
    """Nội dung bullet dòng xe, đã bóc ký tự bullet và dấu in đậm Markdown.

    Các test dưới đây nói về NỘI DUNG dòng xe; bố cục Markdown được khoá riêng ở
    `test_a_model_line_bolds_the_model_name` và `test_reply_format`.

    Liên kết "Xem thêm" cũng bị bóc: nó được khoá riêng ở
    `test_a_model_line_links_to_the_vehicle_page_on_this_site`, còn ở đây nó chỉ
    làm nhiễu những phép so khớp về thứ tự và mô tả.
    """

    stripped = (re.sub(r"\s*\[Xem thêm\]\([^)]*\)", "", line) for line in answer.splitlines())
    return [line[2:].replace("**", "") for line in stripped if line.startswith("* ")]


# ── Dựng câu trả lời ──────────────────────────────────────────────────────────


def test_an_empty_catalog_renders_nothing() -> None:
    """Danh mục rỗng là sự cố dữ liệu, không phải một câu để nói với khách."""

    assert render_browse_answer({MOTORBIKE: []}) is None


def test_variants_of_one_model_collapse_into_a_single_line() -> None:
    """Đây là lý do format này tồn tại.

    `VF 6 Eco` và `VF 6 Plus` là hai bản ghi giá, nhưng là MỘT dòng xe. Liệt kê
    thành hai dòng khiến khách đếm ra nhiều lựa chọn hơn số dòng xe thật sự có.
    """

    answer = render_browse_answer(
        {
            CAR: [
                _variant(
                    "VF 6", "Eco", price=689_000_000, vehicle_type=CAR, body_type="SUV", seat_count=5, range_km=315
                ),
                _variant(
                    "VF 6", "Plus", price=749_000_000, vehicle_type=CAR, body_type="SUV", seat_count=5, range_km=310
                ),
            ]
        }
    )
    assert answer is not None

    lines = _model_lines(answer)
    assert len(lines) == 1
    assert lines[0].startswith("VF 6:")
    assert "có 2 phiên bản (Eco, Plus)" in lines[0]
    assert "1 dòng ô tô điện" in answer


def test_a_model_line_describes_it_from_real_catalog_columns() -> None:
    """Kiểu thân xe, số chỗ, tầm chạy — cả ba đều là cột có thật trong `cars`."""

    answer = render_browse_answer(
        {
            CAR: [
                _variant(
                    "VF 9",
                    "All New",
                    price=1_348_000_000,
                    vehicle_type=CAR,
                    body_type="SUV",
                    seat_count=7,
                    range_km=626,
                )
            ]
        }
    )
    assert answer is not None

    assert "**VF 9**: SUV 7 chỗ, tầm chạy 626 km mỗi lần sạc." in answer


def test_the_listing_carries_no_prices() -> None:
    """Lượt này khách vừa chọn LOẠI xe, chưa nói ngân sách.

    Trả về bảng giá là bắt khách tự lọc theo con số duy nhất họ chưa được hỏi,
    trong khi việc còn lại của lượt là đi hỏi đúng con số đó.
    """

    answer = render_browse_answer(
        {
            CAR: [
                _variant(
                    "VF 2",
                    "All New",
                    price=188_000_000,
                    vehicle_type=CAR,
                    body_type="Hatchback",
                    seat_count=4,
                    range_km=210,
                )
            ]
        }
    )
    assert answer is not None

    assert "188" not in answer
    assert "đồng" not in answer
    assert "Khoảng giá" not in answer


def test_a_model_description_never_invents_a_market_segment() -> None:
    """`vehicles` không có cột `segment`/`price_tier` nào.

    Nên "phân khúc B", "phổ thông", "cao cấp", "phù hợp cho gia đình nhỏ" đều là
    phán đoán marketing catalog không chứng minh được — và một câu giới thiệu bịa
    ra thì tệ hơn một dòng chỉ có tên xe.
    """

    answer = render_browse_answer(
        {
            CAR: [
                _variant(
                    "VF 7", "All New", price=799_000_000, vehicle_type=CAR, body_type="SUV", seat_count=5, range_km=440
                )
            ]
        }
    )
    assert answer is not None

    for invented in ("phân khúc", "phổ thông", "tầm trung", "cao cấp", "gia đình nhỏ"):
        assert invented not in answer.casefold()


def test_models_are_listed_cheapest_first() -> None:
    """Giá không hiện ra, nhưng vẫn là thứ tự đọc tự nhiên của một danh mục."""

    answer = render_browse_answer(
        {
            CAR: [
                _variant("VF 9", "All New", price=1_348_000_000, vehicle_type=CAR),
                _variant("VF 2", "All New", price=188_000_000, vehicle_type=CAR),
                _variant("VF 5", "All New", price=436_000_000, vehicle_type=CAR),
            ]
        }
    )
    assert answer is not None

    assert _model_lines(answer) == ["VF 2", "VF 5", "VF 9"]


def test_a_model_without_a_price_is_listed_last_not_hidden() -> None:
    """Xe chưa công bố giá vẫn đang bán — giấu đi là trả lời thiếu.

    Và nó không được coi như xe rẻ nhất: giá thiếu không phải giá bằng 0.
    """

    answer = render_browse_answer(
        {
            CAR: [
                _variant("VF Wild", "All New", price=None, vehicle_type=CAR),
                _variant("VF 9", "All New", price=1_348_000_000, vehicle_type=CAR),
            ]
        }
    )
    assert answer is not None

    assert _model_lines(answer) == ["VF 9", "VF Wild"]


def test_a_model_with_no_specs_at_all_still_gets_a_line() -> None:
    """Thiếu bản ghi spec thì dòng rút lại còn tên xe, không phải một câu tả rỗng."""

    answer = render_browse_answer({CAR: [_variant("VF Wild", "All New", price=None, vehicle_type=CAR)]})
    assert answer is not None

    assert _model_lines(answer) == ["VF Wild"]


def test_a_range_that_differs_between_variants_is_shown_as_a_span() -> None:
    """Khách đọc "tầm chạy 562 km" rồi mua đúng bản chạy 457 km là câu sai có hậu quả."""

    answer = render_browse_answer(
        {
            CAR: [
                _variant(
                    "VF 8",
                    "Eco Extended Range",
                    price=1_019_000_000,
                    vehicle_type=CAR,
                    body_type="SUV",
                    seat_count=5,
                    range_km=562,
                ),
                _variant(
                    "VF 8",
                    "Plus Extended Range",
                    price=1_079_000_000,
                    vehicle_type=CAR,
                    body_type="SUV",
                    seat_count=5,
                    range_km=457,
                ),
            ]
        }
    )
    assert answer is not None

    assert "tầm chạy 457–562 km mỗi lần sạc" in answer


def test_a_motorbike_line_leads_with_range_speed_and_licence() -> None:
    """Hạng giấy phép là vế phân biệt mạnh nhất với người mua ở Việt Nam."""

    answer = render_browse_answer(
        {
            MOTORBIKE: [
                _variant(
                    "Kinet", "Standard", price=25_000_000, range_km=145, max_speed_kmh=90, license_requirement="A1"
                ),
                _variant(
                    "Motio", "Standard", price=18_000_000, range_km=82, max_speed_kmh=49, license_requirement="NONE"
                ),
            ]
        }
    )
    assert answer is not None

    assert "**Motio**: Tầm chạy tới 82 km, tốc độ tối đa 49 km/h, không cần giấy phép lái xe." in answer
    assert "**Kinet**: Tầm chạy tới 145 km, tốc độ tối đa 90 km/h, cần giấy phép lái xe hạng A1." in answer


def test_a_licence_class_that_differs_between_variants_is_left_unsaid() -> None:
    """Nói sai hạng giấy phép khiến khách mua một chiếc xe họ không được phép đi."""

    answer = render_browse_answer(
        {
            MOTORBIKE: [
                _variant("Klara", "S", price=40_000_000, range_km=194, max_speed_kmh=78, license_requirement="A1"),
                _variant("Klara", "Neo", price=30_000_000, range_km=112, max_speed_kmh=60, license_requirement="NONE"),
            ]
        }
    )
    assert answer is not None

    assert "giấy phép" not in answer
    assert "**Klara**: Tầm chạy tới 112–194 km" in answer


def test_a_model_line_bolds_the_model_name() -> None:
    """Tên dòng xe là "tên trường" của bullet — khách quét mắt tìm đúng nó."""

    answer = render_browse_answer(
        {CAR: [_variant("VF 9", "Plus", price=1_491_000_000, vehicle_type=CAR, seat_count=7)]}
    )
    assert answer is not None

    bullets = [line for line in answer.splitlines() if line.startswith("* ")]
    assert bullets and bullets[0].startswith("* **VF 9**: ")


def test_two_types_render_as_two_separate_blocks() -> None:
    """Hai loại → hai khối riêng, không trộn thành một danh sách phẳng."""

    answer = render_browse_answer(
        {
            MOTORBIKE: [_variant("Theon", "S", price=63_000_000)],
            CAR: [_variant("VF 2", "All New", price=188_000_000, vehicle_type=CAR)],
        }
    )
    assert answer is not None

    assert "1. **Xe máy điện — 1 dòng đang bán**:" in answer
    assert "2. **Ô tô điện — 1 dòng đang bán**:" in answer
    assert answer.index("Theon") < answer.index("VF 2")


def test_the_answer_always_ends_by_asking_for_budget_and_needs() -> None:
    """Câu bắt buộc: đây là chỗ chuyển từ "xem hàng" sang thu thập slot tư vấn."""

    answer = render_browse_answer({CAR: [_variant("VF 2", "All New", price=188_000_000, vehicle_type=CAR)]})
    assert answer is not None

    assert "ngân sách" in answer.lower()
    assert "nhu cầu" in answer.lower()


def test_the_answer_omits_disclaimer_and_styles_example_hint() -> None:
    """Danh mục kết bằng câu hỏi; ví dụ là phần phụ, không chen disclaimer dài."""

    answer = render_browse_answer({CAR: [_variant("VF 2", "All New", price=188_000_000, vehicle_type=CAR)]})
    assert answer is not None

    assert "bộ phận chuyên trách của VinFast" not in answer
    assert "*(ví dụ:" in answer
    assert answer.rstrip().endswith(")*")


def test_the_opening_says_the_lineup_is_broad_and_counts_the_models() -> None:
    """Đếm DÒNG xe, không đếm bản ghi giá — xem `test_variants_of_one_model_...`."""

    answer = render_browse_answer(
        {
            CAR: [
                _variant("VF 6", "Eco", price=689_000_000, vehicle_type=CAR),
                _variant("VF 6", "Plus", price=749_000_000, vehicle_type=CAR),
                _variant("VF 9", "All New", price=1_348_000_000, vehicle_type=CAR),
            ]
        }
    )
    assert answer is not None

    assert "dải sản phẩm ô tô điện đa dạng" in answer
    assert "2 dòng ô tô điện đang bán" in answer


# ── Liên kết "Xem thêm" ──────────────────────────────────────────────────────


def test_a_model_line_links_to_the_vehicle_page_on_this_site() -> None:
    """Sếp 2026-08-25: mỗi xe một câu ngắn, cạnh đó có nút xem thêm trỏ tới trang
    của xe. Trỏ vào `/vehicles/<slug>` của chính web này chứ không ra trang ngoài
    — khách bấm xong vẫn quay lại được cuộc tư vấn đang dở, và khung xem trước
    khi rê chuột chỉ nhúng được trang cùng nguồn."""

    answer = render_browse_answer(
        {
            VehicleType.CAR: [
                _variant("VF 8", "Eco", price=1000, body_type="SUV", seat_count=5, vehicle_type=VehicleType.CAR),
                _variant("VF 8", "Plus", price=2000, body_type="SUV", seat_count=5, vehicle_type=VehicleType.CAR),
            ]
        }
    )

    assert answer is not None
    # Đường dẫn lấy theo TÊN DÒNG, không theo `vehicles.slug` của catalog: route
    # `/vehicles/[slug]` đọc `mocks/vehicle-menu`, không đọc catalog. Dùng slug
    # catalog thì MỌI liên kết đều là 404.
    assert "[Xem thêm](/vehicles/vf-8)" in answer
    assert "vinfast-vf-8" not in answer


def test_a_model_without_a_page_has_no_link_instead_of_a_dead_one() -> None:
    """VF Wild có trong catalog nhưng KHÔNG có trang. Không có liên kết còn hơn
    một liên kết dẫn tới trang trống."""

    answer = render_browse_answer(
        {
            VehicleType.CAR: [
                _variant(
                    "VF Wild", "All New", price=1000, body_type="Pickup", seat_count=5, vehicle_type=VehicleType.CAR
                )
            ]
        }
    )

    assert answer is not None
    assert "Xem thêm" not in answer
    assert "VF Wild" in answer


def test_every_linked_model_has_a_real_page() -> None:
    """Bảng tra đường dẫn phải khớp danh sách trang THẬT của frontend.

    Bản đầu sinh đường dẫn từ `vehicles.slug` và mọi liên kết đều 404 — lỗi chỉ
    lộ khi Em thử mở trang sau lúc deploy. Test này bắt nó ngay ở đây.
    """

    import re

    from src.agents.domain.catalog_browse import _MODEL_PAGE_SLUG

    menu = Path("frontend/src/mocks/vehicle-menu.ts").read_text(encoding="utf-8")
    real_pages = set(re.findall(r'id: "([a-z0-9-]+)"', menu))

    missing = sorted(slug for slug in _MODEL_PAGE_SLUG.values() if slug not in real_pages)
    assert not missing, f"tro toi trang khong ton tai: {missing}"


# ── Gợi ý mục đích theo loại xe ──────────────────────────────────────────────


def test_the_car_listing_never_suggests_a_purpose_that_does_nothing_for_cars() -> None:
    """ "Giao hàng" ở nhánh ô tô đòi `battery_removable`/`battery_swappable` — hai
    cột CHỈ bảng `motorbikes` mới có. Gợi ý nó cho khách mua ô tô là mời họ chọn
    một đáp án không đổi được gì (Sếp 2026-08-25)."""

    answer = render_browse_answer(
        {VehicleType.CAR: [_variant("VF 8", "Eco", price=1000, vehicle_type=VehicleType.CAR)]}
    )

    assert answer is not None
    assert "chở gia đình" in answer
    assert "giao hàng" not in answer.casefold()


def test_the_motorbike_listing_never_suggests_a_family_purpose() -> None:
    """Chiều ngược lại: "chở gia đình" đòi cột cốp, xe máy không có."""

    answer = render_browse_answer({MOTORBIKE: [_variant("Evo Grand", price=1000)]})

    assert answer is not None
    assert "giao hàng" in answer.casefold()
    assert "chở gia đình" not in answer


def test_a_two_type_listing_keeps_the_shared_hint() -> None:
    """Hỏi cả hai loại thì gợi ý là hợp của hai nhánh — không nhánh nào bị bỏ."""

    answer = render_browse_answer(
        {
            MOTORBIKE: [_variant("Evo Grand", price=1000)],
            VehicleType.CAR: [_variant("VF 8", "Eco", price=2000, vehicle_type=VehicleType.CAR)],
        }
    )

    assert answer is not None
    assert "chở gia đình" in answer
    assert "giao hàng" in answer.casefold()
