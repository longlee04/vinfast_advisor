"""6 chỉ số của lõi v2 (spec mục 8) — kiểm bằng vài hàng bịa, không cần DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts import core_v2_metrics as m

T0 = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)


def row(**over: object) -> dict:
    base = {
        "session_id": "s1",
        "created_at": T0,
        "user_message": "",
        "scope_label": "IN_SCOPE",
        "terminal_reason": None,
        "payload": {},
        "prev_payload": None,
        "bot_answer": "Dạ vâng ạ.",
    }
    base.update(over)
    return base


def test_core_of_doc_khoa_core_trong_payload() -> None:
    assert m.core_of(row(payload={"core": "v2"})) == "v2"
    assert m.core_of(row(payload={"gates": {}})) == "v1"
    assert m.core_of(row(payload={})) == "v1"


def test_split_by_core_giu_thu_tu() -> None:
    rows = [row(payload={"core": "v2"}), row(payload={}), row(payload={"core": "v2"})]
    out = m.split_by_core(rows)
    assert len(out["v2"]) == 2
    assert len(out["v1"]) == 1


# --- chỉ số 1: trả lời loại xe mà bot đổ catalog -------------------------------


def test_chi_so_1_dem_dung_mau_cau_loai_xe() -> None:
    rows = [
        row(user_message="ô tô điện", bot_answer="Dạ dải sản phẩm ô tô điện VinFast gồm 7 dòng..."),
        row(user_message="Ô tô.", bot_answer="Dải sản phẩm hiện có..."),
        row(user_message="xe may dien", bot_answer="Dạ anh dùng xe để đi làm hay chở hàng ạ?"),
        row(user_message="tôi muốn xem ô tô điện", bot_answer="Dạ dải sản phẩm..."),
    ]
    metric = m.metric_1(rows)
    assert (metric.hit, metric.total) == (2, 3)
    assert round(metric.percent) == 67


def test_chi_so_1_khong_co_luot_nao_thi_khong_chia_cho_khong() -> None:
    assert m.metric_1([]).percent == 0.0


def test_chi_so_1_v2_do_catalog_va_hoi_tiep_cung_luc_khong_phai_loi() -> None:
    """Quyết định chủ sản phẩm: đổ catalog + hỏi tiếp một câu hồ sơ TRONG CÙNG
    tin nhắn là ĐÚNG — chỉ tính lỗi khi đổ catalog mà KHÔNG hỏi tiếp."""

    rows = [
        row(
            payload={
                "core": "v2",
                "pending_after": {"kind": "SLOT", "key": "purpose", "asked_at_turn": 1},
            },
            user_message="ô tô",
            bot_answer="Dạ dải sản phẩm ô tô điện gồm 7 dòng. Anh dùng để đi làm hay chở hàng ạ?",
        ),
        row(
            payload={"core": "v2", "pending_after": None},
            user_message="xe máy",
            bot_answer="Dạ dải sản phẩm xe máy điện...",
        ),
    ]
    metric = m.metric_1(rows)
    assert (metric.hit, metric.total) == (1, 2)


def test_chi_so_1_v1_do_catalog_ma_khong_treo_hoi_la_loi() -> None:
    rows = [
        row(payload={}, user_message="ô tô", bot_answer="Dải sản phẩm ô tô điện..."),
        row(
            payload={"outcome": {"has_pending_question": True}},
            user_message="xe máy",
            bot_answer="Dạ dải sản phẩm xe máy điện... Anh đi làm hay chở hàng ạ?",
        ),
    ]
    metric = m.metric_1(rows)
    assert (metric.hit, metric.total) == (1, 2)


# --- chỉ số 2: bot vừa hỏi xong thì từ chối ------------------------------------


def test_chi_so_2_v1_doc_has_pending_question() -> None:
    prev = {"outcome": {"has_pending_question": True}}
    rows = [
        row(prev_payload=prev, scope_label="OUT_OF_SCOPE", bot_answer="Dạ em xin lỗi..."),
        row(prev_payload=prev, bot_answer="Dạ em không trả lời được câu này ạ."),
        row(prev_payload=prev, bot_answer="Dạ ngân sách của anh khoảng bao nhiêu ạ?"),
        row(prev_payload={"outcome": {"has_pending_question": False}}, scope_label="OUT_OF_SCOPE"),
    ]
    metric = m.metric_2(rows)
    assert (metric.hit, metric.total) == (2, 3)


def test_chi_so_2_v2_doc_pending_after() -> None:
    prev = {"core": "v2", "pending_after": {"kind": "SLOT", "key": "purpose", "asked_at_turn": 2}}
    rows = [
        row(payload={"core": "v2"}, prev_payload=prev, bot_answer="Dạ câu này em đành chịu ạ."),
        row(payload={"core": "v2"}, prev_payload=prev, bot_answer="Dạ em ghi nhận rồi ạ."),
        row(payload={"core": "v2"}, prev_payload={"core": "v2", "pending_after": None}, scope_label="OUT_OF_SCOPE"),
    ]
    metric = m.metric_2(rows)
    assert (metric.hit, metric.total) == (1, 2)


def test_chi_so_2_bat_cum_tu_choi_giua_cau_dau() -> None:
    prev = {"outcome": {"has_pending_question": True}}
    answer = "Dạ em xin lỗi, câu này nằm ngoài phần em phụ trách. Em chỉ tư vấn dựa trên dữ liệu..."
    assert m.metric_2([row(prev_payload=prev, bot_answer=answer)]).hit == 1


def test_chi_so_2_khong_bat_cum_tu_choi_o_cuoi_bai_dai() -> None:
    prev = {"outcome": {"has_pending_question": True}}
    answer = "Dạ " + "x" * 400 + " ngoài phần em phụ trách"
    assert m.metric_2([row(prev_payload=prev, bot_answer=answer)]).hit == 0


# --- chỉ số 3: đọc lại nguyên bài đề xuất --------------------------------------


def test_chi_so_3_v1_doc_gate_post_pitch() -> None:
    gates = {"gates": {"in_post_pitch_stage": True}}
    rows = [
        row(payload=gates, user_message="xe này sạc bao lâu", bot_answer="**VinFast VF 5** giá 458 triệu..."),
        row(payload=gates, user_message="pin có bảo hành không", bot_answer="Dạ pin bảo hành 10 năm ạ."),
        row(payload=gates, user_message="cho em chọn mẫu số 1", bot_answer="**VinFast VF 3** ..."),
        row(payload={"gates": {"in_post_pitch_stage": False}}, user_message="xe này sạc bao lâu"),
    ]
    metric = m.metric_3(rows)
    assert (metric.hit, metric.total) == (1, 2)


def test_chi_so_3_v2_doc_stage_before_va_tien_to_thap_hon_ngan_sach() -> None:
    rows = [
        row(
            payload={"core": "v2", "stage_before": "CHOSEN"},
            user_message="bảo hành thế nào",
            bot_answer="(thấp hơn ngân sách) **VinFast VF 3** ...",
        ),
        row(payload={"core": "v2", "stage_before": "COLLECTING"}, user_message="bảo hành thế nào"),
    ]
    metric = m.metric_3(rows)
    assert (metric.hit, metric.total) == (1, 1)


# --- chỉ số 4: lộ enum / số thô / [n] ------------------------------------------


def test_chi_so_4_bat_enum_so_tho_va_dau_ngoac_vuong() -> None:
    rows = [
        row(bot_answer="Xe này thuộc nhóm 7_SEATER ạ."),
        row(bot_answer="Dung tích 260.00 lít ạ."),
        row(bot_answer="Theo tài liệu [1] thì pin 42 kWh."),
        row(bot_answer="Cốp 260 lít, 7 chỗ ngồi ạ."),
        row(bot_answer=None),
    ]
    metric = m.metric_4(rows)
    assert (metric.hit, metric.total) == (3, 4)


# --- cửa sổ tìm câu trả lời (nguồn của chỉ số 5, xem SQL trong fetch_rows) -----


def test_cua_so_chap_nhan_tin_bot_ghi_truoc_trace_vai_chuc_ms() -> None:
    """`conversation_messages`/`turn_traces` cùng transaction nhưng tin bot có
    thể flush trước trace ~20ms (đo thực tế trên prod) — vẫn phải tính là có trả lời."""

    message_at = T0 - timedelta(milliseconds=20)
    assert m._in_answer_window(message_at, T0, None)


def test_cua_so_tin_cua_luot_truoc_khong_tinh_vao_luot_nay() -> None:
    """Tin thuộc lượt TRƯỚC (mốc thời gian xa hơn `ANSWER_LOOKBACK`) không được
    mượn nhầm cho lượt hiện tại — chỉ nới 5 giây, không phải vô hạn."""

    message_of_prev_turn = T0 - m.ANSWER_LOOKBACK - timedelta(seconds=1)
    assert not m._in_answer_window(message_of_prev_turn, T0, None)


def test_cua_so_van_chan_boi_luot_sau() -> None:
    next_trace_at = T0 + timedelta(seconds=2)
    assert not m._in_answer_window(next_trace_at, T0, next_trace_at)


# --- chỉ số 5: lượt không có tin nhắn bot --------------------------------------


def test_chi_so_5_dem_luot_khong_co_cau_tra_loi() -> None:
    rows = [row(bot_answer=None), row(bot_answer="   "), row(bot_answer="Dạ vâng ạ.")]
    metric = m.metric_5(rows)
    assert (metric.hit, metric.total) == (2, 3)


# --- chỉ số 6: live_probe_eval --------------------------------------------------


def test_chi_so_6_khong_tut_thi_dat() -> None:
    v1 = {"turn_pass": 90, "turn_count": 100}
    v2 = {"turn_pass": 92, "turn_count": 100}
    assert m.metric_6(v1, v2).passed


def test_chi_so_6_tut_thi_do() -> None:
    v1 = {"turn_pass": 90, "turn_count": 100}
    v2 = {"turn_pass": 80, "turn_count": 100}
    assert not m.metric_6(v1, v2).passed


def test_chi_so_6_thieu_bao_cao_thi_khong_ket_luan() -> None:
    metric = m.metric_6(None, None)
    assert metric.total == 0
    assert not metric.passed


# --- bảng ------------------------------------------------------------------------


def test_render_table_co_du_6_dong_va_ca_hai_lo() -> None:
    rows_v1 = [row(user_message="ô tô", bot_answer="Dải sản phẩm...")]
    rows_v2 = [row(payload={"core": "v2"}, user_message="ô tô", bot_answer="Dạ anh đi làm hay chở hàng ạ?")]
    table = m.render_table({"v1": m.all_metrics(rows_v1, None, None), "v2": m.all_metrics(rows_v2, None, None)})
    for number in range(1, 7):
        assert f"| {number} |" in table
    assert "v1" in table and "v2" in table


def test_render_table_khong_co_du_lieu_thi_dam_gach_ngang_khong_dat_ao() -> None:
    """v2 rỗng: cell '—' và Đạt '—' cho cả 6 dòng — không mặc định ✅ khi total=0."""

    rows_v1 = [row(user_message="ô tô", bot_answer="Dải sản phẩm...")]
    table = m.render_table({"v1": m.all_metrics(rows_v1, None, None), "v2": m.all_metrics([], None, None)})
    data_lines = table.splitlines()[2:]
    assert len(data_lines) == 6
    for line in data_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        v2_cell, verdict = cells[3], cells[-1]
        assert v2_cell == "—"
        assert verdict == "—"


# ------------------------------------------------------------ đợt 9: KPI theo đích


def session(**over: object) -> dict:
    base = {"session_id": "s", "ownership": "AI", "chosen_vehicle_id": None, "has_booking": False, "turns": []}
    base.update(over)
    return base


def test_kpi_dich_tinh_ty_le_chon_xe_va_booking() -> None:
    sessions = [
        session(chosen_vehicle_id="v1", has_booking=True),
        session(chosen_vehicle_id="v2"),
        session(),
        session(),
    ]
    chosen, booked, _avg, _handed = m.goal_kpis(sessions)
    assert (chosen.hit, chosen.total) == (2, 4)
    assert (booked.hit, booked.total) == (1, 4)
    assert chosen.cell() == "2/4 = 50%"


def test_kpi_dich_so_luot_toi_lan_chon_xe_dau() -> None:
    turns_a = [{"stage_after": "COLLECTING"}, {"stage_after": "RECOMMENDED"}, {"stage_after": "CHOSEN"}]
    turns_b = [{"stage_after": "CHOSEN"}, {"stage_after": "COSTING"}]
    never = [{"stage_after": "COLLECTING"}]
    assert m.turns_to_first_choice(turns_a) == 3
    assert m.turns_to_first_choice(turns_b) == 1
    assert m.turns_to_first_choice(never) is None
    avg = m.goal_kpis([session(turns=turns_a), session(turns=turns_b), session(turns=never)])[2]
    assert avg.average == 2.0 and avg.total == 2
    assert avg.cell() == "2.0 lượt (n=2)"


def test_kpi_dich_roi_vao_tvv_theo_ownership_hoac_vet_handoff() -> None:
    sessions = [
        session(ownership="PENDING_HANDOFF"),
        session(ownership="HUMAN"),
        session(ownership="AI", turns=[{"action": "Ask"}, {"action": "Handoff"}]),
        session(ownership="AI", turns=[{"action": "Recommend"}]),
    ]
    handed = m.goal_kpis(sessions)[3]
    assert (handed.hit, handed.total) == (3, 4)


def test_kpi_dich_khong_co_phien_thi_gach_ngang() -> None:
    table = m.render_goal_table(m.goal_kpis([]))
    assert table.count("| — |") == 4
    assert "Phiên có chọn xe" in table and "Phiên rơi vào TVV" in table
