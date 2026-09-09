"""Mọi chữ lõi v2 trả khách đi qua đây; cấm enum thô, số .00, dấu [n] (spec mục 7)."""

from __future__ import annotations

import pytest

from src.agents.core.actions import FIT_PARTIAL, FIT_YES, Ask, Reply
from src.agents.core.render import (
    SLOT_QUESTIONS,
    FallbackVehicle,
    RenderError,
    assert_clean,
    compare_fit_lead,
    fit_assessment,
    format_number,
    need_lead,
    next_steps,
    recommend_fallback,
    relax_lead,
    render_ask,
    render_reply,
    render_resume,
)
from src.agents.core.state import Pending
from src.agents.core.state import PendingKind as K


@pytest.mark.parametrize(
    "bad",
    [
        "chọn 7_SEATER nhé",
        "260.00 lít",
        "tầm chạy 500.00 km [1]",
        "xem [2] nhé",
        "chọn __lichlaithu__ nhé",
        "đặt lịch showroom_slot nhé",
    ],
)
def test_bo_loc_cam(bad: str) -> None:
    with pytest.raises(RenderError):
        assert_clean(bad)


@pytest.mark.parametrize("ok", ["xe bảy chỗ", "260 lít", "khoảng 1 tỷ", "VF 8 Plus"])
def test_bo_loc_cho_qua(ok: str) -> None:
    assert assert_clean(ok) == ok


@pytest.mark.parametrize(
    ("value", "unit", "expect"),
    [
        (260.0, "lít", "260 lít"),
        (1_000_000_000, "đ", "1 tỷ"),
        (896_000_000, "đ", "896 triệu"),
        (215.0, "km", "215 km"),
        (18.3, "kWh", "18,3 kWh"),
    ],
)
def test_format_number(value: float, unit: str, expect: str) -> None:
    assert format_number(value, unit) == expect


def test_moi_slot_co_cau_hoi() -> None:
    for key in (
        "vehicle_type",
        "budget_max_vnd",
        "purpose",
        "passenger_count",
        "required_range_km",
        "habit_need_tags",
        "registration_province",
    ):
        assert key in SLOT_QUESTIONS


def test_render_ask_slot_mot_cau_mot_dau_hoi() -> None:
    text = render_ask(Ask(key="purpose", kind=K.SLOT, options=("đi làm", "giao hàng", "đi cá nhân")))
    assert text.count("?") == 1
    assert "đi làm" in text and "giao hàng" in text
    assert_clean(text)


def test_render_ask_feature_dich_nhan() -> None:
    text = render_ask(Ask(key="habit_need_tags", kind=K.SLOT, options=("7_SEATER", "ADAS")))
    assert "7_SEATER" not in text
    assert "bảy chỗ" in text.lower()
    assert_clean(text)


def test_render_ask_choice_danh_so_toi_da_3() -> None:
    text = render_ask(Ask(key="vehicle", kind=K.CHOICE, options=("VF 5", "VF 6", "VF 7", "VF 8")))
    assert "1. VF 5" in text and "3. VF 7" in text and "VF 8" not in text
    assert_clean(text)


def test_render_ask_confirm() -> None:
    text = render_ask(Ask(key="book", kind=K.CONFIRM, options=("lái thử VF 8 lúc 9:00 30/08 tại VinFast HTA",)))
    assert "lái thử VF 8" in text and text.rstrip().endswith("?")


def test_render_ask_confirm_token_nut_chua_nhan_hoa_bi_chan() -> None:
    raw = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    with pytest.raises(RenderError):
        render_ask(Ask(key="book", kind=K.CONFIRM, options=(raw,)))


def test_render_ask_confirm_uu_tien_labels() -> None:
    # Item 1: nhãn khách đọc được (tầng act điền) phải được ưu tiên trước option thô.
    raw = "__lichlaithu__|2026-08-30T09:00:00+07:00|VinFast HTA"
    nhan = "lái thử VF 8 lúc 9:00 30/08 tại VinFast HTA"
    text = render_ask(Ask(key="book", kind=K.CONFIRM, options=(raw,), labels=(nhan,)))
    assert nhan in text
    assert "__lichlaithu__" not in text
    assert_clean(text)


@pytest.mark.parametrize(
    "key",
    (
        "vehicle_type",
        "budget_max_vnd",
        "purpose",
        "passenger_count",
        "required_range_km",
        "habit_need_tags",
        "registration_province",
    ),
)
def test_render_ask_slot_khong_options_mot_dau_hoi_khong_lap_a(key: str) -> None:
    text = render_ask(Ask(key=key, kind=K.SLOT, options=()))
    assert text.count("?") == 1
    assert "ạ ạ" not in text
    assert_clean(text)


def test_render_ask_choice_uu_tien_labels() -> None:
    # I4: options là id thô của xe; nhãn khách đọc được nằm ở `labels` (tầng act điền).
    text = render_ask(
        Ask(
            key="vehicle",
            kind=K.CHOICE,
            options=("3f2504e0-4f89-11d3-9a0c-0305e82c3301", "b1c2d3e4-1111-2222-3333-444455556666"),
            labels=("VF 5 Plus", "VF 6 S"),
        )
    )
    assert "VF 5 Plus" in text and "VF 6 S" in text
    assert "3f2504e0" not in text
    assert_clean(text)


def test_render_ask_choice_id_tho_khong_co_nhan_thi_bao_loi() -> None:
    with pytest.raises(RenderError):
        render_ask(Ask(key="vehicle", kind=K.CHOICE, options=("3f2504e0-4f89-11d3-9a0c-0305e82c3301",)))


def test_render_ask_choice_khong_option_thi_hoi_ten_mau() -> None:
    text = render_ask(Ask(key="vehicle", kind=K.CHOICE))
    assert text.count("?") == 1
    assert "tên mẫu" in text
    assert_clean(text)


def test_render_ask_bo_ma_la_thay_vi_doc_tho() -> None:
    # I5: mã không dịch được thì BỎ, không đọc nguyên mã cho khách.
    text = render_ask(Ask(key="habit_need_tags", kind=K.SLOT, options=("7_SEATER", "XYZ_UNKNOWN")))
    assert "bảy chỗ" in text.lower()
    assert "XYZ" not in text
    vi_du = [x.strip() for x in text.split("ví dụ", 1)[1].rstrip("?").split(",")]
    assert vi_du == ["bảy chỗ"]
    assert_clean(text)


def test_render_ask_bo_het_ma_la_thi_hoi_khong_vi_du() -> None:
    text = render_ask(Ask(key="habit_need_tags", kind=K.SLOT, options=("XYZ_UNKNOWN",)))
    assert "ví dụ" not in text
    assert text.count("?") == 1
    assert_clean(text)


def test_render_ask_ma_chu_thuong_gach_duoi_khong_dich_duoc_bi_chan() -> None:
    # Item 3: `_label` không dịch được mã chữ thường có gạch dưới thì GIỮ NGUYÊN
    # (coi như chữ khách nói) — assert_clean phải chặn nó ở cửa cuối cùng.
    with pytest.raises(RenderError):
        render_ask(Ask(key="habit_need_tags", kind=K.SLOT, options=("toa_do_gps",)))


def test_render_reply_template_la_thi_bao_loi() -> None:
    # I8: không im lặng nuốt template lạ thành câu xã giao.
    with pytest.raises(RenderError):
        render_reply(Reply(template="khong_ton_tai"))


def test_render_resume_khung_gio_hoi_dung_viec() -> None:
    out = render_resume("Giá lăn bánh khoảng 1,2 tỷ.", Pending(kind=K.CHOICE, key="showroom_slot"))
    assert "mẫu nào" not in out
    assert "showroom" in out.lower() or "khung giờ" in out.lower()
    assert_clean(out)


def test_render_reply_chosen_summary_can_ten_xe() -> None:
    text = render_reply(Reply(template="chosen_summary", args={"vehicle_id": "v1"}), vehicle_name="VinFast VF 8 Plus")
    assert "VF 8 Plus" in text
    assert "lái thử" not in text.lower()  # không tự chèn câu mẫu
    assert_clean(text)


@pytest.mark.parametrize("stage", ["COLLECTING", "RECOMMENDED", "CHOSEN", "SCHEDULING"])
def test_render_reply_clarify_theo_chang(stage: str) -> None:
    text = render_reply(Reply(template="clarify", args={"stage": stage}))
    assert text.rstrip().endswith("?")
    assert "OUT_OF_SCOPE" not in text
    assert_clean(text)


def test_render_resume_noi_cau_hoi_treo() -> None:
    out = render_resume("VF 8 có tầm chạy 471 km.", Pending(kind=K.SLOT, key="purpose", options=("đi làm",)))
    assert out.startswith("VF 8 có tầm chạy 471 km.")
    assert "Quay lại câu lúc nãy" in out
    assert "đi làm" in out


def test_render_resume_khong_pending_giu_nguyen() -> None:
    assert render_resume("abc", None) == "abc"


def test_render_reply_khong_bao_gio_tra_chuoi_rong() -> None:
    for template in ("social", "cancelled", "clarify", "chosen_summary"):
        assert render_reply(Reply(template=template, args={"stage": "CHOSEN"}), vehicle_name="VF 3").strip()


# --------------------------------------------------------------- C2 / C3


@pytest.mark.parametrize(
    "dirty",
    [
        "VF 8 có giá 1,2 tỷ [1].",
        "Dung tích cốp 260.00 lít.",
        "Xe dùng pin lfp_battery.",
    ],
)
def test_render_resume_khong_soi_cau_tra_loi_cua_service_cu(dirty: str) -> None:
    """`main` là `answer` của service cũ — miễn `assert_clean` (global constraints).

    Soi cả `main` là mất CẢ câu trả lời LẪN câu hỏi treo: đúng chỉ số 2 spec mục 8.
    """

    out = render_resume(dirty, Pending(kind=K.SLOT, key="purpose"))
    assert out.startswith(dirty)
    assert "Quay lại câu lúc nãy" in out


def test_render_resume_van_chan_chu_cam_trong_cau_treo() -> None:
    with pytest.raises(RenderError):
        render_resume("Câu trả lời sạch.", Pending(kind=K.SLOT, key="habit_need_tags", options=("toa_do_gps",)))


def test_render_ask_confirm_id_tho_khong_co_nhan_thi_bao_loi() -> None:
    with pytest.raises(RenderError):
        render_ask(Ask(key="offer", kind=K.CONFIRM, options=("3f2504e0-4f89-11d3-9a0c-0305e82c3301",)))


def test_confirm_offer_label_khong_bao_gio_tra_ma_may() -> None:
    from src.agents.core.render import confirm_offer_label

    assert "VinFast VF 5" in confirm_offer_label("VinFast VF 5")
    assert confirm_offer_label("").strip()


# ---------- bước 6: lời chào đầu phải nói rõ giúp được gì ----------


def test_social_o_greeting_la_loi_chao_day_du() -> None:
    from src.agents.core.actions import TEMPLATE_SOCIAL

    text = render_reply(Reply(template=TEMPLATE_SOCIAL, args={"stage": "GREETING"}))
    assert "chào" in text.lower()
    assert "chọn xe theo nhu cầu" in text
    assert "chi phí sử dụng" in text
    assert text.count("?") == 1


def test_social_giua_chung_van_dap_ngan() -> None:
    from src.agents.core.actions import TEMPLATE_SOCIAL

    ngan = "Dạ em nghe anh/chị ạ."
    assert render_reply(Reply(template=TEMPLATE_SOCIAL, args={"stage": "COLLECTING"}, resume_pending=True)) == ngan
    assert render_reply(Reply(template=TEMPLATE_SOCIAL, args={"stage": "CHOSEN"})) == ngan


# ------------------------------------------------------- bug prod 2026-08-29
# `Recommendation.reasons` là chuỗi `ScoringReason.render()` thô ("[slot=
# vehicle_type] Đúng loại phương tiện..."), không phải chữ khách đọc được.
# `recommend_fallback`/`need_lead` từng nối THẲNG chuỗi này vào câu trả khách,
# `assert_clean` thấy token "vehicle_type" và ném lỗi, cả lượt rơi về câu an
# toàn ("act hong"). Sửa: mọi reason/claim phải qua bộ từ vựng
# `claim_policy.plan_claims` trước khi vào câu, và mảnh nào không dịch được
# thì BỎ chứ không giữ nguyên.


def test_recommend_fallback_dich_reason_tho_sang_tieng_viet() -> None:
    text = recommend_fallback(
        (
            FallbackVehicle(
                name="VinFast VF 6 Plus",
                reasons=(
                    "[slot=vehicle_type] Đúng loại phương tiện đã chọn",
                    "[slot=budget_max_vnd] Giá nằm trong ngân sách đã xác nhận",
                ),
            ),
        )
    )
    assert "VinFast VF 6 Plus" in text
    assert "vehicle_type" not in text
    assert "[slot=" not in text
    # Claim loại xe là chữ độn (đợt 8): bỏ, chỉ còn lý do có nội dung.
    assert "dòng xe" not in text and "Quý khách" not in text
    # Claim ngân sách giữ nguyên nội dung, chỉ đổi giọng về anh/chị.
    assert "hợp vì có giá nằm trong ngân sách anh/chị dự tính" in text


def test_recommend_fallback_bo_claim_placeholder_khong_dich_duoc() -> None:
    text = recommend_fallback(
        (
            FallbackVehicle(
                name="VinFast VF 6 Plus",
                reasons=(
                    "[slot=vehicle_type] Đúng loại phương tiện đã chọn",
                    "{CLAIM_BLIND_SPOT}",
                ),
            ),
        )
    )
    assert "VinFast VF 6 Plus" in text
    assert "{CLAIM" not in text
    assert "BLIND_SPOT" not in text
    # assert_clean đã chạy bên trong recommend_fallback — không ném là đủ chứng
    # minh chuỗi cuối cùng sạch, nhưng gọi lại tường minh cho rõ ý định test.
    assert_clean(text)


def test_recommend_fallback_ca_hai_reason_khong_dich_duoc_thi_khong_co_ve_hop_vi() -> None:
    text = recommend_fallback((FallbackVehicle(name="VinFast VF 6 Plus", reasons=("{CLAIM_MOT_MA_LA}",)),))
    assert "VinFast VF 6 Plus" in text
    assert "hợp vì" not in text
    assert "{CLAIM" not in text


def test_need_lead_dich_reason_tho_sang_tieng_viet() -> None:
    text = need_lead(
        purpose="đi làm",
        passenger_count=None,
        vehicle_name="VinFast VF 6 Plus",
        reason="[slot=vehicle_type] Đúng loại phương tiện đã chọn",
    )
    assert "VinFast VF 6 Plus" in text
    assert "vehicle_type" not in text
    assert "[slot=" not in text


def test_need_lead_reason_khong_dich_duoc_thi_roi_ve_cau_sat_nhat() -> None:
    text = need_lead(
        purpose="đi làm",
        passenger_count=None,
        vehicle_name="VinFast VF 6 Plus",
        reason="{CLAIM_MOT_MA_LA}",
    )
    assert "VinFast VF 6 Plus" in text
    assert "{CLAIM" not in text
    assert "là mẫu sát nhất" in text


def test_fit_assessment_vua_ghi_nhan_lua_chon_vua_tra_loi_cau_hoi() -> None:
    text = fit_assessment(
        vehicle_name="VinFast VF 3",
        verdict=FIT_PARTIAL,
        reasons=("tầm chạy 210 km mỗi lần sạc, đi chơi xa sẽ phải sạc giữa đường",),
        alternative_name="VinFast VF 5",
        just_chosen=True,
    )
    assert "em ghi nhận anh/chị chọn VinFast VF 3" in text
    assert FIT_PARTIAL in text
    assert "210 km" in text
    assert "VinFast VF 5" in text


def test_fit_assessment_hop_thi_moi_di_tiep_chu_khong_moi_doi_mau() -> None:
    text = fit_assessment(vehicle_name="VinFast VF 5", verdict=FIT_YES, reasons=("xe 5 chỗ, đủ cho 4 người nhà mình",))
    assert "chi phí sử dụng" in text
    assert "mẫu khác" not in text


def test_fit_assessment_chua_hop_ma_khong_co_mau_thay_the_thi_hoi_tim_them() -> None:
    text = fit_assessment(
        vehicle_name="VinFast VF 3",
        verdict=FIT_PARTIAL,
        reasons=("giá từ 300 triệu, cao hơn mức 200 triệu anh/chị dự tính",),
    )
    assert "tìm mẫu khác" in text


def test_compare_fit_lead_noi_ro_mau_nao_hop_hon_va_vi_sao() -> None:
    text = compare_fit_lead(
        better_name="VinFast VF 5",
        better_reasons=("xe 5 chỗ, đủ cho 4 người nhà mình", "tầm chạy 326 km mỗi lần sạc, đi chơi xa vẫn thoải mái"),
        other_name="VinFast VF 3",
    )
    assert "VinFast VF 5 hợp hơn VinFast VF 3" in text
    assert "326 km" in text


def test_compare_fit_lead_ngang_nhau_thi_khong_bia_ra_ke_thang() -> None:
    text = compare_fit_lead(better_name="VinFast VF 5", better_reasons=(), other_name="VinFast VF 3", tie=True)
    assert "ngang nhau" in text
    assert "hợp hơn" not in text


def test_next_steps_ke_dung_viec_he_lam_duoc() -> None:
    text = next_steps("VinFast VF 3")
    assert "để chốt VinFast VF 3" in text
    assert "lái thử" in text
    assert "tư vấn viên" in text
    assert "showroom" in text


def test_tco_summary_nhac_lai_so_km_khach_neu() -> None:
    from src.agents.core.render import tco_summary

    # Sếp 2026-08-31: mọi nhánh đều dẫn về THẺ, không lặp lại số km trong chữ.
    text = tco_summary(vehicle_name="VinFast VF 5", total_text="600 triệu", daily_km=60)
    assert "chỉnh khu vực và số km" in text
    assert "tạm tính" not in text


# ---------- đợt 8: lõi v2 xưng anh/chị, câu dẫn không được là chữ độn ----------


def test_assert_clean_cam_xung_quy_khach() -> None:
    """Toàn lõi v2 xưng anh/chị. "Quý khách" là giọng của nhánh cũ (claim_policy,
    reaction_policy) — lọt vào chữ lõi v2 là hai giọng trong một hội thoại."""

    with pytest.raises(RenderError):
        assert_clean("xe này thuộc đúng dòng xe Quý khách đang tìm")


def test_need_lead_khong_in_claim_dong_xe_va_dung_so_that() -> None:
    """Prod benchmark2: "Với nhu cầu đi rạo, VinFast VF 3 All New hợp vì thuộc
    đúng dòng xe Quý khách đang tìm." lặp cho cả ba xe. Claim `vehicle_type` là
    chữ độn (xe nào trong danh sách cũng "đúng dòng"); không có lý do thật thì
    câu dẫn phải nói bằng SỐ của chính chiếc xe đó."""

    text = need_lead(
        purpose="đi rạo",
        passenger_count=None,
        vehicle_name="VinFast VF 3 All New",
        reason="[slot=vehicle_type] Đúng loại phương tiện CAR đã chọn",
        facts=("từ 278 triệu", "4 chỗ", "~215 km mỗi lần sạc"),
    )
    assert "Quý khách" not in text
    assert "dòng xe" not in text
    assert "278 triệu" in text and "4 chỗ" in text and "215 km" in text
    assert text.startswith("Với nhu cầu đi rạo, VinFast VF 3 All New")


def test_spec_facts_dung_dinh_dang_khach_doc() -> None:
    from src.agents.core.render import spec_facts

    assert spec_facts(price_vnd=278_000_000, seats=4, range_km=215) == ("từ 278 triệu", "4 chỗ", "~215 km mỗi lần sạc")
    # Thiếu số nào thì bỏ số đó, không in "None".
    assert spec_facts(price_vnd=None, seats=None, range_km=None) == ()


def test_spec_answer_tra_dung_mot_cot() -> None:
    from decimal import Decimal

    from src.agents.core.render import spec_answer

    specs = {"fast_charge_time_minutes": Decimal("30.00"), "battery_capacity_kwh": Decimal("37.230"), "range_km": 326}
    text = spec_answer(vehicle_name="VinFast VF 5", question="sạc bao lâu", specs=specs)
    assert text is not None
    assert "30 phút" in text and "37,23 kWh" in text
    assert "326" not in text
    assert spec_answer(vehicle_name="VinFast VF 5", question="bảo hành mấy năm", specs=specs) is None


def test_spec_answer_doc_chuoi_so_tu_db() -> None:
    from src.agents.core.render import spec_answer

    text = spec_answer(
        vehicle_name="VinFast VF 5",
        question="sạc bao lâu",
        specs={"fast_charge_time_minutes": "30", "battery_capacity_kwh": "37.230"},
    )
    assert text and "30 phút" in text and "37,23 kWh" in text


# ------------------------------------------------------------ đợt 9: câu kết theo checklist


def _core(**kw):
    from src.agents.core.state import CoreState

    return CoreState(session_id="s1", **kw)


def test_closing_chua_chot_co_de_xuat_thi_hoi_ung_xe_dau_hay_so_voi_xe_hai() -> None:
    from src.agents.core.render import closing_question

    state = _core(recommended_ids=("a", "b"))
    text = closing_question(
        state, vehicle_name="", has_tco=False, has_booking=False, recommended_names=("VinFast VF 5", "VinFast VF 6")
    )
    assert text == "Anh/chị ưng VinFast VF 5 không, hay để em so với VinFast VF 6 cho dễ quyết?"


def test_closing_da_chot_chua_tco_thi_moi_ba_viec() -> None:
    from src.agents.core.render import closing_question

    text = closing_question(_core(chosen_vehicle_id="a"), vehicle_name="VinFast VF 5", has_tco=False, has_booking=False)
    assert (
        text
        == "Để rõ tổng tiền trước khi quyết: anh/chị muốn xem chi phí 5 năm, giá lăn bánh, hay đặt lái thử VinFast VF 5?"
    )


def test_closing_da_tco_chua_lich_thi_moi_lai_thu() -> None:
    from src.agents.core.render import closing_question

    text = closing_question(_core(chosen_vehicle_id="a"), vehicle_name="VinFast VF 5", has_tco=True, has_booking=False)
    assert text == "Đặt lái thử VinFast VF 5 luôn để cảm nhận thật nhé, hay anh/chị muốn xem giá lăn bánh trước?"


def test_closing_da_co_lich_thi_khong_moi_lai_thu_nua() -> None:
    from src.agents.core.render import closing_question

    text = closing_question(_core(chosen_vehicle_id="a"), vehicle_name="VinFast VF 5", has_tco=True, has_booking=True)
    assert text == "Lịch đã xếp; anh/chị cần hỏi thêm gì về VinFast VF 5 trước ngày lái thử không?"


def test_cac_cau_tra_loi_khong_con_cau_ket_mo_khi_co_closing() -> None:
    from src.agents.core.render import closing_question, spec_answer, tco_summary

    closing = closing_question(
        _core(chosen_vehicle_id="a"), vehicle_name="VinFast VF 5", has_tco=False, has_booking=False
    )
    spec = spec_answer(
        vehicle_name="VinFast VF 5", question="sạc bao lâu", specs={"charging_time_minutes": "30"}, closing=closing
    )
    assert spec and spec.endswith(closing) and "nói thêm gì" not in spec
    tco = tco_summary(vehicle_name="VinFast VF 5", total_text="600 triệu", daily_km=60, closing=closing)
    assert tco.endswith(closing) and "số km khác" not in tco
    same = render_reply(Reply(template="same_pick"), vehicle_name="VinFast VF 5", closing=closing)
    assert same.endswith(closing)
    fit = fit_assessment(vehicle_name="VinFast VF 5", verdict=FIT_YES, reasons=("đủ chỗ",), closing=closing)
    assert fit.endswith(closing)


def test_spec_answer_xe_may_dien_doc_cot_motorbikes() -> None:
    from src.agents.core.render import spec_answer

    specs = {"range_max_km": "262.00", "license_requirement": "A1", "seat_height_mm": "770.00", "range_km": None}
    text = spec_answer(vehicle_name="VinFast Evo Grand", question="Evo đi được bao xa", specs=specs)
    assert text and "262 km" in text
    text = spec_answer(vehicle_name="VinFast Evo Grand", question="cần bằng lái gì", specs=specs)
    assert text and "A1" in text


def test_closing_question_sau_gia_lan_banh_khong_moi_lai_gia_lan_banh() -> None:
    from src.agents.core.render import closing_question
    from src.agents.core.state import CoreState, Stage

    state = CoreState(session_id="s", stage=Stage.CHOSEN, chosen_vehicle_id="v1")
    text = closing_question(state, vehicle_name="VinFast VF 5", has_tco=False, has_booking=False, after_on_road=True)
    assert "lăn bánh" not in text and "chi phí 5 năm" in text and "lái thử" in text


def test_spec_answer_kem_danh_gia_va_cau_ket_khong_lai_sang_tien() -> None:
    from src.agents.core.render import qa_follow_up, spec_answer

    text = spec_answer(
        vehicle_name="VinFast VF 7 All New",
        question="cốp có rộng không tại anh chở khá nhiều đồ",
        specs={"cargo_volume_standard_l": "446.00"},
        closing=qa_follow_up("VinFast VF 7 All New"),
    )
    assert text is not None
    assert "446 lít" in text and "rộng rãi" in text  # con số + lời đánh giá
    assert "chi phí" not in text and "lăn bánh" not in text  # không lái sang tiền
    assert "băn khoăn điểm nào" in text

    hep = spec_answer(vehicle_name="VF 3", question="cốp rộng không", specs={"cargo_volume_standard_l": "285"})
    assert hep is not None and "gập" in hep
    pho = spec_answer(vehicle_name="VF 3", question="đi được bao xa", specs={"range_km": "215"})
    assert pho is not None and "đi phố" in pho


def test_chosen_intro_gioi_thieu_xe_khong_hoi_nhu_cau() -> None:
    """Chọn xe khan → giới thiệu dòng xe + nhóm người điển hình, KHÔNG hỏi nhu cầu."""
    from src.agents.core.render import chosen_intro

    text = chosen_intro(vehicle_name="VinFast VF 6 Eco", specs={"body_type": "SUV", "seat_count": 5, "range_km": 460})
    assert text is not None
    assert "SUV" in text and "460" in text
    assert "gia đình" in text
    assert "nhu cầu của anh/chị" not in text  # KHONG bia hop-nhu-cau khi khach chua ke


def test_chosen_intro_thieu_du_lieu_tra_none() -> None:
    from src.agents.core.render import chosen_intro

    assert chosen_intro(vehicle_name="X", specs={}) is None


# ---------- bug prod 2026-08-31: relax bỏ tầm chạy phải NÓI THẲNG ----------


def test_relax_lead_noi_thang_thieu_tam_chay_va_moi_noi_ngan_sach() -> None:
    """Bậc nới là TẦM CHẠY của nhu cầu đi xa mà câu dẫn đọc "bỏ bớt các tiêu chí
    phụ" là giấu khách sự thật (Sếp 2026-08-31). Phải nói cần ~bao nhiêu km,
    trong ngân sách chưa có mẫu đạt, và mời nới ngân sách."""

    text = relax_lead(
        ["budget", "budget", "range"],
        budget_vnd=200_000_000,
        widened_vnd=280_000_000,
        required_range_km=300,
    )
    assert "tầm chạy" in text
    assert "300 km" in text
    assert "nới thêm ngân sách" in text
    assert "tiêu chí phụ" not in text


def test_relax_lead_khong_co_bac_range_thi_cau_cu_giu_nguyen() -> None:
    text = relax_lead(["budget"], budget_vnd=300_000_000, widened_vnd=360_000_000, required_range_km=300)
    assert "tầm chạy" not in text
    assert "nới ngân sách lên khoảng 360 triệu" in text


# ---------- câu trấn an lo ngại (log prod 2026-08-31) ----------


def test_render_concern_theo_chu_de_khong_so_lieu() -> None:
    from src.agents.core.actions import TEMPLATE_CONCERN

    battery = render_reply(Reply(template=TEMPLATE_CONCERN, args={"topic": "battery"}))
    assert "bảo hành" in battery
    charging = render_reply(Reply(template=TEMPLATE_CONCERN, args={"topic": "charging"}))
    assert "trạm sạc" in charging
    # Không bịa con số nào — mọi chữ số trong câu trấn an là số bịa.
    for text in (battery, charging):
        assert not any(ch.isdigit() for ch in text)


def test_render_concern_resume_thi_khong_ket_bang_cau_hoi_mo() -> None:
    from src.agents.core.actions import TEMPLATE_CONCERN

    resumed = render_reply(Reply(template=TEMPLATE_CONCERN, args={"topic": "general"}, resume_pending=True))
    standalone = render_reply(Reply(template=TEMPLATE_CONCERN, args={"topic": "general"}))
    assert not resumed.rstrip().endswith("?")
    assert standalone.rstrip().endswith("?")


def test_cau_hoi_chon_mau_lai_thu_moi_ke_nhu_cau_khi_chua_co_mau(  ) -> None:
    from src.agents.core.state import PendingKind

    # Sếp 2026-08-31: "phải hỏi kiểu khác — chọn được mẫu chưa, hay cung cấp
    # nhu cầu để em tư vấn". Chưa có danh sách nào để bày thì mở CẢ HAI lối.
    text = render_ask(Ask(key="vehicle", kind=PendingKind.CHOICE, job="đặt lái thử"))
    assert "chọn được mẫu" in text
    assert "nhu cầu" in text and "tư vấn" in text
    # Có danh sách đề xuất thì bày danh sách + vẫn mở lối kể nhu cầu.
    listed = render_ask(
        Ask(key="vehicle", kind=PendingKind.CHOICE, job="đặt lái thử", options=("a", "b"), labels=("VF 5", "VF 6"))
    )
    assert "đặt lái thử mẫu nào" in listed and "VF 5" in listed and "nhu cầu" in listed
    # Không có việc đính kèm thì giữ nguyên câu cũ của luồng thông số.
    assert "kể đúng phần cần" in render_ask(Ask(key="vehicle", kind=PendingKind.CHOICE))


def test_booking_confirmed_cam_on_va_chi_duong_google_maps() -> None:
    from src.agents.core.render import booking_confirmed

    text = booking_confirmed("lái thử VinFast VF 5 lúc 09:00 ngày 01/09 tại VinFast VGC Phúc Yên", showroom="VinFast VGC Phúc Yên")
    assert "cảm ơn" in text.casefold()
    # Dạng BẢNG dòng (Sếp 2026-08-31): xe / thời gian / showroom / vị trí click được.
    assert "**Xe lái thử**: VinFast VF 5" in text
    assert "**Thời gian**: 09:00 ngày 01/09" in text
    assert "**Showroom**: VinFast VGC Phúc Yên" in text
    # Link NỘI BỘ về trang bản đồ với ô tìm điền sẵn — trong đó có nút Chỉ
    # đường mở Google Maps theo toạ độ thật (Sếp 2026-08-31).
    assert "(/locations?q=VinFast%20VGC%20Ph" in text
    # Không có showroom (dữ liệu thiếu) vẫn cảm ơn, không link gãy.
    plain = booking_confirmed("lái thử VinFast VF 5", showroom="")
    assert "cảm ơn" in plain.casefold() and "/locations" not in plain


def test_resume_cau_treo_giu_dung_khung_viec() -> None:
    """Prod 2026-08-31: khách chen "xem chi tiết vf5 đã" giữa lúc treo câu chọn
    mẫu LÁI THỬ — câu "Quay lại câu lúc nãy" đọc lại câu luồng thông số vì
    Pending không mang job. Nối lại phải vẫn là câu lái thử hai lối."""

    from src.agents.core.render import render_resume
    from src.agents.core.state import Pending, PendingKind

    text = render_resume("Em mở chi tiết bên cạnh ạ.", Pending(kind=PendingKind.CHOICE, key="vehicle", job="đặt lái thử"))
    assert "chọn được mẫu" in text and "đặt lái thử" in text
    assert "kể đúng phần cần" not in text
