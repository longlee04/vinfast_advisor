"""Xin lái thử sau bản đề xuất KHÔNG được kéo luồng tư vấn chạy lại.

BUG THẬT, bắt được bằng lưới E2E `test_post_pitch_test_drive_e2e` (2026-08-28):
lưới đỏ 1 trên 4 lần chạy, luôn ở cùng một câu — *"không được chấm điểm lại rồi
pitch đè"*. Khách gõ *"đăng ký lái thử"* ngay sau bản đề xuất và nhận lại đúng
bản đề xuất vừa đọc.

Gốc nằm ở `reconcile_task_action`. Cửa `CLARIFY_TASK` có sẵn một lối tránh cho
lời xin lái thử — đúng ý, vì hỏi lại ngân sách người ta vừa nói là vô duyên.
Nhưng tránh xong thì lượt rơi thẳng xuống `CONTINUE_TASK` ngay bên dưới, và
`CONTINUE_TASK` nghĩa là *chạy lại bảng điểm cũ*. Lối thoát dẫn vào một cái hố
sâu hơn.

Chập chờn vì `Intent.ADVISORY` có nằm trong `intent_set` hay không là do LLU
quyết. Có thì pitch đè, không thì yên. Bản đọc tất định phải thắng: câu xin lái
thử là bước SAU bản đề xuất, không phải một lượt tư vấn mới.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.domain.intent_reconciliation import reconcile_intents
from src.agents.domain.turn_understanding import reconcile_task_action
from src.agents.domain.values import Intent, SlotName, TaskAction

_COMPLETED_ADVISORY = {
    "task_type": "ADVISORY",
    "status": "COMPLETED",
    "form": {},
    "revision": 1,
    "updated_at": datetime(2026, 8, 28, tzinfo=UTC).isoformat(),
}


@pytest.mark.parametrize(
    "message",
    [
        "đăng ký lái thử",
        "cho anh đặt lịch lái thử",
        "dang ky lai thu",
    ],
)
def test_xin_lai_thu_sau_ban_de_xuat_khong_chay_lai_bang_diem(message: str) -> None:
    action, excluded = reconcile_task_action(
        user_message=message,
        intents=(Intent.ADVISORY,),
        raw_action=TaskAction.NONE,
        active_task_payload=_COMPLETED_ADVISORY,
        current_slots={},
        known_slots={},
    )

    assert action is not TaskAction.CONTINUE_TASK, "chạy lại bảng điểm là pitch đè lên bản khách vừa đọc"
    assert action is not TaskAction.CLARIFY_TASK, "hỏi lại ngân sách người ta vừa nói là vô duyên"
    assert action is TaskAction.NONE
    assert excluded == ()


def test_luot_tu_van_that_van_duoc_chay_tiep() -> None:
    """Cửa mới chỉ đóng đúng lời xin lái thử, không đóng luồng tư vấn."""

    action, _ = reconcile_task_action(
        user_message="cho em xem thêm xe nào rộng hơn",
        intents=(Intent.ADVISORY,),
        raw_action=TaskAction.NONE,
        active_task_payload=_COMPLETED_ADVISORY,
        current_slots={},
        known_slots={},
    )

    assert action is not TaskAction.NONE


def test_xin_lai_thu_khi_chua_co_ban_de_xuat_thi_khong_bi_chan() -> None:
    """Chưa có việc tư vấn nào hoàn tất thì lượt vẫn phải mở được việc mới.

    Cửa này chỉ nói *"đừng chấm lại bảng điểm đã xong"*. Khách mở lời bằng câu
    xin lái thử ngay từ đầu phiên vẫn phải đi tiếp được, nếu không thì một lối
    vào hợp lệ bị bịt.
    """

    action, _ = reconcile_task_action(
        user_message="đăng ký lái thử",
        intents=(Intent.ADVISORY,),
        raw_action=TaskAction.NONE,
        active_task_payload=None,
        current_slots={},
        known_slots={},
    )

    assert action is TaskAction.START_NEW_TASK


def test_luot_vua_xin_lai_thu_vua_them_tieu_chi_thi_van_uu_tien_lai_thu() -> None:
    """Đánh đổi đã cân nhắc, ghi ra để không ai đổi ngầm.

    Bản vá đầu còn kèm `not _has_new_task_information(...)`. Hàm đó so hai bản
    đồ slot mà `current_slots` là thứ LLM trích — trên chính câu "đăng ký lái
    thử" nó trích khác nhau giữa các lần chạy, nên lưới E2E vẫn đỏ 1/4 lần.

    Bỏ điều kiện đó nghĩa là lượt vừa xin lái thử vừa mang tiêu chí mới sẽ không
    chấm lại điểm NGAY. Chấp nhận: thứ khách nói to nhất là muốn lái thử, và
    tiêu chí vừa nói vẫn nằm trong slot cho lượt tư vấn kế tiếp.
    """

    action, _ = reconcile_task_action(
        user_message="cho anh xe 7 chỗ rồi đăng ký lái thử",
        intents=(Intent.ADVISORY,),
        raw_action=TaskAction.NONE,
        active_task_payload=_COMPLETED_ADVISORY,
        current_slots={"seat_count": 7},
        known_slots={},
    )

    assert action is TaskAction.NONE


def test_xin_lai_thu_khong_bi_doc_thanh_luot_tu_van_chi_vi_da_biet_loai_xe() -> None:
    """`vehicle_type` khoá sẵn KHÔNG biến câu xin lái thử thành lượt tư vấn.

    Đây là gốc thật của chỗ chập chờn, đo bằng bản in tại chỗ:

        XANH:  RAW=[]  SLOTS={}                      -> intents []
        ĐỎ:    RAW=[]  SLOTS={vehicle_type: CAR}     -> intents [ADVISORY]

    LLM không gắn intent nào ở CẢ HAI lần. Khác nhau ở chỗ lần đỏ, `vehicle_type`
    — thứ đã khoá từ đầu phiên, không phải tiêu chí khách vừa nói — làm bật
    `continues_active_vehicle_branch`, và `ADVISORY` được thêm vào. Từ đó luồng
    chấm điểm lại chạy và khách nhận đè lên bản đề xuất vừa đọc.

    Theo đúng định nghĩa của chính enum: `ADVISORY` là khách đưa TIÊU CHÍ CÁ
    NHÂN (ngân sách, số người, quãng đường). Loại xe đã biết từ trước không phải
    tiêu chí mới, và "đăng ký lái thử" không mang tiêu chí nào.
    """

    intents = reconcile_intents(
        user_message="đăng ký lái thử",
        raw_intents=(),
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR"},
        vehicle_mentions=(),
        known_slots={SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 800_000_000},
    )

    assert Intent.ADVISORY not in intents


def test_luot_that_su_khai_nhu_cau_van_giu_advisory() -> None:
    """Cửa mới hẹp: chỉ đóng câu xin lái thử, không đóng lượt khai nhu cầu."""

    intents = reconcile_intents(
        user_message="nhà 5 người, ngân sách 800 triệu",
        raw_intents=(),
        normalized_slots={SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 800_000_000},
        vehicle_mentions=(),
        known_slots={SlotName.VEHICLE_TYPE: "CAR"},
    )

    assert Intent.ADVISORY in intents
