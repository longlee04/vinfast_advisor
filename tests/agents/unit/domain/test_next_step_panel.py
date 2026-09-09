"""Panel "Bước tiếp theo" — DỮ LIỆU TRÌNH BÀY, không phải một chặng.

Sếp 2026-08-28 chốt: `VEHICLE_DETAILS_SHOWN` và `TEST_DRIVE_CTA` là **màn hình**,
không phải trạng thái cần TTL, revision và compare-before-write. Phiên
2026-08-28 đã vá NĂM lỗi quanh `PostPitchStage`, mỗi lỗi cùng một hình dạng:
*chặng tiến lên nhưng bước sau không có gì để làm việc*. Thêm chặng mới vào đó là
viết lại thứ vừa mới ổn định.

Luật mở thẻ đặt lịch, chốt sau hai vòng phản biện:

    KHÔNG mở thẻ trước khi khách nhận lời.
    Khách ĐÃ xin hoặc ĐÃ nhận lời  →  mở luồng ngay.

Tương thích với quyết định 2026-08-26 (*"nối luôn đăng ký lái thử"*): thẻ vẫn
hiện ngay khi khách nhận lời, chỉ không tự bật sau bảng chi phí khi khách chưa
nói gì.
"""

from __future__ import annotations

from src.agents.domain.next_step import NextStepAction, build_next_step_panel
from src.agents.domain.post_pitch import PostPitchStage


def test_sau_khi_xem_xe_thi_moi_ba_viec_khong_ep_lai_thu() -> None:
    """Chưa có chi phí thì lái thử chưa phải bước tự nhiên kế tiếp."""

    panel = build_next_step_panel(stage=PostPitchStage.AWAITING_DECISION, cost_shown=False)

    assert panel is not None
    actions = [action.action for action in panel.actions]
    assert NextStepAction.ON_ROAD_PRICE in actions
    assert NextStepAction.TEST_DRIVE not in actions


def test_sau_khi_co_chi_phi_moi_moi_lai_thu() -> None:
    """Khách đã biết tốn bao nhiêu — chỗ tự nhiên nhất để mời cầm lái."""

    panel = build_next_step_panel(stage=PostPitchStage.AWAITING_DECISION, cost_shown=True)

    assert panel is not None
    assert panel.actions[0].action is NextStepAction.TEST_DRIVE
    assert panel.actions[0].primary is True


def test_luon_co_mot_loi_ra_ngang_hang_de_hoi_them() -> None:
    """Ngang hàng về QUYỀN CHỌN, không ngang hàng về thứ bậc thị giác.

    "Tôi muốn hỏi thêm" phải là một lựa chọn RÕ, không bị làm mờ hay đặt xa —
    nhưng nó là `secondary`, không cạnh tranh với việc chính.
    """

    panel = build_next_step_panel(stage=PostPitchStage.AWAITING_DECISION, cost_shown=True)

    assert panel is not None
    secondary = [action for action in panel.actions if not action.primary]
    assert any(action.action is NextStepAction.ASK_MORE for action in secondary)


def test_dung_mot_viec_chinh_khong_bay_nam_nut() -> None:
    panel = build_next_step_panel(stage=PostPitchStage.AWAITING_DECISION, cost_shown=True)

    assert panel is not None
    assert sum(1 for action in panel.actions if action.primary) == 1
    assert len(panel.actions) <= 3


def test_chang_dang_cho_khach_chon_mau_thi_chua_co_buoc_tiep() -> None:
    """Chưa chốt xe nào thì "bước tiếp theo" của cái gì?"""

    assert build_next_step_panel(stage=PostPitchStage.AWAITING_CHOICE, cost_shown=False) is None


def test_chang_da_dong_thi_khong_moi_them() -> None:
    assert build_next_step_panel(stage=PostPitchStage.DONE, cost_shown=True) is None


def test_dang_cho_tu_van_vien_thi_khong_chen_ngang() -> None:
    """Khách đang chờ người thật — mời họ bấm nút lúc này là cắt ngang."""

    assert build_next_step_panel(stage=PostPitchStage.IN_HITL, cost_shown=True) is None


def test_dang_chon_khung_gio_thi_khong_moi_lai_thu_lan_nua() -> None:
    """Đã ở bước chọn giờ rồi mà vẫn mời lái thử là mời việc đang làm dở."""

    panel = build_next_step_panel(stage=PostPitchStage.AWAITING_SLOT, cost_shown=True)

    assert panel is None


def test_khong_co_chang_thi_khong_co_panel() -> None:
    assert build_next_step_panel(stage=None, cost_shown=True) is None


# ------------------------------------------------------------ đợt 9: MỘT hành động theo checklist


def test_chua_chot_co_de_xuat_thi_moi_chon_mau_dau() -> None:
    from src.agents.domain.next_step import build_single_action_panel

    panel = build_single_action_panel(chosen_name="", recommended_name="VF 5", has_booking=False)
    assert panel is not None
    assert panel.action is not None
    assert panel.action.label == "Chốt VF 5"
    assert panel.action.message == "Chọn VF 5"


def test_da_chot_chua_lich_thi_moi_dat_lai_thu() -> None:
    from src.agents.domain.next_step import build_single_action_panel

    panel = build_single_action_panel(chosen_name="VF 5", recommended_name="VF 5", has_booking=False)
    assert panel is not None and panel.action is not None
    assert panel.action.label == "Đặt lịch lái thử"
    assert panel.action.message == "Đặt lái thử VF 5"


def test_da_co_lich_thi_moi_xem_lich_message_rong() -> None:
    from src.agents.domain.next_step import build_single_action_panel

    panel = build_single_action_panel(chosen_name="VF 5", recommended_name="", has_booking=True)
    assert panel is not None and panel.action is not None
    assert panel.action.label == "Xem lịch của tôi"
    assert panel.action.message == ""


def test_dang_cho_tvv_hoac_chua_co_gi_thi_khong_co_panel() -> None:
    from src.agents.domain.next_step import build_single_action_panel

    assert (
        build_single_action_panel(chosen_name="VF 5", recommended_name="", has_booking=False, waiting_advisor=True)
        is None
    )
    assert build_single_action_panel(chosen_name="", recommended_name="", has_booking=False) is None
