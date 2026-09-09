"""Pitch KHÔNG được khẳng định một tính năng mà xe không có căn cứ.

**Bug thật Sếp báo 2026-08-26.** Khách nói *"anh chỉ cần 1 chiếc nhỏ gọn thôi tại
đi trong nội thành"*; hệ đề xuất **VF 8** (SUV cỡ D, dài 4750 mm) và pitch viết:

    "VinFast VF 8 All New ... với thiết kế nhỏ gọn, rất tiện lợi cho việc di
     chuyển trong nội thành."

Catalog ĐÚNG: cờ `COMPACT_SIZE` chỉ gắn cho VF 2 và VF 3, không gắn VF 8. Mô hình
**nhại lại chính lời khách** thành một lời khẳng định về sản phẩm.

`reject_unstructured_claims` không bắt được vì nó chặn cụm TIẾP THỊ mơ hồ ("phù
hợp", "lý tưởng", "đáp ứng"). `"nhỏ gọn"` nghe như một SỰ THẬT, nên lọt.

**Bất biến dùng để chặn** — đã có sẵn trong `services/synthesis`: mọi thứ CÓ căn
cứ đều nằm trong placeholder, và phần văn xuôi được bóc placeholder ra trước khi
kiểm. Vậy một tên tính năng còn sót trong văn xuôi là tính năng **không có căn
cứ**. Cùng tinh thần với luật "chữ số phải nằm trong placeholder".
"""

from __future__ import annotations

import pytest

from src.agents.domain.claim_policy import (
    feature_codes_backed_by_facts,
    reject_unbacked_feature_claims,
    reject_unstructured_claims,
)


def test_a_size_claim_the_vehicle_has_no_flag_for_is_rejected() -> None:
    """Đúng câu đã ra prod."""

    with pytest.raises(ValueError):
        reject_unbacked_feature_claims(
            "thuộc đúng dòng xe Quý khách đang tìm, với thiết kế nhỏ gọn, rất tiện lợi "
            "cho việc di chuyển trong nội thành.",
            approved_feature_codes=frozenset({"ADAS_SUITE"}),
        )


def test_the_same_claim_passes_when_the_vehicle_really_has_the_flag() -> None:
    """VF 3 có cờ `COMPACT_SIZE` thật — câu y hệt phải được nói."""

    reject_unbacked_feature_claims(
        "với thiết kế nhỏ gọn, rất tiện lợi cho việc di chuyển trong nội thành.",
        approved_feature_codes=frozenset({"COMPACT_SIZE"}),
    )


@pytest.mark.parametrize(
    ("prose", "code"),
    [
        ("xe được trang bị cảnh báo điểm mù", "BLIND_SPOT_MONITOR"),
        ("có cửa sổ trời rộng rãi", "PANORAMIC_ROOF"),
        ("ghế bọc da sang trọng", "LEATHER_SEATS"),
        ("hỗ trợ sạc nhanh tại trạm", "FAST_CHARGING"),
    ],
)
def test_other_unbacked_feature_claims_are_rejected_too(prose: str, code: str) -> None:
    with pytest.raises(ValueError):
        reject_unbacked_feature_claims(prose, approved_feature_codes=frozenset())
    # Cùng câu đó, khi xe CÓ cờ, phải đi qua.
    reject_unbacked_feature_claims(prose, approved_feature_codes=frozenset({code}))


@pytest.mark.parametrize(
    "prose",
    [
        # Văn xuôi bình thường của pitch — không câu nào được dính.
        "thuộc đúng dòng xe Quý khách đang tìm, với đủ chỗ cho số người Quý khách thường chở.",
        "có giá nằm trong ngân sách Quý khách dự tính.",
        "Quý khách có thể tham khảo thêm tại showroom gần nhất.",
        "xe có khả năng di chuyển xa mỗi lần sạc, thuận tiện cho những chuyến đi dài.",
        # "sạc" trần KHÁC "sạc nhanh" — một chữ khác nhau, đừng chặn nhầm.
        "thời gian sạc tại nhà rất thuận tiện.",
        # "da" trong "da dạng" không phải "ghế bọc da".
        "VinFast có dải sản phẩm đa dạng.",
    ],
)
def test_ordinary_pitch_prose_is_never_rejected(prose: str) -> None:
    reject_unbacked_feature_claims(prose, approved_feature_codes=frozenset())


def test_the_claim_key_shape_is_locked_because_the_guard_depends_on_it() -> None:
    """Hình dạng khoá claim là HỢP ĐỒNG NGẦM giữa `plan_claims` và chỗ kiểm nháp.

    Bản nối đầu tiên đoán khoá có dạng `slot:feature_code` → suy ra tập mã đã
    duyệt là RỖNG → chặn nhầm MỌI pitch hợp lệ. Test cũ không bắt được vì văn
    xuôi của chúng không chứa tên tính năng nào. Test này khoá lại.
    """

    from src.agents.domain.claim_policy import approved_feature_codes, plan_claims

    claims = plan_claims(["[slot=habit_need_tags;feature_code=COMPACT_SIZE] Tính năng đã kiểm chứng"])
    claim_by_key = {claim.placeholder: claim for claim in claims}

    assert claim_by_key, "plan_claims phải dựng được claim từ lý do có feature_code"
    assert "COMPACT_SIZE" in approved_feature_codes(claim_by_key)


# ── Cùng bảng cụm chữ, dùng cho chiều NGƯỢC LẠI ──────────────────────────────


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("anh chỉ cần 1 chiếc nhỏ gọn thôi tại đi trong nội thành", "COMPACT_SIZE"),
        ("có khoá chống trộm không em", "ANTI_THEFT"),
        ("anh cần xe bảy chỗ", "7_SEATER"),
        ("xe có sạc nhanh chứ", "FAST_CHARGING"),
    ],
)
def test_customer_wording_is_recovered_into_feature_codes(message: str, code: str) -> None:
    """Chiều ngược của cùng một bảng cụm chữ.

    Đo trên prod 2026-08-26: prompt trích slot ĐÃ khai đúng `COMPACT_SIZE = thân
    xe nhỏ gọn` (kiểm bằng `docker exec` đọc thẳng schema), mà mô hình vẫn trả
    `feature_mentions=[]` cho câu "anh chỉ cần 1 chiếc nhỏ gọn". Cùng kiểu với bộ
    phân loại phạm vi ở mục 3.14: prompt đúng, mô hình không theo.

    Bảng cụm chữ đã curate sẵn cho việc chặn claim bịa — dùng luôn cho chiều thu
    nhận. Một bảng, hai chiều: chữ nào đủ đặc trưng để KẾT TỘI một câu bịa thì
    cũng đủ đặc trưng để NHẬN RA một yêu cầu.
    """

    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert code in feature_codes_mentioned(message)


@pytest.mark.parametrize(
    "message",
    [
        "anh muốn tư vấn",
        "khoảng 500 triệu",
        "nhà anh có ổ cắm ở chỗ để xe",
        "thời gian sạc tại nhà thế nào",
        "VinFast có dải sản phẩm đa dạng",
    ],
)
def test_ordinary_customer_sentences_recover_nothing(message: str) -> None:
    """Bẫy 3.5 áp cho cả chiều này: nhận nhầm là gán cho khách một yêu cầu họ
    chưa nêu, rồi cộng điểm cho xe sai."""

    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert feature_codes_mentioned(message) == frozenset()


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("anh chi can 1 chiec nho gon thoi tai di trong noi thanh", "COMPACT_SIZE"),
        ("co khoa chong trom khong em", "ANTI_THEFT"),
        ("xe co sac nhanh chu", "FAST_CHARGING"),
    ],
)
def test_unaccented_typing_is_recovered_too(message: str, code: str) -> None:
    """Gõ KHÔNG DẤU là cách viết rất thường trong chat, không phải lỗi gõ.

    Bảng cụm chữ viết có dấu, mà bản đầu chỉ `casefold()` — nên "nho gon" không
    khớp "nhỏ gọn". Đo trên prod: hàm trả `[]` cho bản không dấu và
    `['COMPACT_SIZE']` cho bản có dấu của **cùng một câu**.
    """

    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert code in feature_codes_mentioned(message)


@pytest.mark.parametrize(
    "message",
    [
        # Bỏ dấu làm nhiều chữ trùng nhau — ca âm tính phải kiểm ở CẢ hai dạng.
        "VinFast co dai san pham da dang",
        "thoi gian sac tai nha the nao",
        "nha anh co o cam o cho de xe",
        "khoang 500 trieu",
    ],
)
def test_unaccented_ordinary_sentences_still_recover_nothing(message: str) -> None:
    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert feature_codes_mentioned(message) == frozenset()


# ── Nhóm A (2026-08-26): bảng cụm chữ quá hẹp ────────────────────────────────


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("có camera 360 không", "CAMERA_360"),
        ("muốn xe 7 chỗ", "7_SEATER"),
        ("ghế da", "LEATHER_SEATS"),
        ("ghế chỉnh điện", "POWER_DRIVER_SEAT"),
        ("cốp điện", "POWER_TAILGATE"),
        ("sạc không dây", "WIRELESS_CHARGING"),
        ("màn hình HUD", "HEAD_UP_DISPLAY"),
        ("điều hòa 2 vùng", "MULTI_ZONE_AC"),
        ("pin đổi được", "BATTERY_SWAPPABLE"),
        ("chế độ eco", "ECO_MODE"),
        ("pin đi được xa", "HIGH_RANGE_BATTERY"),
    ],
)
def test_common_wording_variants_are_recovered(message: str, code: str) -> None:
    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert code in feature_codes_mentioned(message)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("xe có định vị gps không", "GPS"),
        ("có kết nối bluetooth chứ", "BLUETOOTH"),
        ("xe có esim không", "ESIM"),
        ("có ứng dụng điều khiển trên điện thoại không", "MOBILE_APP"),
        ("hỗ trợ carplay không", "SMARTPHONE_MIRRORING"),
        ("sạc có tự ngắt khi đầy không", "AUTO_SHUTOFF_CHARGER"),
    ],
)
def test_six_newly_mapped_codes_are_recovered(message: str, code: str) -> None:
    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert code in feature_codes_mentioned(message)


@pytest.mark.parametrize(
    "message",
    [
        # Bốn câu âm bắt buộc — cả dạng có dấu và không dấu. Bỏ dấu làm "đa"→"da",
        # "chế độ"→"che do", nên từng cụm mới phải đủ dài để không dính nhầm.
        "khoảng 500 triệu",
        "chở được năm người",
        "đa dạng lựa chọn",
        "xe VF 8 Eco Extended Range",
        "khoang 500 trieu",
        "cho duoc nam nguoi",
        "da dang lua chon",
        "xe vf 8 eco extended range",
    ],
)
def test_required_negative_sentences_recover_nothing(message: str) -> None:
    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert feature_codes_mentioned(message) == frozenset()


@pytest.mark.parametrize(
    "vehicle_name",
    [
        # Chiều RA: tên bản xe trong catalog KHÔNG được dính cụm nào. Đặc biệt "eco"
        # trong tên bản xe — cụm ECO_MODE phải là "chế độ eco", không được là "eco".
        "VF 8 Eco Extended Range",
        "Evo Grand Lite",
        "Klara Lithium Standard",
    ],
)
def test_vehicle_names_never_trigger_unbacked_claim(vehicle_name: str) -> None:
    reject_unbacked_feature_claims(vehicle_name, approved_feature_codes=frozenset())


# ── Cụm tải trọng đã CHUYỂN sang cảm quan (2026-08-26) ───────────────────────


@pytest.mark.parametrize("message", ["xe chở được nặng", "chở nặng", "tải trọng lớn"])
def test_cum_tai_trong_khong_con_quy_ve_ma_ma(message: str) -> None:
    """`HIGH_PAYLOAD` là một trong ba mã 0 cờ YES. Quy ba cụm này về nó thì hại
    cả hai chiều: khách gõ xong không xe nào mang mã đó (im lặng, 0 điểm), còn
    pitch nói "chở nặng" bị chặn VĨNH VIỄN vì mã này không bao giờ vào nổi tập đã
    duyệt — kể cả xe máy tải 180 kg có thật.
    """

    from src.agents.domain.claim_policy import feature_codes_mentioned

    assert "HIGH_PAYLOAD" not in feature_codes_mentioned(message)


@pytest.mark.parametrize("message", ["xe chở được nặng", "chở nặng", "tải trọng lớn"])
def test_cum_tai_trong_nay_do_cam_quan_nhan(message: str) -> None:
    """Không được rơi vào khoảng trống: bỏ khỏi bảng tính năng thì phải có bảng
    khác nhận, nếu không là lặng lẽ mất một cách nói phổ biến."""

    from src.agents.domain.perceptual_traits import TRAIT_HEAVY_CARRY, trait_codes_mentioned

    assert TRAIT_HEAVY_CARRY in trait_codes_mentioned(message)


def test_hai_bang_cum_chu_khong_cung_giu_mot_cum() -> None:
    """Một cụm nằm ở CẢ hai bảng thì bảng tính năng chặn trước, bảng cảm quan
    không bao giờ được hỏi tới — giấy phép theo số trở nên vô nghĩa mà không ai
    thấy. Chốt chặn để lần mở rộng sau không vô tình dựng lại tình trạng đó."""

    from src.agents.domain.claim_policy import _FEATURE_CLAIM_CUES
    from src.agents.domain.perceptual_traits import _TRAIT_CUES

    feature_cues = {cue for cues in _FEATURE_CLAIM_CUES.values() for cue in cues}
    trait_cues = {cue for cues in _TRAIT_CUES.values() for cue in cues}

    assert not (feature_cues & trait_cues), f"cụm nằm ở cả hai bảng: {sorted(feature_cues & trait_cues)}"


def test_fast_charging_is_backed_by_the_charge_time_fact_in_the_snapshot() -> None:
    """BUG PROD 2026-08-26: 32/32 pitch bị vứt đều vì đúng cụm "sạc nhanh".

    Không mô hình nào bịa: cả 10 ô tô đều sạc nhanh được, và số phút sạc nằm sẵn
    trong snapshot. Nhưng tập mã đã duyệt chỉ đọc claim plan, mà claim plan chỉ
    chứa tính năng KHÁCH NHẮC — khách không nhắc sạc nhanh thì câu "sạc nhanh
    trong {FAST_CHARGE_TIME_MINUTES} phút" bị kết tội bịa, dù con số ngay bên
    cạnh chính là bằng chứng.

    Nặng hơn: nhãn thông số của bản dựng tay là "Thời gian sạc nhanh", nên chính
    lưới đỡ cũng vướng cùng cái bẫy.
    """

    backed = feature_codes_backed_by_facts({"FAST_CHARGE_TIME_MINUTES", "CAR_RANGE_KM"})

    assert "FAST_CHARGING" in backed
    reject_unbacked_feature_claims(
        "* **Thời gian sạc nhanh**: 31 phút",
        approved_feature_codes=backed,
    )


def test_a_snapshot_without_any_charging_fact_still_rejects_the_claim() -> None:
    """Ca ÂM TÍNH: không có thông số sạc thì "sạc nhanh" vẫn là lời bịa."""

    backed = feature_codes_backed_by_facts({"CAR_RANGE_KM", "STARTING_PRICE_VND"})

    assert backed == frozenset()
    with pytest.raises(ValueError):
        reject_unbacked_feature_claims("Xe hỗ trợ sạc nhanh.", approved_feature_codes=backed)


def test_seat_count_fact_does_not_authorize_a_seven_seater_claim() -> None:
    """Chỉ mã nào mà FACT là bằng chứng ĐỦ mới được vào bảng.

    "Có số chỗ ngồi" không suy ra "bảy chỗ" — nếu bảng nới ra tới đó thì một xe
    4 chỗ được phép tự xưng bảy chỗ.
    """

    backed = feature_codes_backed_by_facts({"CAR_SEAT_COUNT"})

    assert "7_SEATER" not in backed


def test_a_vague_convenience_claim_is_blocked() -> None:
    """BUG PROD 2026-08-27, Sếp bắt được. Đo trên 6 pitch thật liên tiếp: 5 cái
    mang cụm "rất tiện lợi", không cái nào có căn cứ.

        "hợp với mục đích sử dụng Quý khách chia sẻ nên RẤT TIỆN LỢI cho việc
         di chuyển trong đô thị"

    Mô hình nhại lại lời khách rồi khẳng định thành đặc tính sản phẩm — đúng lỗi
    đã bắt hồi 2026-08-26 ở vế "nhỏ gọn". Vế "rất tiện lợi" sống sót vì không có
    trong danh sách, nên nguyên nửa câu bịa vẫn ra tới khách suốt từ đó.
    """

    with pytest.raises(ValueError):
        reject_unstructured_claims("nên rất tiện lợi cho việc di chuyển trong đô thị.")


def test_a_vague_flexibility_claim_is_blocked() -> None:
    """BUG PROD 2026-08-27: pitch tự nhận xe "di chuyển linh hoạt"."""

    with pytest.raises(ValueError):
        reject_unstructured_claims("Mẫu xe này có khả năng di chuyển linh hoạt trong nội thành.")


def test_new_praise_cues_do_not_collide_with_approved_vocabulary() -> None:
    """Cue cấm mới không được vô hiệu hoá claim, trait hay nhãn tính năng đã duyệt."""

    from src.agents.domain.claim_policy import _CLAIM_TEXT_BY_SLOT
    from src.agents.domain.perceptual_traits import TRAIT_PHRASING
    from src.agents.prompts.feature_askable import FEATURE_LABELS

    approved_texts = (*_CLAIM_TEXT_BY_SLOT.values(), *TRAIT_PHRASING.values(), *FEATURE_LABELS.values())

    assert all("linh hoạt" not in text.casefold() for text in approved_texts)


def test_the_home_charging_claim_still_passes() -> None:
    """Ca ÂM TÍNH: claim hợp lệ viết "THUẬN TIỆN sạc tại nhà".

    Chặn "tiện" trần sẽ giết chính câu đã duyệt.
    """

    reject_unstructured_claims("thuận tiện sạc tại nhà theo điều kiện Quý khách chia sẻ.")
    reject_unstructured_claims("Sang trọng tiện nghi.")


def test_only_equipment_claims_may_join_the_extra_sentence() -> None:
    """Câu "Ngoài ra xe còn …" gom TRANG BỊ, không gom thông số hay claim slot.

    Lời dặn cũ không nêu tên placeholder nào nên mô hình vơ cả vào, ra hai câu
    hỏng trên prod: *"Ngoài ra xe còn 5 chỗ ngồi"* (đọc như còn thừa 5 chỗ) và
    *"Ngoài ra xe còn thuộc đúng dòng xe Quý khách đang tìm"*.
    """

    from src.agents.domain.claim_policy import EQUIPMENT_CLAIM_PREFIXES

    equipment = "được trang bị móc gắn ghế trẻ em ISOFIX"
    confirmed = "có đúng khoá chống trộm mà Quý khách vừa xác nhận quan tâm ở lượt trước"
    assert equipment.startswith(EQUIPMENT_CLAIM_PREFIXES)
    assert confirmed.startswith(EQUIPMENT_CLAIM_PREFIXES)

    for not_equipment in (
        "thuộc đúng dòng xe Quý khách đang tìm",
        "đủ chỗ cho số người Quý khách thường chở",
        "có giá nằm trong ngân sách Quý khách dự tính",
        "hợp với mục đích sử dụng Quý khách chia sẻ",
    ):
        assert not not_equipment.startswith(EQUIPMENT_CLAIM_PREFIXES)
