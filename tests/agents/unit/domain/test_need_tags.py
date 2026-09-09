"""`canonical_need_tag` phải quy lời khách viết TỰ DO về đúng nhãn tập đóng.

Prompt trích slot dặn LLM ghi `habit_need_tags` "giữ nguyên lời khách", nên mọi
giá trị tới `scoring._need_tag_reasons` đều là tiếng Việt tự do. Nhãn nào không
có mẫu tiếng Việt ở đây thì thói quen đó **không góp một điểm nào** — im lặng,
không log, không lỗi. Đúng cái bẫy `luong-tu-van-da-sua.md` mục 3.4 đã dính một
lần với `purpose`.
"""

from __future__ import annotations

import pytest

from src.agents.domain.need_tags import NeedTag, canonical_need_tag


@pytest.mark.parametrize(
    ("customer_words", "expected"),
    [
        ("hay chở hàng nặng", "DELIVERY_LOAD"),
        ("chạy giao hàng mỗi ngày", "DELIVERY_LOAD"),
        ("cần chở đồ cồng kềnh", "DELIVERY_LOAD"),
        ("muốn tiết kiệm chi phí", "ECO_SAVING"),
        ("tiết kiệm điện", "ECO_SAVING"),
        ("chi phí vận hành rẻ", "ECO_SAVING"),
        ("thích xe sang trọng", "PREMIUM_COMFORT"),
        ("muốn nội thất cao cấp", "PREMIUM_COMFORT"),
        ("thích cửa sổ trời", "PREMIUM_COMFORT"),
    ],
)
def test_free_text_habits_reach_the_three_previously_unreachable_tags(customer_words: str, expected: str) -> None:
    assert canonical_need_tag(customer_words) == expected


@pytest.mark.parametrize(
    ("customer_words", "expected"),
    [
        ("hay đi trong phố", "URBAN_TRAFFIC"),
        ("chở gia đình đi chơi", "FAMILY_TRIP"),
        ("hay về quê", "LONG_DISTANCE"),
    ],
)
def test_ba_nhan_cu_khong_bi_ba_nhan_moi_cuop_mat(customer_words: str, expected: str) -> None:
    """Mẫu mới thêm không được khớp trước và nuốt mất ba nhãn vốn đã chạy."""

    assert canonical_need_tag(customer_words) == expected


@pytest.mark.parametrize(
    "stored_value",
    [tag.value for tag in NeedTag],
)
def test_moi_nhan_luu_trong_db_van_quy_ve_chinh_no(stored_value: str) -> None:
    """`need_tag_links.need_tag` lưu tên enum. Hai vế của phép so sánh ở
    `scoring._need_tag_reasons` đều đi qua hàm này, nên tên enum phải bền."""

    canonical = canonical_need_tag(stored_value)
    assert canonical == canonical_need_tag(canonical)
    assert canonical != ""


# ── Nhãn tập đóng do LLM trả về ───────────────────────────────────────────────
#
# `slot_extraction_prompts` nay bắt LLM chọn `habit_need_tags` trong tập đóng
# `NeedTag`. Nhưng chữ tự do KHÔNG biến mất: `conversation_slots` trên prod đang
# chứa đầy chữ tự do của các phiên cũ, và `_explicit_habit_need_tags` vẫn thêm
# "đi nội thành"/"về quê" bằng regex tất định. Cả hai dạng phải cùng chạy.

from src.agents.domain.need_tags import NEED_TAG_REGISTRY, need_tag_display  # noqa: E402


@pytest.mark.parametrize("tag", list(NeedTag))
def test_nhan_tap_dong_duoc_doi_sang_ten_tieng_viet(tag: NeedTag) -> None:
    """Giá trị slot còn đi thẳng vào prompt tổng hợp (`nodes/synthesize.
    _customer_wording`). Để nguyên `URBAN_TRAFFIC` ở đó là mời LLM chép mã thô
    vào câu trả lời, rồi `RAW_STRUCTURED_PATTERN` loại cả pitch — đúng bẫy 3.9.
    """

    assert need_tag_display(tag.value) == NEED_TAG_REGISTRY[tag].name_vi


@pytest.mark.parametrize("tag", list(NeedTag))
def test_ten_tieng_viet_quy_nguoc_ve_dung_nhan_cu(tag: NeedTag) -> None:
    """Hai vế của phép so ở `scoring._need_tag_reasons` đều đi qua
    `canonical_need_tag`, nên tên tiếng Việt phải quy về đúng nhãn ban đầu."""

    name_vi = NEED_TAG_REGISTRY[tag].name_vi

    assert canonical_need_tag(name_vi) == canonical_need_tag(tag.value)


@pytest.mark.parametrize(
    "customer_words",
    ["nhỏ gọn", "hay chở con nhỏ", "thích màu đỏ"],
)
def test_chu_tu_do_khong_quy_duoc_thi_giu_nguyen_loi_khach(customer_words: str) -> None:
    """Dữ liệu cũ và regex tất định vẫn ghi chữ tự do vào slot này. Bịa một nhãn
    cho chúng còn tệ hơn giữ nguyên: câu tổng hợp sẽ nói sai ý khách."""

    assert need_tag_display(customer_words) == customer_words


@pytest.mark.parametrize(
    "customer_words",
    ["khoá chống trộm", "khoảng 500 triệu", "chở được năm người"],
)
def test_ba_cau_am_tinh_khong_duoc_dinh_vao_nhan_nao(customer_words: str) -> None:
    """Bẫy 3.5: mọi mẫu mới phải kiểm theo chiều ÂM. Ba câu này không nói gì về
    thói quen sử dụng — dính nhầm là cộng điểm cho một nhu cầu khách chưa nêu."""

    assert need_tag_display(customer_words) == customer_words
    assert canonical_need_tag(customer_words) not in {canonical_need_tag(tag.value) for tag in NeedTag}


@pytest.mark.parametrize("tag", list(NeedTag))
def test_ten_tieng_viet_khong_lam_vo_pitch(tag: NeedTag) -> None:
    """`name_vi` nay là GIÁ TRỊ SLOT, mà slot này đi thẳng vào prompt tổng hợp.
    Nên nó chịu đúng ba ràng buộc cứng của `FEATURE_DISPLAY_LABELS`: chữ số làm
    `_reject_digits_outside_placeholders` raise trước cả lần gọi LLM, gạch dưới
    dính `RAW_STRUCTURED_PATTERN`, và "phù hợp"/"hỗ trợ"/"đáp ứng" dính
    `UNSTRUCTURED_CLAIM_PATTERN` — mỗi cái đều loại cả pitch, không chỉ xấu chữ.
    """

    from src.agents.domain.claim_policy import UNSTRUCTURED_CLAIM_PATTERN
    from src.agents.services.synthesis import DIGIT_PATTERN, RAW_STRUCTURED_PATTERN

    name_vi = NEED_TAG_REGISTRY[tag].name_vi

    assert not DIGIT_PATTERN.search(name_vi)
    assert not RAW_STRUCTURED_PATTERN.search(name_vi)
    assert not UNSTRUCTURED_CLAIM_PATTERN.search(name_vi)


# ── Từ CẢM QUAN khách dùng để mô tả nhu cầu (Sếp 2026-08-26) ─────────────────
#
# Câu mở lời THẬT, đọc từ `pending_feature_mentions` prod:
#
#   "Tôi cần một chiếc SUV cho gia đình… Yêu cầu xe rộng rãi, thoải mái,
#    tone màu trắng, bền bỉ"
#
# Bốn cụm lưu nguyên văn rồi không quy được về đâu: bảng cụm chữ có 27 mã tính
# năng, không mã nào tả "rộng rãi"; còn ở đây thì rơi xuống nhánh cuối thành
# chuỗi rác `R_NG_R_I` — không khớp tag nào trong 8 tag thật, cộng 0 điểm, im
# lặng. Từ khi bỏ bước chủ động hỏi tính năng, câu mở lời là đường CHÍNH để
# khách nói ra nhu cầu, nên mất ở đây là mất phần lớn tín hiệu.


@pytest.mark.parametrize(
    ("wording", "expected"),
    [
        ("rộng rãi", "FAMILY_TRIP"),
        ("xe rộng rãi cho cả nhà", "FAMILY_TRIP"),
        ("thoải mái", "PREMIUM_COMFORT"),
        ("êm ái", "PREMIUM_COMFORT"),
        ("ngồi thoải mái", "PREMIUM_COMFORT"),
    ],
)
def test_tu_cam_quan_quy_ve_nhan_co_that(wording: str, expected: str) -> None:
    assert canonical_need_tag(wording) == expected


@pytest.mark.parametrize(
    ("wording", "expected"),
    [
        ("chở hàng nặng", "DELIVERY_LOAD"),
        ("tiết kiệm", "ECO_SAVING"),
        ("sang trọng", "PREMIUM_COMFORT"),
        ("đi trong nội thành", "URBAN_TRAFFIC"),
        ("chở gia đình", "FAMILY_TRIP"),
        ("hay về quê", "LONG_DISTANCE"),
    ],
)
def test_cac_nhanh_cu_khong_bi_cuop_cau(wording: str, expected: str) -> None:
    """Mẫu mới thêm vào cuối, không được lấy mất câu nào của nhánh đã chạy thật."""

    assert canonical_need_tag(wording) == expected
