"""Điểm mỗi xe HƠN HẲN những xe còn lại trong cùng một lượt đề xuất.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

**Bệnh đang chữa** (Sếp 2026-08-27: *"văn của LLM sinh ra cho các đối tượng khác
giống nhau"*). Bản pitch thật lấy từ prod:

    **VinFast VF 8 All New** thuộc đúng dòng xe Quý khách đang tìm, với tầm vận
    hành thoải mái cho quãng đường mỗi ngày và đủ chỗ cho số người Quý khách
    thường chở. Ngoài ra xe còn được trang bị điều hòa tự động chia vùng…

    **VinFast VF 7 All New** thuộc đúng dòng xe Quý khách đang tìm, với tầm vận
    hành thoải mái cho quãng đường mỗi ngày và đủ chỗ cho số người Quý khách
    thường chở. Ngoài ra xe còn được trang bị móc gắn ghế trẻ em ISOFIX…

Giống nhau tới từng chữ, trừ cái tên và tính năng cuối. Và đó KHÔNG phải lỗi
prompt: `claim_policy._CLAIM_TEXT_BY_SLOT` đánh khoá theo SLOT, nên hai xe cùng
thoả `vehicle_type` + `required_range_km` + `passenger_count` nhận đúng ba câu
như nhau. Mô hình chỉ được phép sắp xếp lại những câu đã duyệt, nên bảo nó "viết
đa dạng hơn" là bảo nó bịa.

**Cách chữa.** Cho mỗi xe một câu nói về chỗ nó HƠN những xe đứng cạnh trong
chính lượt đó. So sánh nội bộ nên luôn đúng theo dựng: số lấy thẳng từ snapshot
của lượt, và câu chữ không mang chữ số nào nên guardrail A6-1 không có gì để đối
chiếu sai.

Đây cũng là điều một tư vấn viên thật làm: đứng trước ba xe cùng vừa túi tiền,
họ không đọc lại ba lần cùng một lý do, họ nói chiếc này cốp to hơn, chiếc kia đi
xa hơn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from uuid import UUID

from src.agents.domain.claim_policy import PlannedClaim


class _Fact(Protocol):
    """Đúng phần `SynthesisFact` mà module này đọc."""

    @property
    def fact_code(self) -> str: ...

    @property
    def value_text(self) -> str | None: ...


#: (mã fact, càng-lớn-càng-thắng, câu chữ).
#:
#: Thứ tự là THỨ TỰ ƯU TIÊN: mỗi xe chỉ được một câu, và nó lấy luật đầu tiên mà
#: xe đó thắng. Quãng đường đứng trước vì đó là con số khách hỏi nhiều nhất.
#:
#: Ba ràng buộc cứng của `services/synthesis` áp cho từng câu, y như
#: `_CLAIM_TEXT_BY_SLOT`:
#: - KHÔNG chữ số (`_reject_digits_outside_placeholders`);
#: - KHÔNG cụm tán dương mơ hồ (`UNSTRUCTURED_CLAIM_PATTERN`: "phù hợp", "lý
#:   tưởng", "vượt trội", "hàng đầu"…);
#: - KHÔNG cụm cảm quan chưa được cấp phép (`perceptual_traits._TRAIT_CUES`).
#:
#: Vì ràng buộc thứ ba mà câu công suất viết "công suất động cơ lớn nhất" chứ
#: không viết "động cơ mạnh nhất" — "động cơ mạnh" là cue của `TRAIT_STRONG_MOTOR`
#: và chỉ xe qua ngưỡng mới được nói.
#:
#: Giá KHÔNG có mặt: `quote_risk` đọc cụm "giá thấp" như một tín hiệu thương
#: lượng, và nhãn lệch ngân sách (`claim_policy.budget_fit_note`) đã nói phần đó
#: ngay trên thẻ xe rồi.
_STANDOUT_RULES: Final[tuple[tuple[str, bool, str], ...]] = (
    ("CAR_RANGE_KM", True, "đi được xa nhất trong nhóm em vừa chọn"),
    ("MOTORBIKE_RANGE_MAX_KM", True, "đi được xa nhất trong nhóm em vừa chọn"),
    ("CARGO_VOLUME_STANDARD_L", True, "có khoang hành lý lớn nhất trong nhóm em vừa chọn"),
    ("CAR_SEAT_COUNT", True, "chở được nhiều người nhất trong nhóm em vừa chọn"),
    ("MOTORBIKE_MAX_LOAD_KG", True, "chở được nặng nhất trong nhóm em vừa chọn"),
    ("CAR_MOTOR_POWER_KW", True, "có công suất động cơ lớn nhất trong nhóm em vừa chọn"),
    ("FAST_CHARGE_TIME_MINUTES", False, "sạc nhanh nhất trong nhóm em vừa chọn"),
)

#: Khoá placeholder của câu này. Hậu tố KHÔNG được trùng một mã tính năng nào:
#: `claim_policy.approved_feature_codes` suy mã đã duyệt từ chính hậu tố khoá, nên
#: một hậu tố trùng mã sẽ cấp phép cho lời khẳng định tính năng mà xe chưa có căn cứ.
STANDOUT_PLACEHOLDER: Final[str] = "CLAIM_STANDOUT"

#: Dưới hai xe thì không có "nhóm" nào để hơn. Một câu so sánh nhất giữa một
#: mình là câu nói thật mà vô nghĩa — và nghe như tự khen.
_MIN_GROUP_SIZE: Final[int] = 2


def standout_claims(
    facts_by_vehicle: Mapping[UUID, Sequence[_Fact]],
) -> dict[UUID, PlannedClaim]:
    """Mỗi xe → câu nói về chỗ nó hơn hẳn phần còn lại, hoặc không có mục nào.

    Xe không thắng luật nào thì KHÔNG có mặt trong kết quả: thà thiếu một câu còn
    hơn dựng một hạng mục chỉ để mọi xe đều có huy chương.

    Hoà thì KHÔNG ai thắng. Hai xe cùng 5 chỗ mà một chiếc được xưng "chở được
    nhiều người nhất" là nói sai, và sai theo kiểu khách kiểm tra được ngay trên
    chính thẻ xe bên cạnh.
    """

    if len(facts_by_vehicle) < _MIN_GROUP_SIZE:
        return {}
    claimed: dict[UUID, PlannedClaim] = {}
    for fact_code, higher_is_better, text in _STANDOUT_RULES:
        values = _values_for(facts_by_vehicle, fact_code)
        if len(values) < _MIN_GROUP_SIZE:
            continue
        best = max(values.values()) if higher_is_better else min(values.values())
        winners = [vehicle_id for vehicle_id, value in values.items() if value == best]
        if len(winners) != 1:
            continue
        winner = winners[0]
        if winner in claimed:
            continue
        claimed[winner] = PlannedClaim(
            placeholder=STANDOUT_PLACEHOLDER,
            slot="standout",
            text=text,
        )
    return claimed


def _values_for(
    facts_by_vehicle: Mapping[UUID, Sequence[_Fact]],
    fact_code: str,
) -> dict[UUID, Decimal]:
    """Giá trị số của một mã fact, chỉ những xe THẬT SỰ có nó.

    Xe thiếu số thì vắng mặt chứ không nhận 0: coi thiếu là 0 sẽ trao giải "sạc
    nhanh nhất" cho đúng chiếc không có dữ liệu sạc nhanh.
    """

    values: dict[UUID, Decimal] = {}
    for vehicle_id, facts in facts_by_vehicle.items():
        for fact in facts:
            if fact.fact_code != fact_code:
                continue
            parsed = _as_decimal(fact.value_text)
            if parsed is not None:
                values[vehicle_id] = parsed
            break
    return values


def _as_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


__all__ = ["STANDOUT_PLACEHOLDER", "standout_claims"]
