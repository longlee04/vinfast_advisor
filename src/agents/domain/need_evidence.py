"""Bảng `NeedTag → EvidenceCode` — chỗ nối còn thiếu giữa planner và synthesis.

BẰNG CHỨNG từ prod 2026-08-28: bản LLM bị loại chứa `{CLAIM_PURPOSE}`,
`{CLAIM_CARGO_VOLUME_MAXIMUM_L}`, `{CAR_SEAT_COUNT}`, và cả hai bộ viết đều trượt
với `suitability statement must use an approved claim placeholder`.

**LLM không bịa tính năng — nó với tay tìm những claim chưa được duyệt.** Nên lỗi
nằm ở hợp đồng planner ↔ synthesis, không ở prompt. Siết prompt thêm không đổi
được gì; mở đúng claim có bằng chứng thì mới đổi.

Vì sao `EvidenceCode` KHÔNG chỉ là mã tính năng
------------------------------------------------
Code đã có sẵn BA nguồn bằng chứng khác nhau, ép cả ba vào một kiểu là sai từ
đầu:

- cờ tính năng — `BLIND_SPOT_MONITOR`, đọc `vehicle_feature_flags.status`
- thông số — `FAST_CHARGE_TIME_MINUTES`, xem `claim_policy._FACT_BACKED_FEATURE_CODES`
- số suy ra — `ENERGY_CONSUMPTION_KWH_PER_100KM`, do `scoring.py` sinh

`COMPACT_SIZE` thuộc nhóm thứ ba: không có cờ nào tên vậy trong danh mục.

Phạm vi
-------
Phase 0 mở một lát dọc `URBAN_TRAFFIC` để chứng minh hợp đồng planner ↔ synthesis
chạy. Phase 1 mở nốt năm nhãn còn lại.

Mã tính năng lấy từ danh mục THẬT (`prompts/feature_askable.FEATURE_DISPLAY_LABELS`,
28 mã) — có test canh, vì một mã không có thật thì claim sinh ra không bao giờ
tra được bằng chứng, và sai kiểu đó im lặng: câu vẫn viết ra, chỉ là không có gì
đỡ lưng.

`HIGH_PAYLOAD` và `ECO_MODE` KHÔNG được dùng: `need_tags.py` đã bỏ chúng khỏi
`default_feature_codes` vì **0 cờ `YES`** trên dữ liệu thật, có ghi chú lý do.
Bảng này theo cùng quyết định đó — mở lại là mở lại đúng cửa người trước đã đóng
có căn cứ.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.claim_policy import _CLAIM_TEXT_BY_SLOT, PlannedClaim
from src.agents.domain.need_tags import NeedTag


class EvidenceKind(StrEnum):
    """Bằng chứng đến từ đâu — quyết định tầng sau đi tra ở bảng nào."""

    #: `vehicle_feature_flags.status`
    FEATURE_FLAG = "FEATURE_FLAG"
    #: Thông số trong snapshot của lượt.
    FACT = "FACT"
    #: Số do `scoring` suy ra từ thông số, không có cột riêng trong danh mục.
    DERIVED_METRIC = "DERIVED_METRIC"


@dataclass(frozen=True, slots=True)
class EvidenceCode:
    """Một mã bằng chứng, kèm nguồn và CHIỀU LỢI ÍCH nó nói tới.

    `benefit_code` dùng chung khoá khử trùng với
    `synthesis.select_fallback_claims`: hai mã cùng chiều là hai cách nói một
    điều, và nói hai lần chỉ dài hơn chứ không thuyết phục hơn.
    """

    code: str
    kind: EvidenceKind
    benefit_code: str


#: Lát dọc đầu tiên. Mỗi mã một CHIỀU LỢI ÍCH khác nhau — không có hai mã cùng
#: nói "an toàn" hay cùng nói "tiết kiệm".
_URBAN_TRAFFIC: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("BLIND_SPOT_MONITOR", EvidenceKind.FEATURE_FLAG, "quan_sat_an_toan"),
    EvidenceCode("SMARTPHONE_MIRRORING", EvidenceKind.FEATURE_FLAG, "ket_noi_dien_thoai"),
    EvidenceCode("FAST_CHARGING", EvidenceKind.FACT, "thoi_gian_sac"),
    EvidenceCode("ENERGY_CONSUMPTION_KWH_PER_100KM", EvidenceKind.DERIVED_METRIC, "tiet_kiem_dien"),
    EvidenceCode("COMPACT_SIZE", EvidenceKind.DERIVED_METRIC, "de_xoay_so_trong_pho"),
)

#: Chở gia đình đi chơi: đủ chỗ, trẻ em ngồi an toàn, khoang rộng, cả xe dễ chịu.
_FAMILY_TRIP: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("7_SEATER", EvidenceKind.FEATURE_FLAG, "cho_ngoi"),
    EvidenceCode("ISOFIX_ANCHORS", EvidenceKind.FEATURE_FLAG, "an_toan_tre_em"),
    EvidenceCode("PANORAMIC_ROOF", EvidenceKind.FEATURE_FLAG, "khong_gian_khoang"),
    EvidenceCode("MULTI_ZONE_AC", EvidenceKind.FEATURE_FLAG, "dieu_hoa_hanh_khach"),
)

#: Đi tỉnh, về quê: đi được xa, sạc lại nhanh, đỡ mỏi trên đường trường.
_LONG_RANGE: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("HIGH_RANGE_BATTERY", EvidenceKind.FEATURE_FLAG, "tam_chay"),
    EvidenceCode("FAST_CHARGING", EvidenceKind.FACT, "thoi_gian_sac"),
    EvidenceCode("ADAS_SUITE", EvidenceKind.FEATURE_FLAG, "ho_tro_lai_duong_dai"),
    EvidenceCode("MOBILE_APP", EvidenceKind.FEATURE_FLAG, "theo_doi_hanh_trinh"),
)

#: Giao hàng, chạy dịch vụ: chạy liên tục nên sống nhờ đổi pin, và xe hay đứng
#: ngoài đường nên chống trộm là nhu cầu thật, không phải tiện nghi.
_DELIVERY_LOAD: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("BATTERY_SWAPPABLE", EvidenceKind.FEATURE_FLAG, "doi_pin_nhanh"),
    EvidenceCode("ANTI_THEFT", EvidenceKind.FEATURE_FLAG, "chong_trom"),
    EvidenceCode("MOBILE_APP", EvidenceKind.FEATURE_FLAG, "theo_doi_hanh_trinh"),
    EvidenceCode("GPS", EvidenceKind.FEATURE_FLAG, "dinh_vi"),
)

#: Giảm chi phí hằng tháng: tốn ít điện, sạc được chỗ rẻ, sạc xong tự ngắt.
_ECO_SAVING: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("ENERGY_CONSUMPTION_KWH_PER_100KM", EvidenceKind.DERIVED_METRIC, "tiet_kiem_dien"),
    EvidenceCode("BATTERY_REMOVABLE", EvidenceKind.FEATURE_FLAG, "sac_noi_gia_re"),
    EvidenceCode("AUTO_SHUTOFF_CHARGER", EvidenceKind.FEATURE_FLAG, "an_toan_khi_sac"),
    EvidenceCode("MOBILE_APP", EvidenceKind.FEATURE_FLAG, "theo_doi_hanh_trinh"),
)

#: Ưu tiên tiện nghi khoang xe.
_PREMIUM_COMFORT: Final[tuple[EvidenceCode, ...]] = (
    EvidenceCode("LEATHER_SEATS", EvidenceKind.FEATURE_FLAG, "chat_lieu_ghe"),
    EvidenceCode("VENTILATED_SEATS", EvidenceKind.FEATURE_FLAG, "thong_gio_ghe"),
    EvidenceCode("PANORAMIC_ROOF", EvidenceKind.FEATURE_FLAG, "khong_gian_khoang"),
    EvidenceCode("ADAS_SUITE", EvidenceKind.FEATURE_FLAG, "ho_tro_lai_duong_dai"),
)

_BY_NEED: Final[dict[NeedTag, tuple[EvidenceCode, ...]]] = {
    NeedTag.URBAN_TRAFFIC: _URBAN_TRAFFIC,
    NeedTag.FAMILY_TRIP: _FAMILY_TRIP,
    NeedTag.LONG_RANGE: _LONG_RANGE,
    NeedTag.DELIVERY_LOAD: _DELIVERY_LOAD,
    NeedTag.ECO_SAVING: _ECO_SAVING,
    NeedTag.PREMIUM_COMFORT: _PREMIUM_COMFORT,
}


def evidence_for_need(tag: NeedTag) -> tuple[EvidenceCode, ...]:
    """Các mã bằng chứng phục vụ một nhãn nhu cầu; rỗng khi chưa mở nhãn đó."""

    return _BY_NEED.get(tag, ())


def evidence_claims(fact_codes: Collection[str]) -> tuple[PlannedClaim, ...]:
    """Claim MỞ THÊM cho lượt này, mỗi claim có một thông số thật đỡ lưng.

    Đo trên prod 24h (2026-08-28): **36/36** lần rơi bản dựng tay đều vì
    `suitability statement must use an approved claim placeholder`. Claim plan
    sinh từ `plan_claims(recommendation.reasons)`, mà lý do chấm điểm không phủ
    hết những gì xe THẬT SỰ có — nên mô hình với tay tìm claim chưa được duyệt và
    bị loại.

    Cách sửa KHÔNG phải cho qua. Mỗi claim thêm vào đây phải có mã của nó nằm
    trong `fact_codes` — tức trong snapshot của CHÍNH lượt đó. Không có số thì
    không có gì để nói, và im lặng vẫn tốt hơn một câu không có căn cứ.

    Chỉ nhận mã thuộc nhóm `FACT`/`DERIVED_METRIC`: cờ tính năng đã có đường
    riêng qua `plan_claims`, và mở hai đường cho một thứ là mở một chỗ để lệch.
    """

    present = set(fact_codes)
    claims: list[PlannedClaim] = []
    seen_benefits: set[str] = set()
    for codes in _BY_NEED.values():
        for code in codes:
            if code.kind is EvidenceKind.FEATURE_FLAG or code.code not in present:
                continue
            text = _CLAIM_TEXT_BY_SLOT.get(code.code)
            if text is None or code.benefit_code in seen_benefits:
                continue
            seen_benefits.add(code.benefit_code)
            claims.append(PlannedClaim(placeholder=f"CLAIM_{code.code}", slot=code.code, text=text))
    return tuple(claims)


def required_status_of(code: EvidenceCode) -> str:
    """Trạng thái tối thiểu để được nói ra.

    Luôn là `YES`. Hàm tồn tại để chỗ gọi KHÔNG tự viết chuỗi `"YES"` rải rác —
    ngày nào cần nới cho một loại bằng chứng nào đó thì chỉ có một chỗ để sửa,
    và chỗ đó có test canh.
    """

    del code
    return "YES"
