"""Máy trạng thái chặng sau khi đã đề xuất xe.

Chặng này có năm điểm dừng, mà cả hệ chỉ có một cờ `pending_question` nói được
"đang chờ trả lời" — không nói đang chờ trả lời CÁI GÌ. Khách gõ "không" có thể
là "không cần tính năng", "không còn băn khoăn", hay "không muốn lái thử", và ba
câu đó dẫn đi ba hướng khác hẳn nhau.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.agents.domain.post_pitch import (
    HITL_WAIT_LIMIT,
    MAX_HITL_ROUNDS,
    PostPitchStage,
    after_choice,
    after_concern,
    after_offer,
    chosen_vehicle,
    close,
    hitl_rounds,
    hitl_wait_expired,
    stage_of,
    start_after_pitch,
)

NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)


def test_chang_bat_dau_ngay_sau_ban_de_xuat() -> None:
    form = start_after_pitch()

    assert stage_of(form) is PostPitchStage.AWAITING_CHOICE
    assert hitl_rounds(form) == 0


def test_chon_mau_thi_sang_thang_cau_hoi_hai_loi() -> None:
    form = after_choice(start_after_pitch(), vehicle_name="VF 8 All New")

    assert stage_of(form) is PostPitchStage.AWAITING_DECISION
    assert chosen_vehicle(form) == "VF 8 All New"


def test_thieu_quang_duong_khong_con_lam_dung_luong() -> None:
    """Sếp 2026-08-26: bỏ chặng xin quãng đường.

    Đo trên VF 8, phần chi phí đổi theo quãng đường chiếm 2,4% tổng ở 20 km/ngày
    và 8,8% ở 80 km/ngày — hơn 91% con số đã biết trước khi khách nói gì. Dừng cả
    luồng để xin nó là trả một lượt hỏi-đáp cho chưa tới 9% độ chính xác; thay
    vào đó `nodes/tco` tính theo mốc mặc định và NÓI RA mốc đó.
    """

    form = after_choice(start_after_pitch(), vehicle_name="VF 3 All New")

    assert stage_of(form) is PostPitchStage.AWAITING_DECISION


def test_chang_cu_trong_db_van_doc_duoc() -> None:
    """`active_task_state` là JSON đã nằm trong DB prod.

    Đổi tên chặng mà không ánh xạ thì mọi phiên đang mở giữa chừng đọc ra `None`,
    chặng biến mất, và khách đang chờ đặt lịch bị bỏ giữa đường.
    """

    for cu in ("AWAITING_DISTANCE", "AWAITING_CONCERN", "AWAITING_TEST_DRIVE"):
        assert stage_of({"stage": cu}) is PostPitchStage.AWAITING_DECISION, cu
    assert stage_of({"stage": "GIA_TRI_LA"}) is None


def test_het_ban_khoan_thi_moi_lai_thu() -> None:
    form = after_choice(start_after_pitch(), vehicle_name="VF 8")

    moved = after_concern(form, has_concern=False, now=NOW)

    assert stage_of(moved) is PostPitchStage.AWAITING_DECISION
    assert hitl_rounds(moved) == 0


def test_con_ban_khoan_thi_qua_tu_van_vien_va_dem_vong() -> None:
    form = after_choice(start_after_pitch(), vehicle_name="VF 8")

    moved = after_concern(form, has_concern=True, now=NOW)

    assert stage_of(moved) is PostPitchStage.IN_HITL
    assert hitl_rounds(moved) == 1


def test_cap_uu_dai_xong_thi_quay_lai_moi_lai_thu() -> None:
    form = after_concern(
        after_choice(start_after_pitch(), vehicle_name="VF 8"),
        has_concern=True,
        now=NOW,
    )

    assert stage_of(after_offer(form)) is PostPitchStage.AWAITING_DECISION


def test_het_so_vong_thi_di_thang_lai_thu_khong_quay_nua() -> None:
    """Chặn vòng lặp `lăn tăn → tư vấn viên → ưu đãi → lái thử → lăn tăn → …`.
    Khách đã gặp tư vấn viên đủ số lần, quay thêm không giải quyết được gì."""

    form = after_choice(start_after_pitch(), vehicle_name="VF 8")
    for _ in range(MAX_HITL_ROUNDS):
        form = after_offer(after_concern(form, has_concern=True, now=NOW))

    assert hitl_rounds(form) == MAX_HITL_ROUNDS

    once_more = after_concern(form, has_concern=True, now=NOW)

    assert stage_of(once_more) is PostPitchStage.AWAITING_DECISION
    assert hitl_rounds(once_more) == MAX_HITL_ROUNDS


# ── Hạn chờ tư vấn viên ──────────────────────────────────────────────────────


def test_cho_qua_han_thi_luong_tu_di_tiep() -> None:
    """Tư vấn viên không online mà luồng đứng im là khách bị treo, và nhánh
    "quay về lái thử" không bao giờ chạy."""

    form = after_concern(
        after_choice(start_after_pitch(), vehicle_name="VF 8"),
        has_concern=True,
        now=NOW,
    )

    assert not hitl_wait_expired(form, now=NOW + HITL_WAIT_LIMIT - timedelta(minutes=1))
    assert hitl_wait_expired(form, now=NOW + HITL_WAIT_LIMIT + timedelta(minutes=1))


def test_chua_vao_hang_doi_thi_khong_the_qua_han() -> None:
    form = after_choice(start_after_pitch(), vehicle_name="VF 8")

    assert not hitl_wait_expired(form, now=NOW + timedelta(days=1))


@pytest.mark.parametrize("broken", [{"stage": "IN_HITL"}, {"stage": "IN_HITL", "hitl_since": "khong-phai-ngay"}])
def test_moc_cho_hong_thi_coi_nhu_chua_qua_han(broken: dict) -> None:
    """Chiều an toàn: kết luận "quá hạn" từ một giá trị hỏng là cắt ngang một
    cuộc trao đổi đang diễn ra thật."""

    assert not hitl_wait_expired(broken, now=NOW + timedelta(days=1))


# ── Dữ liệu cũ / hỏng không được làm vỡ lượt ─────────────────────────────────


@pytest.mark.parametrize("form", [None, {}, {"stage": "MOT_CHANG_KHONG_TON_TAI"}, {"stage": 7}])
def test_form_la_hoac_rong_thi_khong_co_chang_nao(form: object) -> None:
    """`form` là JSON đọc từ DB, có thể do một bản cũ ghi. Vỡ ở đây là vỡ cả lượt
    của khách vì một giá trị lịch sử."""

    assert stage_of(form) is None
    assert chosen_vehicle(form) is None
    assert hitl_rounds(form) == 0


def test_dong_chang() -> None:
    assert stage_of(close(start_after_pitch())) is PostPitchStage.DONE
