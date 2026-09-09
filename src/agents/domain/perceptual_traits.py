"""Cảm quan SUY TỪ SỐ — cho pitch nói "mạnh mẽ" khi xe thật sự mạnh.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

**Vì sao có file này** (Sếp 2026-08-26): `UNSTRUCTURED_CLAIM_PATTERN` chặn thẳng
"mạnh mẽ", "rộng rãi", "gầm cao" sau lỗi VF 8. Chặn đúng về mặt an toàn nhưng
thô — nó giết cả câu ĐÚNG. VF 9 công suất 300 kW, nói "vận hành mạnh mẽ" không
sai chỗ nào; bịt miệng nó là mất một điểm bán hàng thật.

Đường ra không phải nới mẫu chặn, mà là **đưa căn cứ**. Kiến trúc đã sẵn lối:
pitch được phép nói "500 km" vì con số đi qua placeholder `{CAR_RANGE_KM}`. Cảm
quan đi cùng đường đó — chỉ khác chỗ nó không in ra số, mà dùng số làm giấy phép.

**Vì sao KHÔNG thêm cờ tính năng mới**: đó đúng là cách đẻ ra ba mã ma
(`ECO_MODE`, `HIGH_PAYLOAD`, `HIGH_RANGE_BATTERY` — có định nghĩa, 0 cờ, agent
hỏi những câu không câu trả lời nào đổi được kết quả). Cờ phải điền tay cho 51
xe rồi để trống 79% ô. Cột thông số thì ngược lại — gần như đầy:

    body_type          11/11 ô tô        max_load_kg      40/40 xe máy
    motor_power_kw     11/11 ô tô        seat_height_mm   40/40 xe máy
    cargo_volume       10/11 ô tô        motor_power_w    40/40 xe máy

Suy từ số đã có thì không sinh thêm một ô trống nào.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Final

#: Mã cảm quan. Tiền tố `TRAIT_` tách hẳn khỏi `feature_code` — chúng KHÔNG phải
#: tính năng, không có cờ, không vào `feature_definitions`. Trộn hai không gian
#: tên là mời người sau đi tìm `STRONG_MOTOR` trong catalog rồi kết luận dữ liệu hỏng.
TRAIT_STRONG_MOTOR: Final[str] = "TRAIT_STRONG_MOTOR"
TRAIT_LARGE_CARGO: Final[str] = "TRAIT_LARGE_CARGO"
TRAIT_HEAVY_CARRY: Final[str] = "TRAIT_HEAVY_CARRY"
TRAIT_SUV_STANCE: Final[str] = "TRAIT_SUV_STANCE"


#: (mã cảm quan, mã fact, ngưỡng). Ngưỡng đo từ dữ liệu thật 2026-08-26, KHÔNG
#: bịa — mỗi cái rơi vào một khoảng trống tự nhiên của phân phối:
#:
#: - `CAR_MOTOR_POWER_KW`: 300×3 · 170 · 150×2 · 130 · 100×2 · 30×2.
#:   Ngưỡng 150 kW (≈200 mã lực) tách sáu xe trên khỏi năm xe dưới.
#: - `CARGO_VOLUME_STANDARD_L`: 446 · 423×2 · 376×3 · 260 · 212 · 47 · 36.
#:   Ngưỡng 376 L tách sáu xe khoang lớn.
#: - `MOTORBIKE_MAX_LOAD_KG`: 180×6 · 160 · 150×2 · 140 · 130×27 · 120 · 103 · 90.
#:   130 kg là mốc phổ thông (27/40 xe), nên ngưỡng phải nằm TRÊN nó: 150 kg.
#:
#: Ngưỡng là ĐIỀU KIỆN ĐỦ để được phép nói, không phải điều kiện xếp hạng. Xe
#: dưới ngưỡng không bị chê — pitch chỉ không được tự nhận thay nó.
_TRAIT_RULES: Final[tuple[tuple[str, str, Decimal], ...]] = (
    (TRAIT_STRONG_MOTOR, "CAR_MOTOR_POWER_KW", Decimal("150")),
    (TRAIT_LARGE_CARGO, "CARGO_VOLUME_STANDARD_L", Decimal("376")),
    (TRAIT_HEAVY_CARRY, "MOTORBIKE_MAX_LOAD_KG", Decimal("150")),
)


#: Cảm quan suy từ một giá trị CHỮ thay vì một ngưỡng số.
#:
#: `body_type` là thông số duy nhất trong catalog nói được về dáng xe — bảng
#: `cars` không có cột khoảng sáng gầm nào, nên "gầm cao" chỉ có đúng một căn cứ
#: này. Suy từ nó là suy từ dữ liệu đã có, không phải bịa thêm một cờ.
#:
#: **Cảm quan này KHÔNG phân biệt được xe** — 10/11 mẫu ô tô là SUV, chỉ VF 2 là
#: Hatchback. Nó tồn tại để pitch được PHÉP NÓI điều khách hỏi, không để xếp
#: hạng. Nhầm hai vai là dựng một tiêu chí lọc chia tập ứng viên 10–1.
_TRAIT_TEXT_RULES: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (TRAIT_SUV_STANCE, "CAR_BODY_TYPE", frozenset({"suv"})),
)


#: Cụm chữ của từng cảm quan, dùng cho CẢ HAI CHIỀU y như `_FEATURE_CLAIM_CUES`.
#:
#: Chữ phải nói đúng cái ĐO ĐƯỢC. `cargo_volume_standard_l` là dung tích KHOANG
#: HÀNH LÝ, không phải không gian cabin — bằng chứng: VF 9 là xe to nhất, bảy
#: chỗ, mà chỉ 212 L vì hàng ghế thứ ba dựng lên ăn hết cốp. Nên cụm ở đây là
#: "khoang rộng"/"cốp rộng", KHÔNG phải "rộng rãi" trống không: một câu "xe rộng
#: rãi" dựa trên số lít cốp là đúng kiểu sai của VF 8, chỉ đổi thông số.
#:
#: `UNSTRUCTURED_CLAIM_PATTERN` vẫn giữ "rộng rãi" trần — nói về khoang thì phải
#: nói rõ là khoang.
_TRAIT_CUES: Final[dict[str, tuple[str, ...]]] = {
    TRAIT_STRONG_MOTOR: ("mạnh mẽ", "vận hành mạnh", "động cơ mạnh", "khoẻ khoắn"),
    TRAIT_LARGE_CARGO: ("khoang hành lý rộng", "cốp rộng", "khoang chứa đồ rộng"),
    TRAIT_HEAVY_CARRY: ("chở khoẻ", "chở nặng", "tải trọng lớn", "chở được nặng"),
    TRAIT_SUV_STANCE: ("gầm cao", "dáng suv", "kiểu suv", "gầm xe cao"),
}


#: Cụm chữ GỢI Ý cho prompt tổng hợp — mô hình cần biết nó ĐƯỢC PHÉP nói gì, chứ
#: không chỉ bị chặn khi nói sai. Gỡ chặn mà không mời dùng thì cảm quan chỉ nằm
#: đó: mô hình vẫn viết "mạnh mẽ" ngẫu nhiên cho xe bất kỳ rồi ăn một lần retry.
#:
#: Mỗi cụm phải nằm TRONG `_TRAIT_CUES` của chính nó — mô hình rất hay chép
#: nguyên văn gợi ý, và chép xong mà không khớp cue thì giấy phép thành vô dụng.
#: Ba ràng buộc cứng của `synthesis` cũng áp ở đây: không chữ số, không gạch
#: dưới, không "phù hợp"/"hỗ trợ"/"đáp ứng". Test đi kèm khoá cả bốn điều.
TRAIT_PHRASING: Final[dict[str, str]] = {
    TRAIT_STRONG_MOTOR: "vận hành mạnh mẽ",
    TRAIT_LARGE_CARGO: "khoang hành lý rộng",
    TRAIT_HEAVY_CARRY: "chở khoẻ",
    TRAIT_SUV_STANCE: "dáng SUV gầm cao",
}


def _fold(value: str) -> str:
    """Bỏ dấu + gộp khoảng trắng. Giống `claim_policy._fold_diacritics` — hai
    bảng cụm chữ phải so khớp cùng một kiểu, lệch nhau là lệch âm thầm."""

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d"))


_FOLDED_TRAIT_CUES: Final[dict[str, tuple[str, ...]]] = {
    trait: tuple(_fold(cue) for cue in cues) for trait, cues in _TRAIT_CUES.items()
}


def _as_decimal(value_text: str) -> Decimal | None:
    """`SynthesisFact.value_text` là chuỗi ("300.00"). Không parse được thì coi
    như KHÔNG có căn cứ — im lặng bỏ qua, không raise: một thông số lạ dạng
    không được phép làm hỏng cả lượt tổng hợp."""

    try:
        return Decimal(value_text.strip())
    except (InvalidOperation, AttributeError):
        return None


def traits_from_values(value_by_fact_code: dict[str, str]) -> frozenset[str]:
    """Thông số của MỘT xe → tập cảm quan xe đó được phép mang.

    Nhận `{fact_code: value_text}` chứ không nhận `SynthesisFact`, để hàm này
    nằm trọn trong `domain/` — mục 6.5b cấm `domain/` biết gì về `services/`.
    """

    earned = {
        trait
        for trait, fact_code, threshold in _TRAIT_RULES
        if (value := _as_decimal(value_by_fact_code.get(fact_code, ""))) is not None and value >= threshold
    }
    earned |= {
        trait
        for trait, fact_code, accepted in _TRAIT_TEXT_RULES
        if _fold(value_by_fact_code.get(fact_code, "")).strip() in accepted
    }
    return frozenset(earned)


def reject_unbacked_trait_claims(text_without_placeholders: str, *, approved_traits: frozenset[str]) -> None:
    """Chặn câu cảm quan mà thông số xe KHÔNG đỡ được.

    Cùng hình dạng với `claim_policy.reject_unbacked_feature_claims` một cách cố
    ý: hai hàm giải cùng một bài toán ("mô hình khẳng định thay cho dữ liệu"),
    khác nhau chỗ căn cứ đến từ cờ hay từ số. Ai sửa một cái nên ngó cái kia.
    """

    haystack = _fold(text_without_placeholders)
    for trait, cues in _FOLDED_TRAIT_CUES.items():
        if trait in approved_traits:
            continue
        for cue in cues:
            if cue in haystack:
                raise ValueError(f"unbacked perceptual claim in prose: {trait} ({cue!r})")


def trait_codes_mentioned(text: str) -> frozenset[str]:
    """Lời khách → cảm quan, bằng chính bảng cụm chữ ở trên.

    Chiều NGƯỢC, cùng lý do như `claim_policy.feature_codes_mentioned`: chữ nào
    đủ đặc trưng để kết tội một câu bịa thì cũng đủ đặc trưng để nhận ra một yêu
    cầu. Một bảng cho hai chiều là cách chắc nhất để chúng không lệch nhau.
    """

    haystack = _fold(text)
    return frozenset(trait for trait, cues in _FOLDED_TRAIT_CUES.items() if any(cue in haystack for cue in cues))
