"""Allowlist tính năng lượt 2 (T7) — mở rộng 2026-08-21 (TOWING, BATTERY_SWAPPABLE)."""

from __future__ import annotations

from src.agents.domain.values import PurposeBucket, VehicleType
from src.agents.prompts.feature_askable import ALL_ASKABLE, FEATURE_LABELS, askable_for


def test_towing_is_askable_for_car_family_and_work() -> None:
    assert "TOWING" in askable_for(VehicleType.CAR, PurposeBucket.FAMILY)
    assert "TOWING" in askable_for(VehicleType.CAR, PurposeBucket.WORK)


def test_towing_is_not_askable_for_car_service() -> None:
    assert "TOWING" not in askable_for(VehicleType.CAR, PurposeBucket.SERVICE)


def test_battery_swappable_is_askable_for_every_motorbike_bucket() -> None:
    for bucket in (PurposeBucket.WORK, PurposeBucket.DELIVERY, PurposeBucket.PERSONAL):
        assert "BATTERY_SWAPPABLE" in askable_for(VehicleType.ELECTRIC_MOTORBIKE, bucket)


def test_new_codes_have_vietnamese_labels() -> None:
    assert FEATURE_LABELS["TOWING"] == "móc kéo moóc"
    assert FEATURE_LABELS["BATTERY_SWAPPABLE"] == "đổi pin nhanh tại trạm"
    assert FEATURE_LABELS["FAST_CHARGING"] == "sạc nhanh"


def test_all_askable_includes_the_new_codes() -> None:
    assert {"TOWING", "BATTERY_SWAPPABLE", "FAST_CHARGING"} <= ALL_ASKABLE


def test_fast_charging_is_askable_for_every_car_bucket() -> None:
    """Sếp 2026-08-21: "sạc nhanh" có dữ liệu thật (10 xe đã duyệt YES, 0 NO —
    xác thực dù không tách đôi được), đáng xác nhận khi khách hỏi dù không tự
    được chọn làm câu hỏi mở đầu (không phân biệt được xe nào với xe nào)."""

    for bucket in (PurposeBucket.FAMILY, PurposeBucket.WORK, PurposeBucket.SERVICE):
        assert "FAST_CHARGING" in askable_for(VehicleType.CAR, bucket)


def test_panoramic_roof_is_not_askable_anywhere() -> None:
    """ "Cửa sổ trời" KHÔNG được thêm — catalog chưa duyệt dữ liệu cho bất kỳ
    xe nào (0 bản ghi), thêm vào chỉ trỏ tới allowlist không có gì xác nhận."""

    assert "PANORAMIC_ROOF" not in ALL_ASKABLE


def test_high_payload_is_no_longer_askable_because_no_vehicle_has_it() -> None:
    """Nhóm C 2026-08-26: `HIGH_PAYLOAD` có 0 cờ `YES` — hỏi "có cần tải trọng
    lớn không" mà khách đáp "có" thì không xe nào khớp (im lặng, không lỗi)."""

    assert "HIGH_PAYLOAD" not in ALL_ASKABLE
    assert {"BATTERY_REMOVABLE", "ANTI_THEFT"} <= ALL_ASKABLE


def test_car_fallback_for_an_unmapped_bucket_never_offers_motorbike_only_codes() -> None:
    """Bug thật 2026-08-21 (Sếp báo): hỏi ô tô với mục đích rơi ngoài
    FAMILY/WORK/SERVICE (vd DELIVERY, PERSONAL) từng fallback về `ALL_ASKABLE`
    gộp cả nhánh xe máy — gợi ý "pin tháo rời"/"đổi pin nhanh" cho khách mua ô
    tô. Fallback giờ phải tự giới hạn trong mã CỦA Ô TÔ."""

    for bucket in (PurposeBucket.DELIVERY, PurposeBucket.PERSONAL):
        askable = askable_for(VehicleType.CAR, bucket)
        assert "BATTERY_REMOVABLE" not in askable
        assert "BATTERY_SWAPPABLE" not in askable
        assert askable  # vẫn phải có gì đó để hỏi, không rỗng


def test_motorbike_fallback_for_an_unmapped_bucket_never_offers_car_only_codes() -> None:
    askable = askable_for(VehicleType.ELECTRIC_MOTORBIKE, PurposeBucket.FAMILY)

    assert "TOWING" not in askable
    assert askable


# ── Nhãn hiển thị của TOÀN BỘ danh mục ────────────────────────────────────────

import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from src.agents.domain.claim_policy import UNSTRUCTURED_CLAIM_PATTERN  # noqa: E402
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS  # noqa: E402
from src.agents.services.synthesis import DIGIT_PATTERN, RAW_STRUCTURED_PATTERN  # noqa: E402

_FEATURE_DEFINITIONS_CSV = Path("data-p150/catalog/feature_definitions.csv")


def _active_feature_codes() -> list[str]:
    with _FEATURE_DEFINITIONS_CSV.open(encoding="utf-8") as handle:
        return [row["feature_code"] for row in csv.DictReader(handle) if row["status"] == "ACTIVE"]


def test_every_active_feature_code_has_a_vietnamese_label() -> None:
    """`scoring._feature_showcase_reasons` BỎ QUA mã không có nhãn — im lặng, đúng
    theo thiết kế. Nên mã mới thêm vào catalog mà quên nhãn thì không lỗi ở đâu
    cả, nó chỉ lặng lẽ không bao giờ được kể cho khách. Test này là chỗ duy nhất
    bắt được."""

    missing = sorted(set(_active_feature_codes()) - set(FEATURE_DISPLAY_LABELS))

    assert not missing, f"thiếu nhãn tiếng Việt cho: {missing}"


def test_every_active_feature_has_a_useful_customer_description() -> None:
    """Mô tả phải đủ ý để khách hiểu công dụng + tình huống dùng, không chỉ lặp nhãn."""

    with _FEATURE_DEFINITIONS_CSV.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["status"] == "ACTIVE"]

    descriptions = [row["description"].strip() for row in rows]

    assert all(len(description) >= 90 for description in descriptions)
    assert all(description.endswith(".") for description in descriptions)
    assert len(descriptions) == len(set(descriptions))


def test_need_tag_descriptions_are_rich_enough_for_matching() -> None:
    """Need-tag description là đầu vào embedding; quá ngắn làm mất cách nói phổ biến."""

    from src.agents.domain.need_tags import NEED_TAG_REGISTRY

    descriptions = [definition.description_vi.strip() for definition in NEED_TAG_REGISTRY.values()]

    assert all(len(description) >= 120 for description in descriptions)
    assert all(description.endswith(".") for description in descriptions)
    assert len(descriptions) == len(set(descriptions))


@pytest.mark.parametrize("code", sorted(FEATURE_DISPLAY_LABELS))
def test_label_obeys_the_three_hard_synthesis_constraints(code: str) -> None:
    """Ba ràng buộc cứng, sai cái nào cũng làm vỡ pitch chứ không chỉ xấu chữ:

    1. Chữ số — `synthesis._reject_digits_outside_placeholders` quét CẢ prompt,
       mà prompt in nguyên văn nhãn ⇒ raise trước khi kịp gọi LLM.
    2. Dấu gạch dưới / tên trường — `RAW_STRUCTURED_PATTERN` chặn trong draft.
    3. Cụm "hỗ trợ"/"phù hợp"/"đáp ứng"… — `UNSTRUCTURED_CLAIM_PATTERN` chặn phần
       văn xuôi ngoài placeholder, và LLM rất hay chép nguyên nhãn vào câu của nó.
    """

    label = FEATURE_DISPLAY_LABELS[code]

    assert not DIGIT_PATTERN.search(label), f"{code}: nhãn có chữ số"
    assert not RAW_STRUCTURED_PATTERN.search(label), f"{code}: nhãn có dấu vết kỹ thuật"
    assert not UNSTRUCTURED_CLAIM_PATTERN.search(label), f"{code}: nhãn chứa cụm khẳng định bị chặn"


# ── Nhóm C (2026-08-26): chốt chặn mã ma ──────────────────────────────────────

_FLAGS_CSV = Path("data-p150/catalog/vehicle_feature_flags.csv")


def _yes_feature_codes() -> set[str]:
    with _FLAGS_CSV.open(encoding="utf-8") as handle:
        return {row["feature_code"] for row in csv.DictReader(handle) if row["status"] == "YES"}


def test_every_askable_code_has_at_least_one_yes_flag() -> None:
    """Chốt chặn: mã hỏi được lượt 2 mà không xe nào có cờ YES thì câu hỏi vô
    nghĩa — `_feature_mention_reasons` lọc `FLAG + YES` ra rỗng, không cộng điểm,
    không lỗi, im lặng. Ai thêm mã không có cờ vào `ASKABLE_FEATURES` thì test đỏ."""

    missing = sorted(set(ALL_ASKABLE) - _yes_feature_codes())

    assert not missing, f"mã hỏi được nhưng không xe nào có cờ YES: {missing}"


def test_every_default_feature_code_has_at_least_one_yes_flag() -> None:
    """Cùng chốt chặn cho `default_feature_codes` của need tag."""

    from src.agents.domain.need_tags import NEED_TAG_REGISTRY

    defaults = {code for definition in NEED_TAG_REGISTRY.values() for code in definition.default_feature_codes}
    missing = sorted(defaults - _yes_feature_codes())

    assert not missing, f"mã trong default_feature_codes không xe nào có cờ YES: {missing}"


def test_moi_ma_deu_co_nhan_khi_khach_vua_chon_no() -> None:
    """`recommendation` dựng `feature_mention_labels` cho mã khách VỪA chọn, và
    `scoring._feature_mention_reasons` rơi về in MÃ THÔ khi thiếu nhãn.

    Bug thật 2026-08-26, thấy khi chạy hội thoại thật trên prod: bảng chỉ tra
    `FEATURE_LABELS` (6 mã hỏi được lượt 2), nên khách chọn "cảnh báo điểm mù" thì
    pitch gửi khách đọc "có đúng BLIND_SPOT_MONITOR mà Quý khách vừa xác nhận
    quan tâm". `RAW_STRUCTURED_PATTERN` không cứu được: mã nằm trong claim
    placeholder nên phần văn xuôi bị bóc ra trước khi kiểm.
    """

    thieu = [
        code
        for code in FEATURE_DISPLAY_LABELS
        if not (FEATURE_LABELS.get(code) or FEATURE_DISPLAY_LABELS.get(code))
    ]

    assert thieu == []


@pytest.mark.parametrize("code", sorted(FEATURE_DISPLAY_LABELS))
def test_nhan_khong_bao_gio_la_chinh_ma_thô(code: str) -> None:
    """Nhãn trùng mã nghĩa là fallback đã lọt qua mà không ai thấy."""

    label = FEATURE_LABELS.get(code) or FEATURE_DISPLAY_LABELS[code]

    assert label != code
    assert "_" not in label
