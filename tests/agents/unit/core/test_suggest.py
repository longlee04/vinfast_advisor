"""Bảng gợi ý câu hỏi tiếp theo — thuần, tất định (spec Sếp chốt 2026-08-29)."""

from __future__ import annotations

import re

import pytest

from src.agents.core.actions import (
    Ask,
    Compare,
    Lookup,
    OnRoadPrice,
    Recommend,
    Reply,
    ShowroomOptions,
    Tco,
)
from src.agents.core.state import CoreState, Pending, PendingKind, Stage
from src.agents.core.suggest import MAX_SUGGESTIONS, OPENING, quick_replies

V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
NAMES = {V1: "VinFast VF 5", V2: "VinFast VF 6"}


def S(**kw) -> CoreState:  # noqa: N802 -- quy ước test S=CoreState
    return CoreState(session_id="s", **kw)


def _suggest(state: CoreState, action) -> tuple[str, ...]:
    return quick_replies(state, action, vehicle_names=NAMES)


def test_luot_dau_goi_y_cach_tra_loi() -> None:
    assert _suggest(S(), Ask(key="profile", kind=PendingKind.SLOT)) == OPENING


def test_sau_de_xuat_goi_y_theo_ten_xe_that() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2))
    items = _suggest(state, Recommend(reason="first"))
    assert items[0] == "Chọn VinFast VF 5"
    assert "So sánh VinFast VF 5 và VinFast VF 6" in items
    assert "Xem mẫu khác" in items


def test_de_xuat_mot_mau_thi_khong_goi_y_so_sanh() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=(V1,))
    assert not any(item.startswith("So sánh") for item in _suggest(state, Recommend()))


def test_ten_xe_tra_khong_ra_thi_bo_han_khong_doc_id() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("khong-co-trong-danh-ba",))
    items = _suggest(state, Recommend())
    assert items == ("Xem mẫu khác",)


def test_sau_khi_chon_xe_goi_y_bon_viec() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id=V1)
    items = _suggest(state, Reply(template="chosen_summary"))
    assert items == ("Tính chi phí sử dụng", "Giá lăn bánh", "Đặt lịch lái thử", "Có ưu đãi gì không?")


def test_sau_tco_goi_y_con_so_con_lai() -> None:
    state = S(stage=Stage.COSTING, chosen_vehicle_id=V1)
    assert "Giá lăn bánh" in _suggest(state, Tco(vehicle_id=V1))
    assert "Tính chi phí sử dụng" in _suggest(state, OnRoadPrice(vehicle_id=V1))


def test_dang_chon_khung_gio_thi_khong_them_goi_y_chu() -> None:
    state = S(stage=Stage.SCHEDULING, chosen_vehicle_id=V1)
    assert _suggest(state, ShowroomOptions(vehicle_id=V1)) == ()
    treo = S(
        stage=Stage.SCHEDULING, chosen_vehicle_id=V1, pending=Pending(kind=PendingKind.CHOICE, key="showroom_slot")
    )
    assert _suggest(treo, Reply(template="social")) == ()


def test_dang_cho_nguoi_that_chi_con_mot_loi() -> None:
    for stage in (Stage.OFFER_REVIEW, Stage.HANDED_OFF):
        assert _suggest(S(stage=stage, chosen_vehicle_id=V1), Reply(template="social")) == ("Hỏi thêm về xe",)


def test_chen_ngang_thi_goi_y_giup_tra_loi_cau_dang_treo() -> None:
    state = S(stage=Stage.COLLECTING, pending=Pending(kind=PendingKind.SLOT, key="profile"))
    assert _suggest(state, Lookup(mode="browse", resume_pending=True)) == OPENING


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (S(), Ask(key="profile", kind=PendingKind.SLOT)),
        (S(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2)), Recommend()),
        (S(stage=Stage.CHOSEN, chosen_vehicle_id=V1), Reply(template="chosen_summary")),
        (S(stage=Stage.COSTING, chosen_vehicle_id=V1), Tco(vehicle_id=V1)),
        (S(stage=Stage.HANDED_OFF), Reply(template="social")),
    ],
)
def test_moi_goi_y_deu_sach_va_khong_qua_tran(state: CoreState, action) -> None:
    items = _suggest(state, action)
    assert len(items) <= MAX_SUGGESTIONS
    for item in items:
        # `quick_replies` đã chạy `assert_clean`; khẳng định lại hình dạng ở đây
        # để một mã máy hay uuid lọt vào bảng là test đỏ ngay.
        assert not re.search(r"[A-Za-z0-9]+_[A-Za-z0-9_]+", item)
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", item)
        assert item == item.strip() and item


def test_trong_vong_chinh_thi_giu_vong_mo_va_giu_duong_lui() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2))
    items = _suggest(state, Recommend(reason="revised", refine="rẻ hơn"))
    assert items == ("Chọn VinFast VF 5", "Rẻ hơn nữa", "Xem lại mẫu trước")


# ---------- bước 4-5 mục 4: sau khi so sánh, gợi ý phải theo ĐÚNG hai mẫu vừa so ----------


def test_sau_so_sanh_goi_y_theo_hai_mau_vua_so() -> None:
    """Prod: bảng so sánh xong, khách nhận lại ba gợi ý mở đầu ("Ô tô khoảng 800
    triệu…") — đúng lúc họ chỉ còn một việc là chốt một trong hai mẫu."""

    state = S(recommended_ids=(V1, V2))
    items = _suggest(state, Compare(vehicle_ids=(V1, V2)))
    assert items == ("Chọn VinFast VF 5", "Chọn VinFast VF 6", "Tính chi phí VinFast VF 5", "Đặt lái thử VinFast VF 5")


def test_so_sanh_ma_tra_khong_ra_ten_thi_bo_han_khong_doc_id() -> None:
    state = S(recommended_ids=("khong-co-trong-danh-ba",))
    assert _suggest(state, Compare(vehicle_ids=("khong-co-trong-danh-ba",))) == ()


def test_so_sanh_chen_ngang_thi_van_nhuong_cho_cau_dang_treo() -> None:
    state = S(recommended_ids=(V1, V2), pending=Pending(kind=PendingKind.SLOT, key="profile"))
    assert _suggest(state, Compare(vehicle_ids=(V1, V2), resume_pending=True)) == OPENING


# ---------- [agent-migration Bước 6] Action OpenQuestion không làm vỡ bảng gợi ý ----------


def test_quick_replies_voi_open_question() -> None:
    """`OpenQuestion` rơi đúng nhánh mặc định theo chặng, không ném."""

    from src.agents.core.actions import OPEN_REASON_UNCLEAR, OpenQuestion

    action = OpenQuestion(question="tính năng nào hợp nhất", reason=OPEN_REASON_UNCLEAR)
    assert _suggest(S(stage=Stage.RECOMMENDED, recommended_ids=(V1, V2)), action)
    assert _suggest(S(), action) == OPENING
    assert _suggest(S(stage=Stage.CHOSEN, chosen_vehicle_id=V1), action)
