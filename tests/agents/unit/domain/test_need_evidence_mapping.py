"""Bảng `NeedTag → EvidenceCode` — lát dọc đầu tiên: `URBAN_TRAFFIC`.

Bằng chứng từ prod 2026-08-28: bản LLM bị loại chứa `{CLAIM_PURPOSE}`,
`{CLAIM_CARGO_VOLUME_MAXIMUM_L}`, `{CAR_SEAT_COUNT}`. **LLM không bịa tính năng —
nó với tay tìm những claim chưa được duyệt.** Lỗi nằm ở hợp đồng planner ↔
synthesis, không ở prompt.

Bảng này là chỗ nối còn thiếu. Ba luật, mỗi luật một lý do riêng:

1. **`EvidenceCode` không chỉ là mã tính năng.** Code đã có ba nguồn: cờ tính
   năng (`BLIND_SPOT_MONITOR`), thông số (`FAST_CHARGE_TIME_MINUTES`), và số suy
   ra (`ENERGY_CONSUMPTION_KWH_PER_100KM` — `scoring.py` sinh). Ép cả ba vào một
   kiểu là sai từ đầu.
2. **Mỗi mã phải nói ra nó cần bằng chứng loại nào.** Không có nó thì tầng sau
   phải đoán, và đoán sai theo chiều "cho qua" là mở lại đúng cửa đang đóng.
3. **Trạng thái phải là `YES`.** `NO` và `UNKNOWN` không bao giờ được nói ra.
"""

from __future__ import annotations

import pytest

from src.agents.domain.need_evidence import (
    EvidenceKind,
    evidence_for_need,
    required_status_of,
)
from src.agents.domain.need_tags import NeedTag


def test_lat_doc_dau_tien_co_du_bang_chung_cho_di_lai_do_thi() -> None:
    """`URBAN_TRAFFIC` phải có ít nhất ba mã — đủ để lấp ô claim của bản dựng tay."""

    codes = evidence_for_need(NeedTag.URBAN_TRAFFIC)

    assert len(codes) >= 3


def test_moi_ma_deu_noi_ro_nguon_bang_chung() -> None:
    """Không mã nào được để tầng sau tự đoán nó là cờ hay thông số."""

    for code in evidence_for_need(NeedTag.URBAN_TRAFFIC):
        assert isinstance(code.kind, EvidenceKind)


def test_co_du_ba_loai_nguon_khong_ep_het_vao_co_tinh_nang() -> None:
    """`COMPACT_SIZE` là số SUY RA, không phải cờ trong `vehicle_feature_flags`."""

    kinds = {code.kind for code in evidence_for_need(NeedTag.URBAN_TRAFFIC)}

    assert EvidenceKind.FEATURE_FLAG in kinds
    assert EvidenceKind.DERIVED_METRIC in kinds


def test_chi_nhan_trang_thai_da_xac_minh() -> None:
    """`NO` và `UNKNOWN` không bao giờ được nói ra."""

    for code in evidence_for_need(NeedTag.URBAN_TRAFFIC):
        assert required_status_of(code) == "YES"


def test_moi_ma_mang_mot_chieu_loi_ich_de_khu_trung() -> None:
    """Cùng khoá khử trùng với `select_fallback_claims` — không dựng bảng thứ hai."""

    codes = evidence_for_need(NeedTag.URBAN_TRAFFIC)
    benefits = [code.benefit_code for code in codes]

    assert all(benefits)
    assert len(set(benefits)) >= 3, f"quá nhiều mã nói cùng một lợi ích: {benefits}"


def test_khong_co_nhan_nao_ngoai_tap_dong() -> None:
    """Bảng chỉ được nhận `NeedTag` — không có nhãn viết tự do.

    Test Phase 0 canh "năm nhãn còn lại chưa mở" đã hết vai khi Phase 1 mở chúng.
    Thay bằng cửa canh THẬT: tập nhãn là tập ĐÓNG, thêm nhãn ngoài nó là mở một
    đường cho chữ tự do đi vào chỗ chỉ được nhận mã đã duyệt.
    """

    from src.agents.domain.need_evidence import _BY_NEED

    assert set(_BY_NEED) <= set(NeedTag)


# ── Nối vào claim planner ────────────────────────────────────────────────────


def test_chi_mo_claim_khi_snapshot_co_bang_chung() -> None:
    """Nới claim plan KHÔNG có nghĩa là mở bừa.

    Đo trên prod 24h: 36/36 lần rơi bản dựng tay đều vì `suitability statement
    must use an approved claim placeholder` — claim plan quá hẹp. Nhưng cách sửa
    KHÔNG phải là cho qua: mỗi claim thêm vào phải có một thông số THẬT trong
    snapshot của chính lượt đó đỡ lưng.
    """

    from src.agents.domain.need_evidence import evidence_claims

    # Snapshot có thông số tiêu thụ điện ⇒ được nói về tiết kiệm điện.
    claims = evidence_claims({"ENERGY_CONSUMPTION_KWH_PER_100KM"})

    assert [claim.placeholder for claim in claims] == ["CLAIM_ENERGY_CONSUMPTION_KWH_PER_100KM"]


def test_snapshot_rong_thi_khong_them_claim_nao() -> None:
    """Không có số nào thì không có gì để nói."""

    from src.agents.domain.need_evidence import evidence_claims

    assert evidence_claims(set()) == ()


def test_khong_mo_claim_cho_ma_khong_co_trong_snapshot() -> None:
    """Có số tiêu thụ điện KHÔNG cho phép nói về sạc nhanh."""

    from src.agents.domain.need_evidence import evidence_claims

    codes = {claim.placeholder for claim in evidence_claims({"ENERGY_CONSUMPTION_KWH_PER_100KM"})}

    assert "CLAIM_FAST_CHARGING" not in codes


def test_claim_them_vao_mang_dung_chieu_loi_ich() -> None:
    """Dùng chung khoá khử trùng với `select_fallback_claims`."""

    from src.agents.domain.need_evidence import evidence_claims

    for claim in evidence_claims({"ENERGY_CONSUMPTION_KWH_PER_100KM"}):
        assert claim.slot
        assert claim.text


# ── Phase 1: mở đủ sáu nhãn ──────────────────────────────────────────────────


@pytest.mark.parametrize("tag", list(NeedTag))
def test_moi_nhan_deu_co_bang_chung(tag: NeedTag) -> None:
    """Phase 1 mở nốt năm nhãn Phase 0 cố ý để trống."""

    assert len(evidence_for_need(tag)) >= 3, f"{tag} chưa đủ bằng chứng"


@pytest.mark.parametrize("tag", list(NeedTag))
def test_moi_ma_co_tinh_nang_deu_co_that_trong_danh_muc(tag: NeedTag) -> None:
    """Mã không có thật thì claim sinh ra không bao giờ tra được bằng chứng.

    Sai kiểu này im lặng: câu vẫn viết ra, chỉ là không có gì đỡ lưng.
    """

    from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS

    for code in evidence_for_need(tag):
        if code.kind is EvidenceKind.FEATURE_FLAG:
            assert code.code in FEATURE_DISPLAY_LABELS, f"{tag}: mã lạ {code.code}"


@pytest.mark.parametrize("tag", list(NeedTag))
def test_khong_nhan_ma_khong_xe_nao_co(tag: NeedTag) -> None:
    """`HIGH_PAYLOAD` và `ECO_MODE` có 0 cờ `YES` trên dữ liệu thật.

    `need_tags.py` đã bỏ chúng khỏi `default_feature_codes` kèm ghi chú lý do.
    Bảng này phải theo cùng một quyết định, nếu không ta mở lại đúng cửa mà người
    trước đã đóng có căn cứ.
    """

    codes = {code.code for code in evidence_for_need(tag)}

    assert "HIGH_PAYLOAD" not in codes
    assert "ECO_MODE" not in codes


@pytest.mark.parametrize("tag", list(NeedTag))
def test_trong_mot_nhan_khong_hai_ma_noi_cung_loi_ich(tag: NeedTag) -> None:
    benefits = [code.benefit_code for code in evidence_for_need(tag)]

    assert len(benefits) == len(set(benefits)), f"{tag} trùng chiều: {benefits}"


def test_nhan_gia_dinh_uu_tien_cho_ngoi_va_an_toan_tre_em() -> None:
    """Không phải nhãn nào cũng cùng một bộ mã — mỗi nhãn phải nói đúng nhu cầu."""

    codes = {code.code for code in evidence_for_need(NeedTag.FAMILY_TRIP)}

    assert "7_SEATER" in codes
    assert "ISOFIX_ANCHORS" in codes


def test_nhan_di_xa_uu_tien_tam_chay_va_sac_nhanh() -> None:
    codes = {code.code for code in evidence_for_need(NeedTag.LONG_RANGE)}

    assert "HIGH_RANGE_BATTERY" in codes
    assert "FAST_CHARGING" in codes


def test_nhan_giao_hang_uu_tien_doi_pin() -> None:
    """Xe máy giao hàng chạy liên tục sống nhờ đổi pin nhanh tại trạm."""

    assert "BATTERY_SWAPPABLE" in {code.code for code in evidence_for_need(NeedTag.DELIVERY_LOAD)}
