"""Bảng quyết định lõi v2 — case lấy thẳng từ 34 phiên prod đã gán nhãn 2026-08-29.

Ba nhóm đầu tương ứng ba chỉ số thắng/thua ở spec mục 8.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.core.actions import (
    REASON_REVISED,
    TEMPLATE_CHOSEN_SUMMARY,
    Ask,
    Book,
    EnqueueHitl,
    FitCheck,
    Handoff,
    Lookup,
    Nearby,
    NextSteps,
    OnRoadPrice,
    Recommend,
    Reply,
    ScopeNote,
    ShowroomOptions,
    Silent,
    Tco,
    VehicleQa,
)
from src.agents.core.policy import MAX_ASKS, decide
from src.agents.core.state import (
    UNCLEAR_UNDERSTANDING,
    CoreState,
    Pending,
    Stage,
    Understanding,
)
from src.agents.core.state import (
    DialogueAct as A,
)
from src.agents.core.state import (
    Intent as I,  # noqa: N817 -- quy ước test I=Intent trong brief
)
from src.agents.core.state import (
    PendingKind as K,
)
from src.agents.domain.values import SlotName as N


def S(**kw: Any) -> CoreState:  # noqa: N802 -- quy ước test S=CoreState trong brief
    return CoreState(session_id="s", **kw)


def U(act: A, intent: I = I.NONE, **kw: Any) -> Understanding:  # noqa: N802 -- quy ước test U=Understanding trong brief
    return Understanding(dialogue_act=act, intent=intent, **kw)


CAR_FULL = {N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 1_000_000_000, N.PURPOSE: "đi làm", N.PASSENGER_COUNT: 5}
ASK_VT = Pending(kind=K.SLOT, key="vehicle_type")
#: Câu hỏi DUY NHẤT của luồng tư vấn từ 2026-08-29 (Sếp chốt): ngân sách + mục
#: đích + thói quen trong một câu, trả lời xong là đề xuất luôn.
ASK_PROFILE = Pending(kind=K.SLOT, key="profile")
ASK_PURPOSE = Pending(kind=K.SLOT, key="purpose", options=("đi làm", "giao hàng", "đi cá nhân"))
ASK_FEAT = Pending(kind=K.SLOT, key="habit_need_tags", options=("ADAS", "BLUETOOTH"))
ASK_CHOICE = Pending(kind=K.CHOICE, key="vehicle", options=("v1", "v2", "v3"))


# ---------- Nhóm 1: trả lời loại xe KHÔNG được đổ catalog (cũ 175/188) ----------


def test_o_to_dien_sau_muon_tu_van_la_slot_answer_khong_browse() -> None:
    # 2026-08-29: câu trả lời cho câu hồ sơ chỉ mang MỖI loại xe vẫn là câu trả
    # lời — không bao giờ là `Lookup(browse)`.
    # Bước 6: biết MỖI loại xe thì chưa có gì để lọc ngoài chính loại đó, nên
    # giữ câu hồ sơ (`act` bày danh sách của loại ấy ngay trong cùng tin nhắn).
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.VEHICLE_TYPE: "CAR"}))
    assert not isinstance(d.action, Lookup)
    assert isinstance(d.action, Ask) and d.action.key == "profile"
    assert d.state_after.slots[N.VEHICLE_TYPE] == "CAR"
    assert d.state_after.pending is not None and d.state_after.pending.key == "profile"


def test_llm_gan_nham_browse_nhung_dang_co_pending_van_la_tra_loi() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE)
    d = decide(state, U(A.SLOT_ANSWER, intent=I.CATALOG_BROWSE, slots={N.VEHICLE_TYPE: "CAR"}))
    assert not isinstance(d.action, Lookup)
    assert d.state_after.intent is I.ADVISORY


def test_browse_that_su_khi_khong_pending() -> None:
    d = decide(S(), U(A.REQUEST, intent=I.CATALOG_BROWSE))
    assert d.action == Lookup(mode="browse")


@pytest.mark.parametrize("act", [A.REQUEST, A.INTERRUPT])
def test_browse_kem_loai_xe_khi_dang_treo_cau_hoi_la_tra_loi(act: A) -> None:
    # C2: "ô tô điện" bị LLM gắn REQUEST/INTERRUPT + CATALOG_BROWSE trong lúc đang
    # treo câu hỏi vẫn là câu TRẢ LỜI — không bao giờ đổ catalog.
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE)
    d = decide(state, U(act, intent=I.CATALOG_BROWSE, slots={N.VEHICLE_TYPE: "CAR"}))
    assert not isinstance(d.action, Lookup)
    assert isinstance(d.action, Ask) and d.action.key == "profile"
    assert d.state_after.slots[N.VEHICLE_TYPE] == "CAR"


@pytest.mark.parametrize("act", [A.REQUEST, A.INTERRUPT])
def test_browse_khong_kem_slot_khi_dang_treo_thi_hoi_lai_cau_cu(act: A) -> None:
    # C2: không có loại xe đi kèm thì hỏi lại đúng câu đang treo, vẫn không đổ catalog.
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PURPOSE)
    d = decide(state, U(act, intent=I.CATALOG_BROWSE))
    assert not isinstance(d.action, Lookup)
    assert isinstance(d.action, Ask)
    assert (d.action.key, d.action.kind, d.action.options) == (ASK_PURPOSE.key, ASK_PURPOSE.kind, ASK_PURPOSE.options)
    assert d.state_after.pending == ASK_PURPOSE
    assert d.state_after.ask_counts["purpose"] == 1


@pytest.mark.parametrize("act", [A.REQUEST, A.INTERRUPT])
def test_dang_treo_chon_mau_ma_khach_xin_danh_sach_thi_bay_danh_muc(act: A) -> None:
    """Prod benchmark2 2026-08-30: bot hỏi "mẫu nào?", khách đáp "thế em có loại
    nào" → `CATALOG_BROWSE`. Câu treo là CHỌN MẪU, mà khách xin danh sách mẫu:
    bày danh mục CHÍNH LÀ trả lời câu treo, hỏi lại y nguyên câu cũ là vòng lặp
    (ask_counts vehicle=2 rồi chuyển TVV cho một câu hỏi rất hợp lý)."""

    state = S(stage=Stage.COLLECTING, intent=I.CATALOG_LOOKUP, pending=ASK_CHOICE, ask_counts={"vehicle": 1})
    d = decide(state, U(act, intent=I.CATALOG_BROWSE))
    assert isinstance(d.action, Lookup) and d.action.mode == "browse"
    assert d.action.resume_pending is False
    assert d.state_after.pending is None
    assert d.state_after.ask_counts.get("vehicle", 0) == 1


def test_hoi_lai_khi_browse_qua_tran_thi_chuyen_tvv() -> None:
    # C2 + trần hỏi: hỏi lại cũng ĐẾM như một lượt hỏi, quá `MAX_ASKS` thì chuyển
    # TVV — nếu không, LLM cứ gán CATALOG_BROWSE là lõi hỏi lại mãi.
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PURPOSE, ask_counts={"purpose": MAX_ASKS})
    d = decide(state, U(A.REQUEST, intent=I.CATALOG_BROWSE))
    assert d.action == Handoff()
    assert d.state_after.stage is Stage.HANDED_OFF


# ---------- Nhóm 2: câu trả lời ngay sau bot hỏi KHÔNG bị từ chối (cũ 36 lượt) ----------


def test_di_lam_thoi_la_slot_answer() -> None:
    state = S(
        stage=Stage.COLLECTING,
        intent=I.ADVISORY,
        pending=ASK_PURPOSE,
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 500_000_000},
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.PURPOSE: "đi làm"}))
    # Không bị từ chối, và không hỏi thêm slot nào nữa: đủ để đề xuất.
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots[N.PURPOSE] == "đi làm"


def test_thoi_khong_voi_cau_hoi_feature_la_de_xuat_luon() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_FEAT, slots=CAR_FULL)
    d = decide(state, U(A.REJECT))
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots[N.HABIT_NEED_TAGS] == []
    assert d.state_after.pending is None


def test_co_tat_ca_lay_moi_option() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_FEAT, slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, features_all=True))
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots[N.HABIT_NEED_TAGS] == ["ADAS", "BLUETOOTH"]


def test_co_tat_ca_nhung_pending_chua_co_option_thi_rong() -> None:
    # finding 6: policy không biết danh mục tính năng — pending do policy tự tạo
    # (_advise) luôn có options=(); "có tất cả" lúc đó nghĩa là không chọn gì.
    pending_rong = Pending(kind=K.SLOT, key="habit_need_tags")
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=pending_rong, slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, features_all=True))
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots[N.HABIT_NEED_TAGS] == []


def test_gia_hoi_cao_o_chosen_khong_tu_choi() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY, question="giá hơi cao"))
    assert isinstance(d.action, Recommend)
    assert d.state_after.stage is Stage.RECOMMENDED


def test_social_giu_nguyen_pending_va_noi_lai() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PURPOSE)
    d = decide(state, U(A.SOCIAL))
    assert d.action == Reply(template="social", args={"stage": "COLLECTING"}, resume_pending=True)
    assert d.state_after.pending == ASK_PURPOSE
    assert d.state_after.stage is Stage.COLLECTING


def test_social_cung_reset_dem_unclear() -> None:
    # finding 4: SOCIAL không phải UNCLEAR — phải reset đếm như mọi act khác.
    state = S(stage=Stage.RECOMMENDED, ask_counts={"__unclear__": 2})
    d = decide(state, U(A.SOCIAL))
    assert "__unclear__" not in d.state_after.ask_counts


# ---------- Nhóm 3: sau đề xuất KHÔNG đọc lại bài (cũ 27 lượt) ----------


def test_sac_bao_lau_o_chosen_la_vehicle_qa() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.VEHICLE_QA, question="xe này sạc đầy mất bao lâu"))
    assert d.action == VehicleQa(vehicle_id="v1", question="xe này sạc đầy mất bao lâu")
    assert d.state_after.stage is Stage.CHOSEN


def test_vehicle_qa_o_recommended_lay_xe_dau_tien() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.VEHICLE_QA, question="tầm chạy bao xa"))
    assert d.action == VehicleQa(vehicle_id="v1", question="tầm chạy bao xa")


def test_vehicle_qa_o_collecting_hoi_mau_nao() -> None:
    d = decide(S(stage=Stage.COLLECTING), U(A.REQUEST, intent=I.VEHICLE_QA, question="sạc bao lâu"))
    assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE


def test_them_slot_sau_de_xuat_de_xuat_lai_khong_lap() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1",), slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REQUIRED_RANGE_KM: 80, N.REGISTRATION_PROVINCE: "HN"}))
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots[N.REQUIRED_RANGE_KM] == 80


def test_tinh_gia_lan_banh_o_chosen() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    d = decide(state, U(A.REQUEST, intent=I.ON_ROAD_PRICE))
    assert d.action == OnRoadPrice(vehicle_id="v1")


def test_tinh_chi_phi_thieu_km_van_tinh_luon() -> None:
    # 2026-08-29: không hỏi số km nữa — `act._tco` tạm tính mức mặc định và nói
    # rõ mức đó trong câu trả lời.
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 900_000_000})
    d = decide(state, U(A.REQUEST, intent=I.COST))
    assert d.action == Tco(vehicle_id="v1")


def test_tinh_chi_phi_du_thi_tco() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots={**CAR_FULL, N.REQUIRED_RANGE_KM: 30})
    d = decide(state, U(A.REQUEST, intent=I.COST))
    assert d.action == Tco(vehicle_id="v1")
    assert d.state_after.stage is Stage.COSTING


def test_khuyen_mai_o_chosen_vao_hitl() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.OFFER, confidence=0.9))
    assert d.action == EnqueueHitl(vehicle_id="v1")
    assert d.state_after.stage is Stage.OFFER_REVIEW


# ---------- Chọn xe ----------


def test_chon_mau_dau_tien() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"), pending=ASK_CHOICE)
    d = decide(state, U(A.CHOICE, choice_ref="v1"))
    assert d.action == Reply(template="chosen_summary", args={"vehicle_id": "v1"})
    assert d.state_after.chosen_vehicle_id == "v1"
    assert d.state_after.stage is Stage.CHOSEN
    assert d.state_after.pending is None


def test_toi_chon_vf5_khong_pending_van_chon_duoc() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"))
    d = decide(state, U(A.CHOICE, vehicle_ids=("v2",)))
    assert d.state_after.chosen_vehicle_id == "v2"
    assert d.state_after.stage is Stage.CHOSEN


def test_chon_lai_xe_khac_o_chosen() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", recommended_ids=("v1", "v2"))
    d = decide(state, U(A.CHOICE, vehicle_ids=("v2",)))
    assert d.state_after.chosen_vehicle_id == "v2"


def test_choice_khong_tro_duoc_thi_hoi_lai() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1",))
    d = decide(state, U(A.CHOICE, choice_ref=None))
    assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE


def test_chon_xe_kem_slot_khong_bi_nuot() -> None:
    # finding 2: CHOICE kèm slot (vd "chọn VF5, ngân sách 800tr") không được bỏ qua slot đó.
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"))
    d = decide(state, U(A.CHOICE, vehicle_ids=("v2",), slots={N.BUDGET_MAX_VND: 800_000_000}))
    assert d.state_after.slots[N.BUDGET_MAX_VND] == 800_000_000


def test_choice_khi_dang_cho_slot_cung_giu_slot_di_kem() -> None:
    # fix round 2/5: CHOICE tới đúng lúc đang treo một câu hỏi SLOT (khác CHOICE) vẫn
    # phải giữ slot đi kèm — trước đó nhánh này gọi _choose() không qua _merge_slots.
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"), pending=ASK_PURPOSE)
    d = decide(state, U(A.CHOICE, vehicle_ids=("v2",), slots={N.BUDGET_MAX_VND: 800_000_000}))
    assert d.state_after.slots[N.BUDGET_MAX_VND] == 800_000_000
    assert d.state_after.chosen_vehicle_id == "v2"
    assert d.state_after.pending is None


# ---------- Chen ngang giữ pending ----------


def test_tra_cuu_chen_ngang_giu_pending() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PURPOSE)
    d = decide(state, U(A.INTERRUPT, intent=I.CATALOG_LOOKUP, vehicle_ids=("v9",)))
    assert d.action == Lookup(mode="lookup", vehicle_ids=("v9",), resume_pending=True)
    assert d.state_after.pending == ASK_PURPOSE
    assert d.state_after.intent is I.ADVISORY


def test_so_sanh_chen_ngang() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, pending=ASK_CHOICE)
    d = decide(state, U(A.REQUEST, intent=I.COMPARE, vehicle_ids=("v1", "v2")))
    assert d.action.__class__.__name__ == "Compare"
    assert d.action.resume_pending is True


def test_tim_showroom_khong_pending_khong_doi_intent() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY)
    d = decide(state, U(A.REQUEST, intent=I.NEARBY))
    assert d.action == Nearby()
    assert d.state_after.intent is I.ADVISORY


# ---------- Thu thập slot ----------


def test_bat_dau_tu_van_hoi_dung_mot_cau_ho_so() -> None:
    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY))
    assert isinstance(d.action, Ask) and d.action.key == "profile"
    assert d.state_after.stage is Stage.COLLECTING
    assert d.state_after.intent is I.ADVISORY
    assert d.state_after.ask_counts["profile"] == 1


def test_mot_cau_du_ba_slot_thi_de_xuat_luon() -> None:
    """ "900 triệu, 4 người, đi làm" ngay tin đầu → thấy xe ngay, không hỏi thêm."""

    d = decide(
        S(),
        U(
            A.REQUEST,
            intent=I.ADVISORY,
            slots={N.BUDGET_MAX_VND: 900_000_000, N.PASSENGER_COUNT: 4, N.PURPOSE: "đi làm"},
        ),
    )
    assert isinstance(d.action, Recommend)
    assert d.state_after.stage is Stage.RECOMMENDED


def test_du_slot_thi_de_xuat_ngay() -> None:
    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY, slots=CAR_FULL))
    assert isinstance(d.action, Recommend)
    assert d.state_after.stage is Stage.RECOMMENDED


def test_chi_mot_slot_cung_de_xuat_khong_hoi_them() -> None:
    """ "anh có 40 triệu, đi Hà Nội 30km" — thiếu loại xe, thiếu mục đích: KHÔNG
    hỏi thêm. `act.infer_vehicle_type` suy ra xe máy điện từ ngân sách."""

    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY, slots={N.BUDGET_MAX_VND: 40_000_000, N.REQUIRED_RANGE_KM: 30}))
    assert isinstance(d.action, Recommend)
    assert d.state_after.pending is None


def test_loai_xe_la_gia_tri_la_thi_bo_qua_chu_khong_hoi_lai() -> None:
    # finding 5 vẫn giữ: "xe may dien" không phải CAR/ELECTRIC_MOTORBIKE nên bị
    # bỏ. Nhưng từ 2026-08-29 lõi KHÔNG hỏi lại — nó đề xuất với phần còn lại.
    slots = {N.VEHICLE_TYPE: "xe may dien", N.BUDGET_MAX_VND: 30_000_000, N.PURPOSE: "giao hàng"}
    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY, slots=slots))
    assert isinstance(d.action, Recommend)
    assert N.VEHICLE_TYPE not in d.state_after.slots


def test_khong_hieu_cau_tra_loi_thi_hoi_lai_roi_chuyen_tvv() -> None:
    """Hỏi lại CHỈ khi không hiểu, và vòng đó phải thoát được."""

    state = decide(S(), U(A.REQUEST, intent=I.ADVISORY)).state_after
    seen: list[object] = []
    for _ in range(3):
        d = decide(state, UNCLEAR_UNDERSTANDING)
        seen.append(d.action)
        state = d.state_after
        if isinstance(d.action, Handoff):
            break
    assert isinstance(seen[-1], Handoff)
    assert all(isinstance(a, Ask) and a.key == "profile" for a in seen[:-1])


def test_tra_loi_ho_so_ma_khong_rut_ra_slot_nao_la_khong_hieu() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE, ask_counts={"profile": 1})
    d = decide(state, U(A.SLOT_ANSWER))
    assert isinstance(d.action, Ask) and d.action.key == "profile"
    assert d.state_after.ask_counts["__unclear__"] == 1


def test_khong_hoi_tinh_nang_nua() -> None:
    """Sếp chốt 2026-08-29: bỏ hẳn câu hỏi tính năng sau đề xuất."""

    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY, slots=CAR_FULL))
    assert isinstance(d.action, Recommend)
    assert d.state_after.pending is None


def test_de_xuat_lan_hai_khong_hoi_feature_nua() -> None:
    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.ADVISORY,
        slots={**CAR_FULL, N.HABIT_NEED_TAGS: []},
        ask_counts={"habit_need_tags": 1},
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.BUDGET_MAX_VND: 800_000_000}))
    assert isinstance(d.action, Recommend)
    assert d.state_after.pending is None


# ---------- Lái thử ----------


def test_lai_thu_thieu_xe_hoi_xe() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE


def test_lai_thu_thieu_vi_tri_van_chay_act_lo_phan_hoi_tinh() -> None:
    # Chuyển chỗ hỏi tỉnh sang `act`: policy thuần không đọc được vị trí trình
    # duyệt khách đã chia sẻ, nên chặn ở đây là hỏi lại thứ hệ đã biết.
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert d.action == ShowroomOptions(vehicle_id="v1")


def test_lai_thu_du_thi_showroom_options() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "HN"})
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert d.action == ShowroomOptions(vehicle_id="v1")
    assert d.state_after.stage is Stage.SCHEDULING
    assert d.state_after.pending is not None and d.state_after.pending.kind is K.CHOICE


def test_bam_khung_gio_khong_co_xe_thi_hoi_xe() -> None:
    # finding 3: không được tạo Book với vehicle_id rỗng khi chosen_vehicle_id chưa có.
    state = S(stage=Stage.SCHEDULING, pending=Pending(kind=K.CHOICE, key="showroom_slot"))
    d = decide(state, U(A.CHOICE, choice_ref="__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA", confidence=1.0))
    assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE


def test_bam_nut_khung_gio_la_book() -> None:
    state = S(stage=Stage.SCHEDULING, chosen_vehicle_id="v1", pending=Pending(kind=K.CHOICE, key="showroom_slot"))
    d = decide(state, U(A.CHOICE, choice_ref="__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA", confidence=1.0))
    assert d.action == Book(vehicle_id="v1", choice_ref="__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA")


def test_book_confidence_thap_thi_hoi_xac_nhan() -> None:
    state = S(stage=Stage.SCHEDULING, chosen_vehicle_id="v1", pending=Pending(kind=K.CHOICE, key="showroom_slot"))
    d = decide(state, U(A.CHOICE, choice_ref="__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA", confidence=0.4))
    assert isinstance(d.action, Ask) and d.action.kind is K.CONFIRM
    assert d.state_after.pending is not None and d.state_after.pending.kind is K.CONFIRM


def test_confirm_thi_lam_hanh_dong_treo() -> None:
    treo = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    state = S(
        stage=Stage.SCHEDULING, chosen_vehicle_id="v1", pending=Pending(kind=K.CONFIRM, key="book", options=(treo,))
    )
    d = decide(state, U(A.CONFIRM))
    assert d.action == Book(vehicle_id="v1", choice_ref=treo)


def test_book_confidence_thap_mang_theo_nhan_doc_duoc() -> None:
    # Item 1: nhãn khách đọc được (Pending.labels tầng act điền cho showroom_slot)
    # phải theo qua CONFIRM — policy chỉ chuyển tiếp choice_ref làm option.
    treo = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    nhan = "lái thử VF 8 lúc 9:00 30/08 tại VinFast HTA"
    state = S(
        stage=Stage.SCHEDULING,
        chosen_vehicle_id="v1",
        pending=Pending(kind=K.CHOICE, key="showroom_slot", options=(treo,), labels=(nhan,)),
    )
    d = decide(state, U(A.CHOICE, choice_ref=treo, confidence=0.4))
    assert isinstance(d.action, Ask) and d.action.kind is K.CONFIRM
    assert d.action.options == (treo,)
    assert d.action.labels == (nhan,)


def test_reject_confirm_thi_huy() -> None:
    state = S(
        stage=Stage.SCHEDULING, chosen_vehicle_id="v1", pending=Pending(kind=K.CONFIRM, key="book", options=("x",))
    )
    d = decide(state, U(A.REJECT))
    assert d.action == Reply(template="cancelled")
    assert d.state_after.pending is None
    assert d.state_after.stage is Stage.CHOSEN


# ---------- HITL / handoff / restart / unclear ----------


def test_handed_off_im_lang() -> None:
    d = decide(S(stage=Stage.HANDED_OFF), U(A.REQUEST, intent=I.ADVISORY))
    assert d.action == Silent()


def test_offer_confidence_thap_hoi_xac_nhan() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1")
    d = decide(state, U(A.REQUEST, intent=I.OFFER, confidence=0.3))
    assert isinstance(d.action, Ask) and d.action.kind is K.CONFIRM


def test_restart_xoa_het() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL, pending=ASK_CHOICE)
    d = decide(state, U(A.RESTART))
    assert isinstance(d.action, Ask) and d.action.key == "profile"
    assert d.state_after.slots == {}
    assert d.state_after.chosen_vehicle_id is None
    assert d.state_after.stage is Stage.COLLECTING


def test_unclear_o_recommended_hoi_mau_nao() -> None:
    d = decide(S(stage=Stage.RECOMMENDED, recommended_ids=("v1",)), UNCLEAR_UNDERSTANDING)
    assert d.action == Reply(template="clarify", args={"stage": "RECOMMENDED"})


def test_unclear_qua_2_lan_thi_handoff() -> None:
    state = S(stage=Stage.RECOMMENDED, ask_counts={"__unclear__": 2})
    d = decide(state, UNCLEAR_UNDERSTANDING)
    assert d.action == Handoff()
    assert d.state_after.stage is Stage.HANDED_OFF


def test_unclear_dem_va_reset_khi_hieu() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1",), ask_counts={"__unclear__": 1})
    d1 = decide(state, UNCLEAR_UNDERSTANDING)
    assert d1.state_after.ask_counts["__unclear__"] == 2
    d2 = decide(d1.state_after, U(A.CHOICE, choice_ref="v1"))
    assert d2.state_after.ask_counts.get("__unclear__", 0) == 0


def test_khong_intent_khong_state_thi_hoi_ho_so() -> None:
    d = decide(S(), U(A.REQUEST, intent=I.NONE))
    assert isinstance(d.action, Ask) and d.action.key == "profile"


def test_turn_count_tang_moi_luot() -> None:
    d = decide(S(turn_count=4), U(A.SOCIAL))
    assert d.state_after.turn_count == 5


# ---------- C1: khách gọi tên xe trước khi tới được chặng CHOSEN ----------


def test_lai_thu_goi_ten_xe_ngay_luc_chao_khong_ket_o_cau_hoi_mau_nao() -> None:
    # C1 (5 lượt prod): "cho tôi lái thử VF 8" ngay lúc chào — GREETING chưa tới
    # được CHOSEN nên lõi cũ hỏi "mẫu nào?", khách trả lời lại ra "mẫu nào?" mãi.
    d1 = decide(S(), U(A.REQUEST, intent=I.TEST_DRIVE, vehicle_ids=("v1",)))
    assert d1.action == ShowroomOptions(vehicle_id="v1")
    assert d1.state_after.chosen_vehicle_id == "v1"
    assert d1.state_after.stage is Stage.CHOSEN
    assert d1.state_after.recommended_ids == ("v1",)
    assert d1.state_after.ask_counts.get("vehicle", 0) == 0

    treo = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    d2 = decide(d1.state_after, U(A.CHOICE, choice_ref=treo))
    assert d2.action == Book(vehicle_id="v1", choice_ref=treo)
    assert d2.state_after.ask_counts.get("vehicle", 0) == 0


def test_chon_xe_o_collecting_van_len_duoc_chosen() -> None:
    # C1: COLLECTING → RECOMMENDED → CHOSEN, hai cạnh đều hợp lệ, trong một lượt.
    d = decide(S(stage=Stage.COLLECTING, intent=I.ADVISORY), U(A.CHOICE, vehicle_ids=("v7",)))
    assert d.state_after.chosen_vehicle_id == "v7"
    assert d.state_after.stage is Stage.CHOSEN
    assert d.state_after.recommended_ids == ("v7",)


def test_hoi_xe_qua_so_lan_cho_phep_thi_chuyen_tvv() -> None:
    # C1: câu hỏi CHOICE "mẫu nào?" cũng phải có trần như mọi câu hỏi khác.
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"), ask_counts={"vehicle": MAX_ASKS})
    d = decide(state, U(A.CHOICE, choice_ref="khong-tro-duoc"))
    assert d.action == Handoff()
    assert d.state_after.stage is Stage.HANDED_OFF


def test_hoi_xe_lap_lai_den_tran_roi_moi_chuyen_tvv() -> None:
    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2"))
    for _ in range(MAX_ASKS):
        d = decide(state, U(A.CHOICE, choice_ref="khong-tro-duoc"))
        assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE
        state = d.state_after
    assert decide(state, U(A.CHOICE, choice_ref="khong-tro-duoc")).action == Handoff()


# ---------- Trần Ask: showroom_slot / registration_province / required_range_km ----------


def test_hoi_showroom_slot_lap_lai_den_tran_roi_moi_chuyen_tvv() -> None:
    # Item 2: CHOICE không trỏ được (choice_ref rỗng) vào vòng hỏi lại showroom_slot
    # cũng phải có trần như mọi vòng hỏi khác.
    state = S(stage=Stage.SCHEDULING, chosen_vehicle_id="v1", pending=Pending(kind=K.CHOICE, key="showroom_slot"))
    for _ in range(MAX_ASKS):
        d = decide(state, U(A.CHOICE))
        assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE
        state = d.state_after
    d = decide(state, U(A.CHOICE))
    assert d.action == Handoff()
    assert d.state_after.stage is Stage.HANDED_OFF


# Trần hỏi tỉnh nay nằm ở `act._ask_province` (xem
# `test_act.test_hoi_tinh_qua_tran_thi_chuyen_tu_van_vien_khong_hoi_mai`):
# policy không còn là chỗ phát ra câu hỏi đó nữa.


# ---------- Giữ slot / hợp đồng action ----------


@pytest.mark.parametrize(
    "pending",
    [
        Pending(kind=K.SLOT, key="purpose"),
        Pending(kind=K.CHOICE, key="vehicle", options=("v1", "v2")),
        Pending(kind=K.CONFIRM, key="offer", options=("v1",)),
    ],
)
def test_slot_answer_khong_bi_nuot_du_dang_treo_cau_hoi_kieu_gi(pending: Pending) -> None:
    # I1: slot đi kèm SLOT_ANSWER phải được ghi dù pending là SLOT, CHOICE hay CONFIRM.
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.BUDGET_MAX_VND: 800_000_000}))
    assert d.state_after.slots[N.BUDGET_MAX_VND] == 800_000_000


def test_confirm_khoa_la_thi_hoi_lai_chu_khong_am_tham_gui_tvv() -> None:
    # I2: khoá CONFIRM lạ trước đây rơi thẳng xuống EnqueueHitl (gửi TVV nhầm).
    state = S(
        stage=Stage.CHOSEN, chosen_vehicle_id="v1", pending=Pending(kind=K.CONFIRM, key="khoa_la", options=("x",))
    )
    d = decide(state, U(A.CONFIRM))
    assert d.action == Reply(template="clarify", args={"stage": "CHOSEN"})
    assert d.state_after.pending is None


def test_confirm_offer_van_vao_hitl() -> None:
    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", pending=Pending(kind=K.CONFIRM, key="offer", options=("v1",)))
    d = decide(state, U(A.CONFIRM))
    assert d.action == EnqueueHitl(vehicle_id="v1")
    assert d.state_after.stage is Stage.OFFER_REVIEW


def test_xe_vua_tra_cuu_duoc_nho_sang_luot_sau() -> None:
    # I3: "VF 5 thế nào" (tra cứu) rồi "giá lăn bánh bao nhiêu" — xe không được quên.
    d1 = decide(
        S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots={N.REGISTRATION_PROVINCE: "HN"}),
        U(A.REQUEST, intent=I.CATALOG_LOOKUP, vehicle_ids=("v5",)),
    )
    assert d1.action == Lookup(mode="lookup", vehicle_ids=("v5",))
    assert d1.state_after.slots[N.INTEREST_VEHICLE] == "v5"
    d2 = decide(d1.state_after, U(A.REQUEST, intent=I.ON_ROAD_PRICE))
    assert d2.action == OnRoadPrice(vehicle_id="v5")


def test_so_sanh_thieu_xe_thi_hoi_xe() -> None:
    d = decide(
        S(stage=Stage.RECOMMENDED, recommended_ids=("v1", "v2")), U(A.REQUEST, intent=I.COMPARE, vehicle_ids=("v1",))
    )
    assert isinstance(d.action, Ask) and d.action.kind is K.CHOICE


def test_de_xuat_lan_dau_reason_first() -> None:
    d = decide(S(), U(A.REQUEST, intent=I.ADVISORY, slots=CAR_FULL))
    assert isinstance(d.action, Recommend)
    assert (d.action.reason, d.action.exclude_ids) == ("first", ())


def test_de_xuat_lai_khi_doi_slot_reason_slots_changed() -> None:
    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.ADVISORY,
        recommended_ids=("v1",),
        slots={**CAR_FULL, N.HABIT_NEED_TAGS: []},
        ask_counts={"habit_need_tags": 1},
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.BUDGET_MAX_VND: 800_000_000}))
    assert isinstance(d.action, Recommend)
    assert d.action.reason == "slots_changed"


def test_de_xuat_lai_khi_slot_khong_doi_reason_retry_va_tru_xe_cu() -> None:
    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.ADVISORY,
        recommended_ids=("v1", "v2"),
        slots={**CAR_FULL, N.HABIT_NEED_TAGS: []},
        ask_counts={"habit_need_tags": 1},
    )
    # Không kèm lời chỉnh nào (`question` trống) → retry thuần: loại xe đã xem.
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY))
    assert isinstance(d.action, Recommend)
    assert (d.action.reason, d.action.exclude_ids) == ("retry", ("v1", "v2"))


@pytest.mark.parametrize(
    "act", [A.SLOT_ANSWER, A.REQUEST, A.CHOICE, A.CONFIRM, A.REJECT, A.INTERRUPT, A.SOCIAL, A.RESTART, A.UNCLEAR]
)
@pytest.mark.parametrize("stage", list(Stage))
@pytest.mark.parametrize("intent", list(I))
def test_moi_to_hop_khong_no_va_canh_hop_le(act: A, stage: Stage, intent: I) -> None:
    from src.agents.core.state import can_transition

    state = S(stage=stage, chosen_vehicle_id="v1", recommended_ids=("v1",), slots=CAR_FULL)
    d = decide(state, U(act, intent=intent, slots={N.PURPOSE: "đi làm"}, choice_ref="v1"))
    after = d.state_after.stage
    # C1 cho phép ĐÚNG một đường hai cạnh trong cùng lượt: chặng chưa tới thẳng
    # được CHOSEN (GREETING/COLLECTING) coi xe khách gọi tên là đề xuất tức thì
    # (→ RECOMMENDED) rồi chọn luôn (→ CHOSEN). Mọi đường khác vẫn phải một cạnh.
    qua_de_xuat = can_transition(stage, Stage.RECOMMENDED) and can_transition(Stage.RECOMMENDED, after)
    assert can_transition(stage, after) or qua_de_xuat


def test_thoi_khong_can_tinh_nang_la_retry_khong_phai_doi_tieu_chi() -> None:
    """Chỉ số 3 của spec mục 8 ("lặp bài"), lượt prod thật phiên 125bdea8.

    "thôi không cần tính năng gì" ở RECOMMENDED chỉ ghi `features=[]`. Đó là
    KHÔNG chọn tính năng nào, không phải đổi tiêu chí — coi là `slots_changed`
    thì lõi chạy lại đúng bộ lọc cũ và khách nhận lại y nguyên bài vừa đọc.
    """

    state = S(
        stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), pending=ASK_FEAT, slots=CAR_FULL
    )
    d = decide(state, U(A.REJECT))
    assert isinstance(d.action, Recommend)
    assert (d.action.reason, d.action.exclude_ids) == ("retry", ("v1", "v2"))


# ---------- Đã chọn xe rồi thì không tư vấn lại (prod phiên 61c9dbbd) ----------


def test_so_km_sau_khi_xin_tinh_chi_phi_thi_tinh_luon() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.COST, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REQUIRED_RANGE_KM: 30}))
    assert d.action == Tco(vehicle_id="v1")
    assert d.state_after.slots[N.REQUIRED_RANGE_KM] == 30


def test_ten_tinh_sau_khi_xin_lai_thu_thi_ra_showroom() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REGISTRATION_PROVINCE: "Hà Nội"}))
    assert d.action == ShowroomOptions(vehicle_id="v1")


def test_cau_tra_loi_roi_o_chosen_khong_de_xuat_lai() -> None:
    """Lỗi prod: "ngày anh đi 30km" ở CHOSEN bị hiểu là xin tư vấn lại — lõi đẩy
    khách về danh sách đề xuất, xoá công cả cuộc trò chuyện."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REQUIRED_RANGE_KM: 30}))
    assert not isinstance(d.action, Recommend)
    assert d.state_after.stage is Stage.CHOSEN
    assert d.state_after.chosen_vehicle_id == "v1"
    # Từ vòng 9: "30 km mỗi ngày" là một tiêu chí THẬT, nên lượt này đối chiếu
    # lại chính chiếc đã chốt thay vì trả một cái menu không nhắc tới con số
    # khách vừa đưa. Vẫn đúng điều test này canh: không `Recommend`, không rời
    # chặng, không mất xe.
    assert isinstance(d.action, FitCheck) and d.action.vehicle_id == "v1"


def test_cau_tra_loi_roi_khong_mang_tieu_chi_nao_thi_van_la_cau_xac_nhan() -> None:
    """Lượt rời KHÔNG có slot tư vấn nào (bộ hiểu ý không rút được gì) vẫn đi
    đường xác nhận cũ: không có tiêu chí mới thì không có gì để đối chiếu lại."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST))
    assert d.action == Reply(template="chosen_summary", args={"vehicle_id": "v1"})


def test_unclear_van_nho_viec_khach_vua_goi_ten() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.UNCLEAR, intent=I.COST, confidence=0.3))
    assert d.state_after.intent is I.COST


# ---------- Chọn xe theo NGỮ CẢNH cuối cùng của khách (Sếp chốt 2026-08-29) ----------


def test_sau_so_sanh_thi_hoi_mau_nao_roi_chay_luon_viec_do() -> None:
    """So sánh MỞ LẠI lựa chọn: không được tự chọn hộ mẫu đầu tiên. Và khi khách
    chỉ ra mẫu thì chạy luôn việc đang treo, không bắt họ xin lại."""

    from src.agents.core.actions import Compare

    d1 = decide(S(stage=Stage.RECOMMENDED, intent=I.ADVISORY), U(A.REQUEST, intent=I.COMPARE, vehicle_ids=("v1", "v2")))
    assert isinstance(d1.action, Compare)
    assert d1.state_after.recommended_ids == ("v1", "v2")
    assert d1.state_after.chosen_vehicle_id is None

    d2 = decide(d1.state_after, U(A.REQUEST, intent=I.COST))
    assert isinstance(d2.action, Ask)
    assert (d2.action.kind, d2.action.options) == (K.CHOICE, ("v1", "v2"))

    d3 = decide(d2.state_after, U(A.CHOICE, choice_ref="v2"))
    assert d3.action == Tco(vehicle_id="v2")
    assert d3.state_after.chosen_vehicle_id == "v2"


def test_sau_so_sanh_goi_dich_danh_thi_khong_hoi() -> None:
    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.ADVISORY,
        recommended_ids=("v1", "v2"),
        slots={**CAR_FULL, N.REGISTRATION_PROVINCE: "Hà Nội"},
    )
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE, vehicle_ids=("v2",)))
    assert d.action == ShowroomOptions(vehicle_id="v2")


def test_sau_tra_cuu_mot_xe_thi_dung_ngay_xe_do() -> None:
    d1 = decide(
        S(stage=Stage.COLLECTING, intent=I.ADVISORY), U(A.REQUEST, intent=I.CATALOG_LOOKUP, vehicle_ids=("v2",))
    )
    assert isinstance(d1.action, Lookup)
    d2 = decide(d1.state_after, U(A.REQUEST, intent=I.COST))
    assert d2.action == Tco(vehicle_id="v2")
    assert d2.state_after.chosen_vehicle_id == "v2"


def test_sau_tra_cuu_mot_xe_lai_thu_dung_ngay_xe_do() -> None:
    d1 = decide(
        S(stage=Stage.COLLECTING, intent=I.ADVISORY), U(A.REQUEST, intent=I.CATALOG_LOOKUP, vehicle_ids=("v2",))
    )
    d2 = decide(d1.state_after, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert d2.action == ShowroomOptions(vehicle_id="v2")


def test_goi_dich_danh_thang_ca_xe_da_chot() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.ON_ROAD_PRICE, vehicle_ids=("v2",)))
    assert d.action == OnRoadPrice(vehicle_id="v2")


# ---------- Vòng tinh chỉnh đề xuất tới khi khách chọn (Sếp chốt 2026-08-29) ----------


def test_xin_re_hon_sau_de_xuat_la_chinh_lai_khong_phai_tu_van_lai() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY, question="cho em mẫu rẻ hơn"))
    assert isinstance(d.action, Recommend)
    assert (d.action.reason, d.action.exclude_ids, d.action.refine) == ("revised", ("v1", "v2"), "cho em mẫu rẻ hơn")
    assert d.state_after.stage is Stage.RECOMMENDED


def test_xin_chinh_khi_da_chon_thi_mo_lai_lua_chon() -> None:
    state = S(
        stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", recommended_ids=("v1", "v2"), slots=CAR_FULL
    )
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY, question="cốp rộng hơn nữa được không"))
    assert isinstance(d.action, Recommend) and d.action.reason == "revised"
    # Chặng lùi về RECOMMENDED (khách đang cân lại) nhưng xe đã chốt thì GIỮ:
    # từ vòng 9, xoá nó ở đây là lượt lái thử ngay sau đó mất chỗ dựa và hỏi
    # lại "muốn xem kỹ mẫu nào ạ?" (xem `test_chuoi_that_chot_xe_...`).
    assert d.state_after.chosen_vehicle_id == "v1"
    assert d.state_after.stage is Stage.RECOMMENDED


def test_chon_mot_mau_thi_ket_thuc_vong_chinh() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, choice_ref="v2"))
    assert d.state_after.stage is Stage.CHOSEN
    assert d.state_after.chosen_vehicle_id == "v2"


def test_xin_chinh_intent_none_o_recommended_van_la_chinh_lai() -> None:
    """LLM prod trả `REQUEST + NONE` cho "rẻ hơn được không". `question` đã được
    `understand` điền tất định, nên policy phải đi đường chỉnh chứ không rơi
    xuống nhánh đề xuất lại y bộ cũ."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.NONE, question="rẻ hơn được không"))
    assert isinstance(d.action, Recommend)
    assert (d.action.reason, d.action.exclude_ids, d.action.refine) == ("revised", ("v1", "v2"), "rẻ hơn được không")


def test_xin_chinh_khi_viec_dang_theo_la_hoi_ve_xe_van_la_chinh_lai() -> None:
    """Sau một lượt hỏi về xe, `state.intent` là VEHICLE_QA. LLM trả `NONE` cho
    "rẻ hơn được không" thì luật 6 sẽ lấy VEHICLE_QA và đem lời xin đổi đi TRA
    THÔNG SỐ. Lời xin chỉnh phải thắng việc đang theo."""

    state = S(stage=Stage.RECOMMENDED, intent=I.VEHICLE_QA, recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.NONE, question="rẻ hơn được không"))
    assert isinstance(d.action, Recommend) and d.action.reason == "revised"
    assert d.state_after.intent is I.ADVISORY


def test_bay_danh_sach_xong_van_nhan_cau_tra_loi_la_slot_answer_roi_de_xuat() -> None:
    """Bày danh sách KHÔNG được biến thành lỗi cũ "đổ catalog thay vì hỏi":
    câu hỏi đi kèm cùng tin nhắn, pending vẫn treo, nên lượt sau khách kể nhu
    cầu là đề xuất luôn."""

    state = S(
        stage=Stage.COLLECTING,
        intent=I.ADVISORY,
        slots={N.VEHICLE_TYPE: "CAR"},
        pending=Pending(kind=K.SLOT, key="profile"),
    )
    d = decide(
        state,
        U(
            A.SLOT_ANSWER,
            intent=I.NONE,
            slots={N.BUDGET_MAX_VND: 900_000_000, N.PASSENGER_COUNT: 5, N.PURPOSE: "đi làm"},
        ),
    )
    assert isinstance(d.action, Recommend)
    assert d.state_after.pending is None


def test_loai_xe_kem_bat_ky_thu_gi_khac_thi_de_xuat_luon() -> None:
    """Bước 6 chỉ giữ câu hồ sơ khi loại xe là thứ DUY NHẤT biết được. Thêm bất
    kỳ slot nào nữa là đủ để lọc — không hỏi thêm lượt nào."""

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 800_000_000}))
    assert isinstance(d.action, Recommend)
    assert d.state_after.pending is None


# ---------- prod: câu trả lời cho slot đang treo thắng intent tra cứu ----------


def test_tra_loi_tinh_dang_treo_khong_bi_nearby_cuop_luot() -> None:
    """Lượt prod: treo `registration_province`, khách gõ "Hà Nội" → LLM trả
    `SLOT_ANSWER + NEARBY`. Luật 6 chạy `Nearby` và khách nhận "Dạ Quý khách
    muốn tìm loại địa điểm nào ạ?" thay vì khung giờ lái thử."""

    pending = Pending(kind=K.SLOT, key=N.REGISTRATION_PROVINCE.value)
    state = S(stage=Stage.CHOSEN, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, intent=I.NEARBY, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert d.action == ShowroomOptions(vehicle_id="v1")
    assert d.state_after.slots[N.REGISTRATION_PROVINCE] == "HN"


def test_hoi_showroom_that_su_giua_chung_van_la_chen_ngang() -> None:
    """Lưới trên KHÔNG được nuốt lượt chen ngang thật: câu hỏi showroom không
    mang slot nào của câu đang treo vẫn phải được trả lời."""

    pending = Pending(kind=K.SLOT, key=N.REGISTRATION_PROVINCE.value)
    state = S(stage=Stage.CHOSEN, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.INTERRUPT, intent=I.NEARBY))
    assert isinstance(d.action, Nearby) and d.action.resume_pending


def test_lai_thu_khong_hoi_tinh_nua_act_lo_phan_vi_tri() -> None:
    """Policy THUẦN không thấy được vị trí trình duyệt khách đã chia sẻ, nên nó
    không được quyền chặn lượt lái thử vì một slot trống. `act` có đọc được vị
    trí đó và tự hỏi tỉnh khi thật sự không có gì."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert d.action == ShowroomOptions(vehicle_id="v1")
    assert d.state_after.stage is Stage.SCHEDULING


# ---------- prod: tỉnh trả lời câu hỏi của act (giá lăn bánh / lái thử) ----------


def test_tra_loi_tinh_cho_gia_lan_banh_khong_bi_nearby_cuop_luot() -> None:
    """Lượt prod: `OnRoadPrice` hỏi tỉnh qua `act` (`pending` = registration_province),
    khách gõ "Hà Nội" → LLM trả `REQUEST + NEARBY`. Act KHÔNG nằm trong
    `_ANSWER_ACTS` nên luật 4 không chạy, luật 5 coi đây là chen ngang và khách
    nhận "Dạ Quý khách muốn tìm loại địa điểm nào ạ?" thay vì giá lăn bánh."""

    pending = Pending(kind=K.SLOT, key=N.REGISTRATION_PROVINCE.value)
    state = S(stage=Stage.CHOSEN, intent=I.ON_ROAD_PRICE, chosen_vehicle_id="v1", pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.NEARBY, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert d.action == OnRoadPrice(vehicle_id="v1")
    assert d.state_after.slots[N.REGISTRATION_PROVINCE] == "HN"
    assert d.state_after.pending is None


def test_tra_loi_tinh_cho_lai_thu_du_llm_goi_la_chen_ngang() -> None:
    """Cùng lưới cho câu hỏi tỉnh của lượt lái thử (`act._ask_province`): act
    `INTERRUPT` kèm ĐÚNG slot đang hỏi vẫn là câu trả lời."""

    pending = Pending(kind=K.SLOT, key=N.REGISTRATION_PROVINCE.value)
    state = S(stage=Stage.SCHEDULING, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.INTERRUPT, intent=I.NEARBY, slots={N.REGISTRATION_PROVINCE: "DN"}))
    assert d.action == ShowroomOptions(vehicle_id="v1")
    assert d.state_after.slots[N.REGISTRATION_PROVINCE] == "DN"


# ---------- prod: đổi loại xe giữa chừng ----------


def test_doi_loai_xe_giua_chung_thi_de_xuat_lai_dung_loai() -> None:
    """Lượt prod LP03: đang ở `RECOMMENDED` với ô tô, khách gõ "thôi xe máy đi"
    → lõi vẫn đọc lại VF 6. Slot loại xe MỚI khác loại đang theo là một lượt làm
    lại: bỏ danh sách cũ, bỏ xe đã chốt, chạy đề xuất cho đúng loại vừa nêu."""

    state = S(
        stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), chosen_vehicle_id="v1", slots=CAR_FULL
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE"}))
    assert isinstance(d.action, Recommend)
    assert d.action.reason == "slots_changed" and d.action.switched_type == "ELECTRIC_MOTORBIKE"
    assert d.state_after.recommended_ids == ()
    assert d.state_after.chosen_vehicle_id is None
    assert d.state_after.slots[N.VEHICLE_TYPE] == "ELECTRIC_MOTORBIKE"


def test_nhac_lai_dung_loai_xe_cu_khong_phai_doi_loai() -> None:
    """Nhắc lại đúng loại đang theo KHÔNG được xoá công: đó là một lượt bình thường."""

    state = S(
        stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), chosen_vehicle_id="v1", slots=CAR_FULL
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.VEHICLE_TYPE: "CAR"}))
    assert not (isinstance(d.action, Recommend) and d.action.switched_type)
    assert d.state_after.recommended_ids == ("v1", "v2")


# ---------- prod: nút khung giờ tới khi lõi không còn treo câu chọn giờ ----------


LP21_TOKEN = "__lichlaithu__|2026-08-29T10:00:00+07:00|VinFast E-Car Hưng Yên"


def test_nut_khung_gio_khong_con_pending_van_di_duong_dat_lich() -> None:
    """Lượt prod LP21: khách bấm lại nút khung giờ của một lượt cũ (phiên đã đi
    tiếp, không còn `pending`) → lõi hỏi "Anh/chị muốn xem mẫu nào ạ?". Nút là
    mã có chữ ký, không phải lời trỏ vào danh sách: nó phải đi đường đặt lịch để
    `act` kiểm chữ ký rồi nói thật khi mã đã hết hạn."""

    state = S(stage=Stage.SCHEDULING, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, choice_ref=LP21_TOKEN))
    assert d.action == Book(vehicle_id="v1", choice_ref=LP21_TOKEN)


def test_nut_khung_gio_khi_dang_treo_cau_chon_mau_cung_di_duong_dat_lich() -> None:
    pending = Pending(kind=K.CHOICE, key="vehicle", options=("v1", "v2"))
    state = S(stage=Stage.RECOMMENDED, intent=I.TEST_DRIVE, chosen_vehicle_id="v1", pending=pending, slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, choice_ref=LP21_TOKEN))
    assert isinstance(d.action, Book) and d.action.choice_ref == LP21_TOKEN


# ---------- prod: slot mới ở chặng đề xuất thì đề xuất lại ----------


def test_slot_moi_o_chang_de_xuat_thi_de_xuat_lai_khong_hoi_mau_nao() -> None:
    """Lượt prod LP03/LP07: sau RESTART, khách gõ "700 triệu" (hay "đi làm") ở
    `RECOMMENDED` và nhận "Anh/chị muốn xem kỹ mẫu nào trong các mẫu em vừa gợi
    ý ạ?" — câu hỏi lại của nhánh KHÔNG HIỂU, đúng lúc khách vừa cho thêm một
    tiêu chí rõ ràng. Có tiêu chí mới thì chạy lại bộ lọc, không hỏi lại."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), slots={N.VEHICLE_TYPE: "CAR"})
    d = decide(state, U(A.UNCLEAR, slots={N.BUDGET_MAX_VND: 700_000_000}))
    assert isinstance(d.action, Recommend) and d.action.reason == "slots_changed"
    assert d.state_after.slots[N.BUDGET_MAX_VND] == 700_000_000


def test_muc_dich_moi_o_chang_de_xuat_cung_chay_lai_bo_loc() -> None:
    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.ADVISORY,
        recommended_ids=("v1",),
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 700_000_000},
    )
    d = decide(state, U(A.SLOT_ANSWER, slots={N.PURPOSE: "đi làm"}))
    assert isinstance(d.action, Recommend) and d.action.reason == "slots_changed"


def test_khong_hieu_that_o_chang_de_xuat_van_duoc_hoi_lai() -> None:
    """Lưới trên KHÔNG được nuốt lượt không hiểu thật: không rút ra slot nào thì
    vẫn đi đường hỏi lại như cũ."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), slots={N.VEHICLE_TYPE: "CAR"})
    d = decide(state, U(A.UNCLEAR))
    assert isinstance(d.action, Reply)


# ---------- prod vòng 7 (LP35): xe khách gọi ĐÍCH DANH luôn thắng ----------


def test_chon_xe_ngoai_danh_sach_de_xuat_van_duoc_chon() -> None:
    """Lượt prod LP35: đang gợi ý VF 3, khách gõ "Tôi chọn VinFast VF 5 All New"
    → lõi đọc lại bài VF 3. Xe khách gọi đích danh luôn thắng, kể cả khi nó
    KHÔNG nằm trong `recommended_ids` — và phải được ghi vào danh sách đó để
    lượt sau ("tính giá lăn bánh") không hỏi lại "muốn xem mẫu nào"."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v3",), slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, vehicle_ids=("v5",), confidence=0.9))
    assert isinstance(d.action, Reply)
    assert d.state_after.chosen_vehicle_id == "v5"
    assert "v5" in d.state_after.recommended_ids


def test_sau_khi_chon_xe_ngoai_danh_sach_thi_tinh_gia_lan_banh_ngay() -> None:
    state = S(
        stage=Stage.CHOSEN, intent=I.ADVISORY, recommended_ids=("v3", "v5"), chosen_vehicle_id="v5", slots=CAR_FULL
    )
    d = decide(state, U(A.REQUEST, I.ON_ROAD_PRICE, confidence=0.9))
    assert d.action == OnRoadPrice(vehicle_id="v5")


def test_doi_loai_xe_o_luot_xin_chinh_van_la_doi_loai() -> None:
    """Lượt prod LP03: "thôi xe máy đi" về `REQUEST + ADVISORY` kèm nguyên văn
    câu ở `question` (đường xin CHỈNH). Luật đổi loại phải thắng đường đó, nếu
    không lõi chỉnh bộ lọc CŨ và trả lại đúng mẫu ô tô vừa gợi ý."""

    state = S(
        stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1", "v2"), chosen_vehicle_id="v1", slots=CAR_FULL
    )
    u = U(
        A.REQUEST, I.ADVISORY, slots={N.VEHICLE_TYPE: "ELECTRIC_MOTORBIKE"}, question="thôi xe máy đi", confidence=0.9
    )
    d = decide(state, u)
    assert isinstance(d.action, Recommend) and d.action.switched_type == "ELECTRIC_MOTORBIKE"
    assert d.state_after.recommended_ids == ()


def test_nut_khung_gio_la_tin_nhan_dau_phien_van_di_duong_dat_lich() -> None:
    """Lượt prod LP21: mã nút tới ở chặng GREETING, chưa có xe nào và không có
    `pending` nào. Vẫn phải đi đường đặt lịch — `act` là chỗ DUY NHẤT đọc được
    chữ ký, nên chỉ nó mới nói được "mã này hết hiệu lực"."""

    d = decide(S(), U(A.CHOICE, choice_ref=LP21_TOKEN, confidence=1.0))
    assert d.action == Book(vehicle_id="", choice_ref=LP21_TOKEN)


# ---------- prod vòng 8: CHOICE kèm tên xe được chốt ở MỌI chặng trước đó ----------


@pytest.mark.parametrize("stage", [Stage.GREETING, Stage.COLLECTING, Stage.RECOMMENDED, Stage.CHOSEN])
def test_choice_kem_ten_xe_duoc_chot_o_moi_chang(stage: Stage) -> None:
    """Xe khách gọi đích danh phải vào `chosen_vehicle_id` VÀ `recommended_ids`
    ở cả bốn chặng trước khi cam kết — lượt sau ("tính giá lăn bánh") mới có xe
    để tra thay vì hỏi lại "muốn xem mẫu nào"."""

    state = S(stage=stage, intent=I.ADVISORY, recommended_ids=("v3",), slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, I.ADVISORY, vehicle_ids=("v5",), confidence=0.9))
    assert d.state_after.chosen_vehicle_id == "v5"
    assert "v5" in d.state_after.recommended_ids


def test_choice_kem_ten_xe_giu_slot_di_kem_khi_khong_treo_gi() -> None:
    """Lượt CHỌN mang thêm tiêu chí ("chọn VF 5, ngân sách 800tr") khi lõi KHÔNG
    treo câu hỏi nào vẫn phải ghi tiêu chí đó."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v3",), slots=CAR_FULL)
    d = decide(
        state, U(A.CHOICE, I.ADVISORY, vehicle_ids=("v5",), slots={N.BUDGET_MAX_VND: 800_000_000}, confidence=0.9)
    )
    assert d.state_after.slots[N.BUDGET_MAX_VND] == 800_000_000
    assert d.state_after.chosen_vehicle_id == "v5"


# ---------- prod vòng 8: tra cứu CÓ tên xe mang theo chiếc xe đó ----------


@pytest.mark.parametrize("act", [A.INTERRUPT, A.REQUEST])
def test_catalog_lookup_kem_ten_xe_mang_theo_xe(act: A) -> None:
    """ "VF 3 giá bao nhiêu" về `CATALOG_LOOKUP, vehicle_ids=[VF3]`. `Lookup`
    trước đây không chở `vehicle_ids` nên `act` chỉ còn cửa danh mục để đi và
    khách nhận cả bảng 27 ô tô + 7 xe máy."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v3", "v5"), slots=CAR_FULL)
    d = decide(state, U(act, I.CATALOG_LOOKUP, vehicle_ids=("v3",), confidence=0.9))
    assert d.action == Lookup(mode="lookup", vehicle_ids=("v3",))
    assert d.state_after.slots[N.INTEREST_VEHICLE] == "v3"


def test_catalog_lookup_khong_ten_xe_van_la_lookup_trong() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.CATALOG_LOOKUP, confidence=0.9))
    assert d.action == Lookup(mode="lookup")


def test_catalog_lookup_kem_ten_xe_khi_dang_treo_cau_hoi_van_mang_theo_xe() -> None:
    """Đường CHEN NGANG (luật 5) cũng phải chở xe — cùng một hàm dựng quyết định."""

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE, slots=CAR_FULL)
    d = decide(state, U(A.INTERRUPT, I.CATALOG_LOOKUP, vehicle_ids=("v3",), confidence=0.9))
    assert d.action == Lookup(mode="lookup", vehicle_ids=("v3",), resume_pending=True)


# ---------- Nhóm prod vòng 9: câu hỏi "có hợp với nhu cầu không" ----------


def test_chon_xe_kem_cau_hoi_do_phu_hop_thi_danh_gia_luon() -> None:
    """Lượt prod vòng 9: "ok chọn VF2 đi, có hợp với nhu cầu của tôi không" →
    lõi đáp "em ghi nhận anh/chị chọn VF 2. Anh/chị muốn em tính chi phí…".
    Vế HỎI bị nuốt sạch. Một lượt phải làm đủ hai việc: chốt xe VÀ trả lời."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, slots=CAR_FULL, recommended_ids=("v5", "v3", "v2"))
    d = decide(state, U(A.CHOICE, I.NONE, vehicle_ids=("v2",), fit_asked=True))
    assert isinstance(d.action, FitCheck)
    assert d.action.vehicle_id == "v2"
    assert d.action.just_chosen is True
    assert d.action.alternative_ids == ("v5", "v3", "v2")
    assert d.state_after.chosen_vehicle_id == "v2"
    assert d.state_after.stage is Stage.CHOSEN


def test_chon_xe_khong_hoi_gi_them_van_la_cau_xac_nhan_cu() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, slots=CAR_FULL, recommended_ids=("v5", "v3", "v2"))
    d = decide(state, U(A.CHOICE, I.NONE, vehicle_ids=("v2",)))
    assert isinstance(d.action, Reply) and d.action.template == "chosen_summary"


def test_viec_cam_ket_dang_theo_van_thang_cau_hoi_do_phu_hop() -> None:
    """ "Chọn VF 2 được không" giữa lượt tính chi phí vẫn phải ra bảng chi phí:
    cụm "được không" là lối nói lịch sự, không phải một câu hỏi đánh giá mới."""

    state = S(stage=Stage.RECOMMENDED, intent=I.COST, recommended_ids=("v2",), slots=CAR_FULL)
    d = decide(state, U(A.CHOICE, I.NONE, vehicle_ids=("v2",), fit_asked=True))
    assert isinstance(d.action, Tco)


def test_them_nhu_cau_sau_khi_da_chon_thi_danh_gia_lai_chinh_xe_do() -> None:
    """Lượt prod vòng 9: đã chọn VF 2, khách gõ "gia đình tôi có 4 người, tôi
    muốn sử dụng đi chơi xa" → lõi trả `SAME_PICK` ("em vẫn thấy VF 2 hợp
    nhất"), không nhắc tới một tiêu chí nào khách vừa đưa."""

    state = S(
        stage=Stage.CHOSEN,
        intent=I.ADVISORY,
        slots={N.VEHICLE_TYPE: "CAR", N.BUDGET_MAX_VND: 500_000_000, N.PURPOSE: "đi chơi cùng gia đình"},
        chosen_vehicle_id="v2",
        recommended_ids=("v5", "v3", "v2"),
    )
    d = decide(state, U(A.SLOT_ANSWER, I.ADVISORY, slots={N.PASSENGER_COUNT: 4, N.PURPOSE: "đi chơi xa"}))
    assert isinstance(d.action, FitCheck)
    assert d.action.vehicle_id == "v2"
    assert d.action.just_chosen is False
    assert d.action.alternative_ids == ("v5", "v3", "v2")
    # Xe đã chốt KHÔNG bị bỏ, và slot mới phải có mặt để `act` lọc lại.
    assert d.state_after.chosen_vehicle_id == "v2"
    assert d.state_after.slots[N.PASSENGER_COUNT] == 4
    assert d.state_after.slots[N.PURPOSE] == "đi chơi xa"


def test_them_nhu_cau_giua_viec_cam_ket_van_di_dung_viec_do() -> None:
    """ "Ngày anh đi 40 km" giữa lượt tính chi phí là câu trả lời cho việc đó."""

    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v2", recommended_ids=("v2",), slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, I.NONE, slots={N.REQUIRED_RANGE_KM: 40}))
    assert isinstance(d.action, Tco)


def test_chua_chot_xe_thi_them_nhu_cau_van_la_mot_luot_de_xuat() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, slots=CAR_FULL, recommended_ids=("v5", "v3"))
    d = decide(state, U(A.SLOT_ANSWER, I.ADVISORY, slots={N.PASSENGER_COUNT: 7}))
    assert isinstance(d.action, Recommend)


def test_hoi_cach_chot_xe_thi_tra_buoc_tiep_theo() -> None:
    """Lượt prod vòng 9: "làm sao để tôi chốt vf3" → `SAME_PICK` ("em vẫn thấy
    VF 3 hợp nhất") — đọc lại đúng chiếc khách vừa nói là muốn chốt."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, slots=CAR_FULL, recommended_ids=("v3", "v5"))
    d = decide(state, U(A.REQUEST, I.ADVISORY, vehicle_ids=("v3",), next_steps_asked=True))
    assert d.action == NextSteps(vehicle_id="v3")
    assert d.state_after.chosen_vehicle_id == "v3"


def test_hoi_cach_chot_khi_da_co_xe_da_chon_khong_can_goi_ten_lai() -> None:
    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, slots=CAR_FULL, chosen_vehicle_id="v3", recommended_ids=("v3",))
    d = decide(state, U(A.REQUEST, I.NONE, next_steps_asked=True))
    assert d.action == NextSteps(vehicle_id="v3")


def test_hoi_thu_tuc_khi_chua_co_xe_nao_thi_van_di_duong_tu_van() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.ADVISORY, next_steps_asked=True))
    assert not isinstance(d.action, NextSteps)


def test_hoi_cach_chot_giua_viec_cam_ket_van_di_dung_viec_do() -> None:
    state = S(
        stage=Stage.SCHEDULING, intent=I.TEST_DRIVE, chosen_vehicle_id="v3", recommended_ids=("v3",), slots=CAR_FULL
    )
    d = decide(state, U(A.REQUEST, I.TEST_DRIVE, next_steps_asked=True))
    assert isinstance(d.action, ShowroomOptions)


def test_cau_ngoai_pham_vi_ve_xe_da_chon_khong_bao_gio_la_loi_xin_chinh() -> None:
    """Lượt prod vòng 9: "VF3 thì nên đi du lịch ở Việt Nam, ở đâu" nhận về
    "em chưa có mẫu nào khác hợp hơn ạ" — sai cả chủ đề."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, slots=CAR_FULL, chosen_vehicle_id="v3", recommended_ids=("v3",))
    d = decide(state, U(A.REQUEST, I.ADVISORY, question="nên đi du lịch ở đâu", off_topic_asked=True))
    assert d.action == ScopeNote(vehicle_id="v3")
    assert not isinstance(d.action, Recommend)
    assert d.state_after.chosen_vehicle_id == "v3"


def test_cau_ngoai_pham_vi_khi_chua_co_xe_nao_thi_di_duong_cu() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.ADVISORY, off_topic_asked=True))
    assert not isinstance(d.action, ScopeNote)


# ---------- prod vòng 9: xe đã chốt không được biến mất giữa chừng ----------


def test_luot_xin_chinh_de_xuat_khong_xoa_xe_da_chot() -> None:
    state = S(
        stage=Stage.CHOSEN, intent=I.ADVISORY, slots=CAR_FULL, chosen_vehicle_id="v3", recommended_ids=("v3", "v5")
    )
    d = decide(state, U(A.REQUEST, I.ADVISORY, question="rẻ hơn được không"))
    assert isinstance(d.action, Recommend) and d.action.reason == "revised"
    assert d.state_after.chosen_vehicle_id == "v3"


def test_chuoi_that_chot_xe_roi_hoi_them_roi_dat_lai_thu() -> None:
    """Chuỗi prod vòng 9, chạy đúng thứ tự thật:

    "ok tôi chốt VF3" → "rẻ hơn được không" → "tôi muốn đặt lịch lái thử" →
    "Hà Nội". Trên prod, lượt xin xem thêm xoá mất xe đã chốt nên lượt lái thử
    hỏi "muốn xem kỹ mẫu nào?", và "Hà Nội" nhận lại y nguyên câu đó.
    """

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, slots=CAR_FULL, recommended_ids=("v3", "v5"))

    chot = decide(state, U(A.CHOICE, I.NONE, vehicle_ids=("v3",)))
    assert chot.state_after.chosen_vehicle_id == "v3"

    them = decide(chot.state_after, U(A.REQUEST, I.ADVISORY, question="rẻ hơn được không"))
    assert them.state_after.chosen_vehicle_id == "v3"

    lai_thu = decide(them.state_after, U(A.REQUEST, I.TEST_DRIVE))
    assert lai_thu.action == ShowroomOptions(vehicle_id="v3")
    assert lai_thu.state_after.pending is not None
    assert lai_thu.state_after.pending.key == "showroom_slot"

    tinh = decide(lai_thu.state_after, U(A.SLOT_ANSWER, I.NONE, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert tinh.action == ShowroomOptions(vehicle_id="v3")
    assert tinh.state_after.slots[N.REGISTRATION_PROVINCE] == "HN"
    assert tinh.state_after.chosen_vehicle_id == "v3"


def test_tra_loi_tinh_du_llm_goi_la_nearby_van_di_tiep_viec_lai_thu() -> None:
    """ "Hà Nội" về `INTERRUPT + NEARBY` trong lúc treo câu chọn khung giờ: luật
    5 chạy `Nearby` và khách nhận "Quý khách muốn tìm loại địa điểm nào ạ?"."""

    state = S(
        stage=Stage.SCHEDULING,
        intent=I.TEST_DRIVE,
        slots=CAR_FULL,
        chosen_vehicle_id="v3",
        recommended_ids=("v3",),
        pending=Pending(kind=K.CHOICE, key="showroom_slot"),
    )
    d = decide(state, U(A.INTERRUPT, I.NEARBY, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert d.action == ShowroomOptions(vehicle_id="v3")


def test_tra_loi_tinh_khi_chua_chot_xe_thi_van_hoi_mau_nao() -> None:
    """Không có xe đã chốt thì "Hà Nội" không đủ để đoán khách muốn lái thử xe
    nào — cửa này KHÔNG được mở rộng thành đoán mò."""

    state = S(
        stage=Stage.RECOMMENDED,
        intent=I.TEST_DRIVE,
        slots=CAR_FULL,
        recommended_ids=("v3", "v5"),
        pending=Pending(kind=K.CHOICE, key="vehicle", options=("v3", "v5")),
    )
    d = decide(state, U(A.SLOT_ANSWER, I.NONE, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert isinstance(d.action, Ask)


# ---------- prod vòng 10: câu hỏi ĐỊA ĐIỂM đứng trước cả đề xuất lẫn đối chiếu ----------


def test_cau_ngoai_pham_vi_thang_duong_doi_chieu_nhu_cau() -> None:
    """Luật 5c (đã chốt xe + lượt mang tiêu chí mới → `FitCheck`) không được
    cướp lượt của một câu hỏi ĐIỂM ĐẾN: lượt prod vòng 10 trả về một bản đánh
    giá độ phù hợp cho câu "VF3 thì nên đi du lịch ở Việt Nam, ở đâu"."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", recommended_ids=("v1",))
    u = U(A.REQUEST, I.ADVISORY, slots={N.PURPOSE: "du lịch"}, off_topic_asked=True)
    assert decide(state, u).action == ScopeNote(vehicle_id="v1")


def test_cau_ngoai_pham_vi_thang_ca_duong_chinh_de_xuat() -> None:
    """Ở `RECOMMENDED`, luật 5b đọc mọi lượt mang tiêu chí thành lời xin CHỈNH.
    Một câu hỏi điểm đến mang theo `purpose` cũng rơi vào đó nếu luật ngoài
    phạm vi đứng sau."""

    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v1",))
    u = U(A.SLOT_ANSWER, I.ADVISORY, slots={N.PURPOSE: "du lịch"}, vehicle_ids=("v1",), off_topic_asked=True)
    assert decide(state, u).action == ScopeNote(vehicle_id="v1")


def test_sua_so_km_sau_khi_da_bao_chi_phi_thi_tinh_lai_ngay() -> None:
    # Probe V2-32: "ngày anh đi 60km cơ" sau lượt TCO phải ra Tco lần nữa, không
    # rơi xuống nhánh chung trả lại con số cũ.
    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REQUIRED_RANGE_KM: 60}))
    assert isinstance(d.action, Tco)
    assert d.action.vehicle_id == "v1"
    assert d.state_after.slots[N.REQUIRED_RANGE_KM] == 60


# ---------- đợt 8: khía cạnh tra cứu (giá) đi theo Lookup ----------


def test_catalog_lookup_mang_theo_khia_canh_gia() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY, recommended_ids=("v3", "v5"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.CATALOG_LOOKUP, vehicle_ids=("v3",), confidence=0.9, aspect="price"))
    assert d.action == Lookup(mode="lookup", vehicle_ids=("v3",), aspect="price")


# ---------- đợt 8: nêu tên xe KHÔNG có trong danh mục → nói thật, không hỏi cụt ----------


@pytest.mark.parametrize("act", [A.CHOICE, A.REQUEST, A.INTERRUPT])
def test_ten_xe_khong_co_trong_danh_muc_thi_not_in_catalog(act: A) -> None:
    """Prod benchmark2: "anh muốn mua mẫu vf10" → `CATALOG_LOOKUP, CHOICE,
    vehicle_ids=[]` → `_ask_vehicle` → "Anh/chị muốn xem mẫu nào ạ?". Khách vừa
    nêu tên rồi; hỏi lại tên là không nghe. Vẫn treo CHỌN MẪU để câu "VF 8" tiếp
    theo đi đúng đường, và vẫn đếm vào trần hỏi."""

    from src.agents.core.actions import NotInCatalog

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots={N.VEHICLE_TYPE: "CAR"})
    d = decide(state, U(act, I.CATALOG_LOOKUP, unresolved_mention="VF 10", confidence=0.8))
    assert d.action == NotInCatalog(mention="VF 10")
    assert d.state_after.pending == Pending(kind=K.CHOICE, key="vehicle", asked_at_turn=1)
    assert d.state_after.ask_counts["vehicle"] == 1


def test_viec_can_xe_ma_ten_khong_co_trong_danh_muc_cung_not_in_catalog() -> None:
    from src.agents.core.actions import NotInCatalog

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.COST, unresolved_mention="VF 10", confidence=0.9))
    assert d.action == NotInCatalog(mention="VF 10")
    assert d.state_after.intent is I.COST


def test_not_in_catalog_qua_tran_hoi_thi_chuyen_tvv() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, ask_counts={"vehicle": MAX_ASKS})
    d = decide(state, U(A.CHOICE, I.CATALOG_LOOKUP, unresolved_mention="VF 10"))
    assert d.action == Handoff()


def test_sau_not_in_catalog_khach_goi_ten_that_thi_chon_duoc() -> None:
    state = S(
        stage=Stage.COLLECTING,
        intent=I.ADVISORY,
        pending=Pending(kind=K.CHOICE, key="vehicle", options=("v1", "v2"), labels=("VF 5", "VF 8")),
    )
    d = decide(state, U(A.CHOICE, I.NONE, vehicle_ids=("v2",)))
    assert isinstance(d.action, Reply) and d.state_after.chosen_vehicle_id == "v2"


# ---------- đợt 8: endpoint chọn vị trí trên thẻ ghi state y như act ShowroomOptions ----------


def test_schedule_for_treo_chon_khung_gio_va_chot_xe() -> None:
    """`POST /agent/test-drive/options` dựng thẻ ngoài lượt chat, nhưng nút giờ
    bấm xong vẫn phải đi đúng đường `Book`: cần `pending=showroom_slot`, xe đã
    chốt, và chặng SCHEDULING khi cạnh hợp lệ."""

    from src.agents.core.policy import schedule_for

    after = schedule_for(S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", recommended_ids=("v1",)), "v1")
    assert after.stage is Stage.SCHEDULING and after.intent is I.TEST_DRIVE
    assert after.pending == Pending(kind=K.CHOICE, key="showroom_slot", asked_at_turn=after.turn_count)
    # Chưa chốt xe (đang ở COLLECTING): vẫn ghi xe, chặng dừng ở CHOSEN như `_run_vehicle_intent`.
    fresh = schedule_for(S(stage=Stage.COLLECTING), "v2")
    assert fresh.chosen_vehicle_id == "v2" and fresh.stage is Stage.CHOSEN and "v2" in fresh.recommended_ids
    # Nút giờ sau đó đi đúng đường Book.
    d = decide(fresh, U(A.CHOICE, choice_ref="__lichlaithu__|x|y", confidence=0.9))
    assert isinstance(d.action, Book) and d.action.vehicle_id == "v2"


def test_khach_xin_gap_tu_van_vien_thi_chuyen_nguoi_ngay() -> None:
    from src.agents.core.actions import Handoff

    state = S(stage=Stage.RECOMMENDED, recommended_ids=("v1",), slots=CAR_FULL, pending=ASK_VT)
    d = decide(state, U(A.REQUEST, I.HANDOFF))
    assert isinstance(d.action, Handoff)
    assert d.state_after.stage is Stage.HANDED_OFF and d.state_after.pending is None


# ---------- Sếp 2026-08-31: thẻ chi phí gộp giá lăn bánh, cập nhật tại chỗ ----------


def test_tinh_thanh_sau_luot_chi_phi_cap_nhat_lai_the_khong_bai_moi() -> None:
    """Thẻ chi phí gộp cả giá lăn bánh: khách nhắc TỈNH sau khi thẻ đã hiện thì
    chạy lại Tco với cờ refreshed — act nói "em đã cập nhật", client thay số
    tại chỗ trên thẻ cũ, không gửi bài dẫn + thẻ mới."""

    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REGISTRATION_PROVINCE: "Đà Nẵng"}))
    assert isinstance(d.action, Tco)
    assert d.action.refreshed_province and not d.action.refreshed_km
    assert d.state_after.slots[N.REGISTRATION_PROVINCE] == "Đà Nẵng"


def test_km_sau_luot_chi_phi_mang_co_refreshed_km() -> None:
    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, slots={N.REQUIRED_RANGE_KM: 60}))
    assert isinstance(d.action, Tco)
    assert d.action.refreshed_km and not d.action.refreshed_province


def test_gia_lan_banh_o_chosen_sang_costing_de_bat_luot_cap_nhat() -> None:
    """Lăn bánh trả thẻ chi phí nên chặng phải sang COSTING như `COST` — không
    sang thì luật 5a' không bắt được khách nhắc lại tỉnh/km ngay sau đó."""

    state = S(stage=Stage.CHOSEN, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.ON_ROAD_PRICE))
    assert d.action == OnRoadPrice(vehicle_id="v1")
    assert d.state_after.stage is Stage.COSTING


def test_dinh_chinh_tinh_sau_the_chi_phi_ke_ca_nhanh_lan_banh_van_la_cap_nhat() -> None:
    state = S(stage=Stage.COSTING, intent=I.ON_ROAD_PRICE, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, I.ON_ROAD_PRICE, slots={N.REGISTRATION_PROVINCE: "DN"}))
    assert isinstance(d.action, Tco) and d.action.refreshed_province


def test_slot_chep_lai_khong_kich_chu_da_cap_nhat() -> None:
    # "giá lăn bánh thì sao" kèm km/tỉnh CŨ (LLM chép transcript) phải đi đường
    # on-road bình thường, không thành lượt "đã cập nhật".
    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v1", slots={**CAR_FULL, N.REQUIRED_RANGE_KM: 60})
    d = decide(state, U(A.REQUEST, I.ON_ROAD_PRICE, slots={N.REQUIRED_RANGE_KM: 60}))
    assert not isinstance(d.action, Tco) or not (d.action.refreshed_km or d.action.refreshed_province)


def test_lan_banh_tu_costing_giu_costing_de_luat_cap_nhat_con_song() -> None:
    state = S(stage=Stage.COSTING, intent=I.COST, chosen_vehicle_id="v1", slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, I.ON_ROAD_PRICE))
    assert d.state_after.stage is Stage.COSTING


# ---------- log prod 2026-08-31: câu lo ngại phải được TRẢ LỜI, giữ mạch như SOCIAL ----------


def test_cau_lo_ngai_tra_loi_tran_an_va_noi_lai_cau_dang_treo() -> None:
    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=ASK_PROFILE)
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY, concern_topic="battery"))
    assert d.action == Reply(template="concern", args={"topic": "battery"}, resume_pending=True)
    assert d.state_after.pending == ASK_PROFILE


def test_cau_lo_ngai_khong_pending_thi_khong_resume() -> None:
    state = S(stage=Stage.RECOMMENDED, intent=I.ADVISORY)
    d = decide(state, U(A.REQUEST, intent=I.ADVISORY, concern_topic="charging"))
    assert d.action == Reply(template="concern", args={"topic": "charging"}, resume_pending=False)


def test_cau_tra_loi_slot_khong_bi_nhanh_lo_ngai_nuot() -> None:
    """Bot hỏi sạc tại nhà, khách đáp "chung cư không có chỗ sạc" — đó là CÂU
    TRẢ LỜI (mang slot), phải đi đường slot như cũ chứ không bị trấn an chen."""

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY, pending=Pending(kind=K.SLOT, key="home_charging"))
    d = decide(state, U(A.SLOT_ANSWER, intent=I.ADVISORY, concern_topic="charging", slots={N.HOME_CHARGING: False}))
    assert not (isinstance(d.action, Reply) and d.action.template == "concern")


# ---------- log prod 2026-08-31: "đăng ký lái thử" khi CHƯA chốt xe bị lạc luồng ----------


def test_lai_thu_chua_co_xe_thi_cau_hoi_mang_dung_viec() -> None:
    """"Tôi muốn đăng ký lái thử" ở phiên mới → câu hỏi phải là "đặt lái thử mẫu
    nào", không phải câu của luồng thông số ("xem mẫu nào để em kể đúng phần cần")."""

    state = S(stage=Stage.COLLECTING, intent=I.ADVISORY)
    d = decide(state, U(A.REQUEST, intent=I.TEST_DRIVE))
    assert isinstance(d.action, Ask)
    assert d.action.kind is K.CHOICE and d.action.key == "vehicle"
    assert d.action.job == "đặt lái thử"
    assert d.state_after.pending is not None and d.state_after.pending.job == "đặt lái thử"
    assert d.state_after.intent is I.TEST_DRIVE


def test_tra_dia_danh_khi_dang_treo_chon_mau_lai_thu_thi_ghi_tinh_va_hoi_lai() -> None:
    """Log prod 06:53: treo "mẫu nào để lái thử", khách gõ "Hà Nội" (tưởng bot
    hỏi nơi) → lượt đó từng rơi sang Nearby/OUT_OF_SCOPE rồi văng TVV. Địa danh
    lúc này là VỊ TRÍ cho lịch lái thử: ghi slot tỉnh, hỏi lại đúng câu chọn mẫu."""

    pending = Pending(kind=K.CHOICE, key="vehicle", asked_at_turn=1)
    state = S(stage=Stage.COLLECTING, intent=I.TEST_DRIVE, pending=pending)
    d = decide(
        state,
        U(A.SLOT_ANSWER, intent=I.NEARBY, slots={N.REGISTRATION_PROVINCE: "Hà Nội"}),
    )
    assert isinstance(d.action, Ask) and d.action.key == "vehicle"
    assert d.action.job == "đặt lái thử"
    assert d.state_after.slots.get(N.REGISTRATION_PROVINCE) == "Hà Nội"
    assert d.state_after.stage is not Stage.HANDED_OFF


def test_ke_nhu_cau_khi_dang_treo_chon_mau_lai_thu_thi_vao_luong_tu_van() -> None:
    """Sếp 2026-08-31: bot hỏi "chọn được mẫu chưa hay cần em tư vấn" — khách
    kể nhu cầu thì phải VÀO luồng tư vấn (đề xuất theo nhu cầu), không hỏi lại
    câu chọn mẫu lần nữa."""

    pending = Pending(kind=K.CHOICE, key="vehicle", asked_at_turn=1)
    state = S(stage=Stage.COLLECTING, intent=I.TEST_DRIVE, pending=pending)
    d = decide(
        state,
        U(A.SLOT_ANSWER, intent=I.NONE, slots={N.BUDGET_MAX_VND: 700_000_000, N.PASSENGER_COUNT: 4}),
    )
    assert isinstance(d.action, Recommend)
    assert d.state_after.slots.get(N.BUDGET_MAX_VND) == 700_000_000


# ---------- [agent-migration] Bước 1: luật 6a không nuốt lời xin đổi xe ----------


def test_luat_6a_khong_nuot_cau_xin_doi_xe() -> None:
    """"xe khác đi" ở CHOSEN: `understand._refine_question` đã cứu câu vào
    `question`; luật 6a không được đọc lại tóm tắt chiếc khách vừa gạt đi mà
    phải đi `_advise(refine=…)` → `Recommend(REASON_REVISED)` loại bộ xe cũ."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.REQUEST, intent=I.NONE, question="xe khác đi"))
    assert isinstance(d.action, Recommend), d.action
    assert d.action.reason == REASON_REVISED
    assert d.action.refine == "xe khác đi"
    assert set(d.action.exclude_ids) == {"v1", "v2"}
    assert not (isinstance(d.action, Reply) and d.action.template == TEMPLATE_CHOSEN_SUMMARY)


def test_luat_6a_van_tom_tat_khi_cau_tra_loi_roi_khong_co_question() -> None:
    """Hành vi cũ giữ nguyên: câu trả lời rời KHÔNG mang `question` (LLM không
    chép, `_refine_question` không cứu vì có slot đổi) → vẫn `CHOSEN_SUMMARY`."""

    state = S(stage=Stage.CHOSEN, intent=I.ADVISORY, chosen_vehicle_id="v1", recommended_ids=("v1", "v2"), slots=CAR_FULL)
    d = decide(state, U(A.SLOT_ANSWER, intent=I.NONE, slots={N.REGISTRATION_PROVINCE: "HN"}))
    assert isinstance(d.action, Reply) and d.action.template == TEMPLATE_CHOSEN_SUMMARY
