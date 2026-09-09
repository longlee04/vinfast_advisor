"""Cảm quan chỉ được nói khi THÔNG SỐ đỡ được.

Sếp 2026-08-26: chặn thẳng "mạnh mẽ"/"rộng rãi" là thô — nó giết cả câu đúng.
VF 9 công suất 300 kW thì "vận hành mạnh mẽ" là sự thật. Bộ test này khoá hai
chiều: xe đủ số thì được nói, xe không đủ thì không.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from src.agents.domain.perceptual_traits import (
    _TRAIT_RULES,
    TRAIT_HEAVY_CARRY,
    TRAIT_LARGE_CARGO,
    TRAIT_PHRASING,
    TRAIT_STRONG_MOTOR,
    TRAIT_SUV_STANCE,
    reject_unbacked_trait_claims,
    trait_codes_mentioned,
    traits_from_values,
)

_CATALOG = Path(__file__).resolve().parents[4] / "data-p150" / "catalog"


# ── Suy cảm quan từ số ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"CAR_MOTOR_POWER_KW": "300.00"}, {TRAIT_STRONG_MOTOR}),
        ({"CAR_MOTOR_POWER_KW": "150.00"}, {TRAIT_STRONG_MOTOR}),
        ({"CAR_MOTOR_POWER_KW": "130.00"}, set()),
        ({"CAR_MOTOR_POWER_KW": "30.00"}, set()),
        ({"CARGO_VOLUME_STANDARD_L": "446.00"}, {TRAIT_LARGE_CARGO}),
        ({"CARGO_VOLUME_STANDARD_L": "376.00"}, {TRAIT_LARGE_CARGO}),
        ({"CARGO_VOLUME_STANDARD_L": "260.00"}, set()),
        ({"MOTORBIKE_MAX_LOAD_KG": "180.00"}, {TRAIT_HEAVY_CARRY}),
        ({"MOTORBIKE_MAX_LOAD_KG": "150.00"}, {TRAIT_HEAVY_CARRY}),
        ({"MOTORBIKE_MAX_LOAD_KG": "130.00"}, set()),
    ],
)
def test_nguong_tach_dung_theo_so(values: dict[str, str], expected: set[str]) -> None:
    """Ngưỡng là ĐIỀU KIỆN ĐỦ để được phép nói. Bằng đúng ngưỡng thì tính."""

    assert traits_from_values(values) == expected


def test_mot_xe_co_the_mang_nhieu_cam_quan() -> None:
    values = {"CAR_MOTOR_POWER_KW": "300.00", "CARGO_VOLUME_STANDARD_L": "376.00"}

    assert traits_from_values(values) == {TRAIT_STRONG_MOTOR, TRAIT_LARGE_CARGO}


@pytest.mark.parametrize("value_text", ["", "  ", "khong phai so", "nhiều", "N/A"])
def test_thong_so_khong_doc_duoc_thi_khong_co_can_cu(value_text: str) -> None:
    """Không parse được thì coi như KHÔNG có căn cứ — im lặng bỏ qua, không
    raise. Một thông số lạ dạng không được phép làm hỏng cả lượt tổng hợp."""

    assert traits_from_values({"CAR_MOTOR_POWER_KW": value_text}) == frozenset()


def test_thieu_thong_so_thi_khong_co_can_cu() -> None:
    assert traits_from_values({}) == frozenset()


# ── Chiều RA: pitch nói cảm quan ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("prose", "traits"),
    [
        ("Xe vận hành mạnh mẽ trên đường trường.", frozenset({TRAIT_STRONG_MOTOR})),
        ("Khoang hành lý rộng, xếp đồ cả nhà thoải mái.", frozenset({TRAIT_LARGE_CARGO})),
        ("Xe chở khoẻ, đi giao hàng cả ngày.", frozenset({TRAIT_HEAVY_CARRY})),
    ],
)
def test_co_can_cu_thi_duoc_noi(prose: str, traits: frozenset[str]) -> None:
    reject_unbacked_trait_claims(prose, approved_traits=traits)


@pytest.mark.parametrize(
    "prose",
    [
        "Xe vận hành mạnh mẽ trên đường trường.",
        "Xe có động cơ mạnh.",
        "Khoang hành lý rộng.",
        "Cốp rộng, xếp được nhiều đồ.",
        "Xe chở nặng tốt.",
        "Tải trọng lớn, chạy dịch vụ bền.",
    ],
)
def test_khong_can_cu_thi_bi_chan(prose: str) -> None:
    """Đây đúng cơ chế đã đẻ ra "VF 8 nhỏ gọn": câu nghe như sự thật, không có
    gì đỡ. Chặn ở đây để mô hình viết lại, chứ không sửa câu hộ nó."""

    with pytest.raises(ValueError, match="unbacked perceptual claim"):
        reject_unbacked_trait_claims(prose, approved_traits=frozenset())


def test_can_cu_cua_cam_quan_nay_khong_mo_khoa_cam_quan_kia() -> None:
    """Xe mạnh KHÔNG vì thế mà được nhận cốp rộng."""

    with pytest.raises(ValueError, match="TRAIT_LARGE_CARGO"):
        reject_unbacked_trait_claims("Cốp rộng lắm.", approved_traits=frozenset({TRAIT_STRONG_MOTOR}))


@pytest.mark.parametrize(
    "prose",
    [
        "Xe co dong co manh.",
        "Khoang hanh ly rong.",
        "Xe cho nang tot.",
    ],
)
def test_bo_dau_van_bat_duoc(prose: str) -> None:
    """Gõ không dấu là cách viết rất thường, không phải lỗi gõ. Bản đầu của bảng
    cụm chữ tính năng chỉ `casefold()` nên "nho gon" trượt "nhỏ gọn" — đo trên
    prod mới thấy. Bảng này bỏ dấu ngay từ đầu."""

    with pytest.raises(ValueError, match="unbacked perceptual claim"):
        reject_unbacked_trait_claims(prose, approved_traits=frozenset())


# ── Chiều ÂM: câu không nói gì về cảm quan thì không được dính ────────────────


@pytest.mark.parametrize(
    "prose",
    [
        "Xe có khoá chống trộm.",
        "Giá khoảng năm trăm triệu.",
        "Xe chở được năm người.",
        "Đa dạng lựa chọn cho Quý khách.",
        "Xe thuộc đúng dòng Quý khách đang tìm.",
        "Quý khách quan tâm tới tính năng nào ạ?",
    ],
)
def test_cau_khong_lien_quan_khong_bi_chan(prose: str) -> None:
    """Bài học "k" nuốt "khoá chống trộm": sai theo chiều ăn mất câu trả lời
    thật là kiểu sai tệ nhất, và nó im lặng. Mỗi cụm mới phải kiểm chiều ÂM."""

    reject_unbacked_trait_claims(prose, approved_traits=frozenset())


def test_ten_xe_that_khong_dinh_cum_nao() -> None:
    """`reject_unbacked_trait_claims` so bằng chuỗi con. Tên bản xe có thật xuất
    hiện trong MỌI pitch — dính một cụm là loại oan toàn bộ."""

    with (_CATALOG / "vehicles.csv").open(encoding="utf-8") as handle:
        names = [f"{row['model_name']} {row.get('variant_name') or ''}".strip() for row in csv.DictReader(handle)]

    for name in names:
        reject_unbacked_trait_claims(f"Xe {name} là lựa chọn của Quý khách.", approved_traits=frozenset())


# ── Chiều VÀO: lời khách ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("anh cần xe chở nặng", {TRAIT_HEAVY_CARRY}),
        ("xe nào mạnh mẽ nhất", {TRAIT_STRONG_MOTOR}),
        ("muốn cốp rộng để đi du lịch", {TRAIT_LARGE_CARGO}),
        ("xe cho nang", {TRAIT_HEAVY_CARRY}),
        ("giá bao nhiêu", set()),
        ("em ơi", set()),
    ],
)
def test_nhan_cam_quan_tu_loi_khach(utterance: str, expected: set[str]) -> None:
    assert trait_codes_mentioned(utterance) == expected


# ── Ngưỡng phải còn tách được xe, không phải ai cũng đạt ──────────────────────


@pytest.mark.parametrize(("trait", "fact_code", "threshold"), _TRAIT_RULES)
def test_nguong_van_tach_duoc_xe(trait: str, fact_code: str, threshold: Decimal) -> None:
    """Chốt chặn kiểu nhóm C, đổi chiều: một cảm quan mà MỌI xe đều đạt thì nó
    không nói lên điều gì, còn KHÔNG xe nào đạt thì nó là cảm quan ma — pitch
    không bao giờ được phép dùng, y hệt ba mã ma vừa dọn.

    Ngưỡng đo từ dữ liệu thật; test này đỏ khi ai đó đổi ngưỡng hoặc khi catalog
    đổi tới mức ngưỡng cũ hết ý nghĩa.
    """

    column = {
        "CAR_MOTOR_POWER_KW": ("cars.csv", "motor_power_kw"),
        "CARGO_VOLUME_STANDARD_L": ("cars.csv", "cargo_volume_standard_l"),
        "MOTORBIKE_MAX_LOAD_KG": ("motorbikes.csv", "max_load_kg"),
    }[fact_code]

    with (_CATALOG / column[0]).open(encoding="utf-8") as handle:
        values = [row[column[1]] for row in csv.DictReader(handle)]

    numeric = [Decimal(value) for value in values if value.strip() and value.strip() != "0.0"]
    reached = [value for value in numeric if value >= threshold]

    assert reached, f"{trait}: không xe nào đạt ngưỡng {threshold} — cảm quan ma"
    assert len(reached) < len(numeric), f"{trait}: mọi xe đều đạt ngưỡng {threshold} — không tách được gì"


# ── Cụm gợi ý cho prompt ─────────────────────────────────────────────────────


@pytest.mark.parametrize(("trait", "phrase"), sorted(TRAIT_PHRASING.items()))
def test_cum_goi_y_phai_nam_trong_cue_cua_chinh_no(trait: str, phrase: str) -> None:
    """Mô hình rất hay chép NGUYÊN VĂN gợi ý. Chép xong mà không khớp cue thì
    giấy phép theo số thành vô dụng — câu bị loại dù xe đủ thông số."""

    assert trait_codes_mentioned(phrase) == {trait}


@pytest.mark.parametrize("phrase", sorted(TRAIT_PHRASING.values()))
def test_cum_goi_y_khong_lam_vo_pitch(phrase: str) -> None:
    """Ba ràng buộc cứng, sai cái nào cũng loại cả pitch chứ không chỉ xấu chữ:
    chữ số làm `_reject_digits_outside_placeholders` raise, gạch dưới dính
    `RAW_STRUCTURED_PATTERN`, và "phù hợp"/"hỗ trợ"/"đáp ứng" dính
    `UNSTRUCTURED_CLAIM_PATTERN`."""

    from src.agents.domain.claim_policy import UNSTRUCTURED_CLAIM_PATTERN
    from src.agents.services.synthesis import DIGIT_PATTERN, RAW_STRUCTURED_PATTERN

    assert not DIGIT_PATTERN.search(phrase)
    assert not RAW_STRUCTURED_PATTERN.search(phrase)
    assert not UNSTRUCTURED_CLAIM_PATTERN.search(phrase)


def test_moi_cam_quan_deu_co_cum_goi_y() -> None:
    """Cảm quan không có cụm gợi ý thì mô hình không bao giờ biết để dùng — nó
    chỉ tồn tại như một cái chặn, đúng thứ việc này đang đi chữa."""

    from src.agents.domain.perceptual_traits import _TRAIT_TEXT_RULES

    declared = {trait for trait, _fact, _threshold in _TRAIT_RULES}
    declared |= {trait for trait, _fact, _accepted in _TRAIT_TEXT_RULES}
    assert declared == set(TRAIT_PHRASING)


def test_prompt_ke_dung_cum_xe_do_duoc_phep_noi() -> None:
    from src.agents.prompts.synthesis_prompts import build_synthesis_prompt

    prompt = build_synthesis_prompt(
        vehicle_name="VF 9 All New",
        available_claims=(("CLAIM_VEHICLE_TYPE", "thuộc đúng dòng xe"),),
        available_placeholders=("CAR_MOTOR_POWER_KW",),
        available_traits=("vận hành mạnh mẽ",),
    )

    assert "vận hành mạnh mẽ" in prompt
    assert "khoang hành lý rộng" not in prompt


def test_prompt_khong_nhac_gi_khi_xe_khong_du_thong_so() -> None:
    """Xe không đủ căn cứ thì prompt phải IM, không phải kể danh sách rỗng —
    một dòng "các cách nói sau: " cụt lủn là lời mời mô hình tự điền."""

    from src.agents.prompts.synthesis_prompts import build_synthesis_prompt

    prompt = build_synthesis_prompt(
        vehicle_name="VF 3 All New",
        available_claims=(("CLAIM_VEHICLE_TYPE", "thuộc đúng dòng xe"),),
        available_placeholders=("CAR_MOTOR_POWER_KW",),
    )

    assert "cách nói" not in prompt


# ── Dáng SUV: cảm quan suy từ một giá trị CHỮ (Sếp 2026-08-26) ───────────────


def test_xe_suv_duoc_phep_noi_gam_cao() -> None:
    """"gầm cao" từng bị `UNSTRUCTURED_CLAIM_PATTERN` chặn CỨNG vì catalog không
    có cột khoảng sáng gầm nào.

    `body_type` là căn cứ duy nhất còn lại, và nó đủ cho 11/11 mẫu — nên cách
    đúng là cấp phép theo dữ liệu, y như "mạnh mẽ" đã làm với công suất.
    """

    approved = traits_from_values({"CAR_BODY_TYPE": "SUV"})

    assert TRAIT_SUV_STANCE in approved
    reject_unbacked_trait_claims("Xe có gầm cao, đi đường xấu yên tâm.", approved_traits=approved)


def test_xe_khong_phai_suv_thi_van_bi_chan() -> None:
    """VF 2 là Hatchback — mẫu duy nhất trong catalog không phải SUV.

    Cấp phép theo dữ liệu chỉ có nghĩa khi nó CÒN từ chối được: nới thành "mọi ô
    tô đều gầm cao" là quay lại đúng kiểu sai của VF 8, chỉ đổi thông số.
    """

    approved = traits_from_values({"CAR_BODY_TYPE": "Hatchback"})

    assert TRAIT_SUV_STANCE not in approved
    with pytest.raises(ValueError):
        reject_unbacked_trait_claims("Xe có gầm cao, đi đường xấu yên tâm.", approved_traits=approved)
