"""Sau bản đề xuất, khách xin lái thử — chạy qua ĐÚNG graph và chain thật.

BUG THẬT trên prod 2026-08-28, chạy thật:

    USER: đăng ký lái thử        (ngay sau khi nhận bản đề xuất)
    BOT:  Em có thể đặt lịch lái thử để anh/chị trải nghiệm trực tiếp, hoặc gửi
          thêm thông tin về màu sắc, phiên bản và chính sách bàn giao.
          Anh/chị muốn xem phần nào trước ạ?

Không có thẻ chọn khung giờ, không sang `AWAITING_SLOT`.

Bộ này KHÔNG gọi `_advance_post_pitch` rời — nó phải đi trọn `run_turn` để nói ra
lượt chết ở SEAM nào. Suy đoán ban đầu ("quote_gate chặn trước routing") đã sai:
`graph.py:133` cho thấy `route_intent -> quote_gate`, tức cổng đứng SAU. Nên bước
đầu tiên là CHỤP trạng thái, chưa sửa gì.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.chain import run_turn

# Dùng lại danh mục seed của bộ acceptance: không có nó thì Lớp 1 không có ứng
# viên nào và lượt 3 không bao giờ ra bản đề xuất — test đỏ vì THIẾU DỮ LIỆU,
# không phải vì lỗi đang truy.
from tests.agents.integration.test_prd_acceptance_e2e import acceptance_catalog  # noqa: F401


async def _create_session(engine: AsyncEngine, session_id: str, customer_id: str) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as setup, setup.begin():
        await SqlAlchemySessionRepository(setup, SystemClock()).ensure_session(session_id, customer_id, None)


#: Kịch bản đưa một phiên mới tới bản đề xuất. Cùng bộ câu với
#: `test_prd_acceptance_e2e`.
_SCRIPT = (
    "toi muon mua o to",
    "nha 5 nguoi, ngan sach 800 trieu, co sac tai nha, di lam moi ngay 30km, uu tien gia dinh",
    "khong can tinh nang gi dac biet",
)


async def _pitch_xong(turn):
    """Chạy kịch bản tới LÚC có bản đề xuất, rồi dừng ngay tại đó.

    Bản trước gọi cứng ba lượt rồi đọc bản đề xuất ở lượt thứ ba — và ba test
    này đỏ khi chạy riêng, xanh khi chạy cùng cả bộ. Nguyên nhân KHÔNG phải
    hành vi sản phẩm: số câu hỏi trước khi chốt phụ thuộc danh mục có bao nhiêu
    ứng viên, mà danh mục lại tuỳ những gì bộ test khác đã ghi vào cùng CSDL.

    Danh mục nhỏ thì lượt HAI đã đủ tiêu chí để pitch. Lượt ba
    ("không cần tính năng gì đặc biệt") khi đó rơi vào
    `turn_understanding` với `task.status = COMPLETED` và không tiêu chí mới —
    tức `CLARIFY_TASK` — nên nó trả câu hỏi lại, `recommendations` rỗng, và
    `assert pitched.recommendations` gãy.

    Dừng NGAY khi có bản đề xuất cũng đúng hơn về ý: mọi test dưới đây kiểm
    hành vi *ngay sau bản đề xuất*, nên gửi thêm một lượt lạc đề vào giữa là
    tự làm bẩn tiền đề.
    """

    for message in _SCRIPT:
        result = await turn(message)
        if result.recommendations:
            return result
    raise AssertionError("kịch bản không ra được bản đề xuất nào — kiểm tra seed danh mục")


@pytest.mark.asyncio
async def test_xin_lai_thu_ngay_sau_ban_de_xuat_mo_duoc_buoc_chon_khung_gio(
    agent_composition, agent_session, migrated_engine: AsyncEngine
) -> None:
    """Lượt 2 phải MỞ bước chọn lịch, không trả một câu hỏi hai lối."""

    from src.agents.domain.post_pitch import PostPitchStage, stage_of
    from src.agents.domain.task_state import ActiveTask

    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)

    async def turn(message: str):
        return await run_turn(
            agent_composition.graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message=message,
        )

    await _pitch_xong(turn)

    second = await turn("đăng ký lái thử")

    # CHỤP trạng thái trước khi phán xét — đây là thứ nói ra seam nào nuốt lượt.
    conversation = agent_composition.services.conversation
    task = ActiveTask.from_payload(await conversation.load_active_task(session_id))
    print(
        "\n>>> luot 2:",
        {
            "answer": (second.answer or "")[:120],
            "pending_question": (second.pending_question or "")[:120],
            "terminal_reason": second.terminal_reason,
            "awaiting_review": second.awaiting_review,
            "recommendations": len(second.recommendations),
            "test_drive_card": second.test_drive_card is not None,
            "quick_replies": len(second.quick_replies or []),
            "stage": None if task is None else stage_of(task.form),
        },
    )

    assert not second.recommendations, "không được chấm điểm lại rồi pitch đè"
    assert second.awaiting_review is False, "câu xin lái thử thuần không phải việc cần người duyệt"
    assert task is not None

    # Khách xin lái thử NGAY sau bản đề xuất, chưa chốt mẫu nào.
    #
    # Trạng thái chụp được ở lần chạy đầu nói ra đúng chỗ hỏng, và nó KHÔNG phải
    # `quote_gate`: chặng đã sang `AWAITING_SLOT`, `terminal_reason` rỗng, không
    # cổng nào đóng lượt — nhưng `test_drive_card` và `quick_replies` đều rỗng.
    # `_test_drive_options` thoát ngay ở `not vehicle_name`, vì chặng tiến lên mà
    # KHÔNG mang theo xe nào.
    #
    # Cùng họ với bug `vehicle_name=''` đã chặn đứng việc đặt lịch: chặng tiến
    # lên trong khi bước sau không có gì để làm việc. Kết cục đúng là HỎI mẫu,
    # không phải lặng lẽ sang một chặng rỗng — và tuyệt đối không lấy chiếc đề
    # xuất đầu tiên làm mặc định.
    assert stage_of(task.form) is not PostPitchStage.AWAITING_SLOT, (
        "không được sang bước chọn giờ khi chưa biết lái thử xe nào"
    )
    assert "mẫu nào" in (second.answer or "")


@pytest.mark.asyncio
async def test_chot_mau_xong_thi_buoc_chon_khung_gio_moi_mo(
    agent_composition, agent_session, migrated_engine: AsyncEngine
) -> None:
    """Có tên xe rồi thì chặng mới được tiến, và bước sau phải có thứ để bấm."""

    from src.agents.domain.post_pitch import PostPitchStage, chosen_vehicle, stage_of
    from src.agents.domain.task_state import ActiveTask

    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)

    async def turn(message: str):
        return await run_turn(
            agent_composition.graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message=message,
        )

    pitched = await _pitch_xong(turn)
    picked = pitched.recommendations[0].display_name

    result = await turn(f"đăng ký lái thử {picked}")

    conversation = agent_composition.services.conversation
    task = ActiveTask.from_payload(await conversation.load_active_task(session_id))
    assert task is not None
    assert chosen_vehicle(task.form) == picked
    assert stage_of(task.form) is PostPitchStage.AWAITING_SLOT
    # Có xe rồi thì bước sau phải đưa được MỘT thứ để khách đi tiếp: thẻ chọn
    # giờ, nút khung giờ, hoặc lời hỏi vị trí. Rỗng cả ba là khách đứng lại.
    assert result.test_drive_card is not None or result.quick_replies or result.nearby_locations


@pytest.mark.asyncio
async def test_hoi_mau_xong_thi_luot_sau_go_ten_xe_di_tiep_duoc(
    agent_composition, agent_session, migrated_engine: AsyncEngine
) -> None:
    """Hỏi "mẫu nào" mà không mở bản ghi chờ là hỏi xong quên ngay.

    Đo trên prod 2026-08-28, ngay sau bản vá "không tiến chặng rỗng":

        USER: đăng ký lái thử
        BOT:  Anh/chị muốn lái thử mẫu nào ạ?
        USER: VF 5
        BOT:  (bảng thông số kỹ thuật)          ← rơi vào nhánh tra cứu

    Đây là lần THỨ BA cùng một cái bẫy trong phiên: `purpose`, rồi lái thử ở
    node, giờ tới chặng sau đề xuất. Câu hỏi nào cũng phải kèm một bản ghi chờ,
    nếu không lượt sau không còn dấu vết nào cho biết khách đang trả lời cái gì.
    """

    from src.agents.domain.on_road_pending import ON_ROAD_VEHICLE_SLOT  # noqa: F401
    from src.agents.domain.test_drive import TEST_DRIVE_VEHICLE_SLOT

    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)

    async def turn(message: str):
        return await run_turn(
            agent_composition.graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message=message,
        )

    pitched = await _pitch_xong(turn)

    asked = await turn("đăng ký lái thử")
    assert "mẫu nào" in (asked.answer or "")

    conversation = agent_composition.services.conversation
    pending = await conversation.load_pending_slot(session_id)
    assert pending is not None, "hỏi mẫu thì phải mở bản ghi chờ"
    assert pending["missing_slot"] == TEST_DRIVE_VEHICLE_SLOT

    # Lượt TIẾP: khách gõ tên xe. Đây là caller thật của `_resume_test_drive_vehicle`,
    # và nó từng nổ `TypeError` (HTTP 500) vì thiếu `session_id`/`customer_id` khi
    # `answer()` thêm tham số — bộ test đơn vị không bắt được vì service giả nhận
    # `**kwargs`. Chỉ đường chạy thật mới nói ra.
    tiep = await turn(pitched.recommendations[0].display_name)

    assert tiep.terminal_reason is None, f"lượt gõ tên xe chết: {tiep.terminal_reason}"
    # Phiên này chưa chia sẻ vị trí, nên câu trả lời ĐÚNG là hỏi vị trí — không
    # phải thẻ chọn giờ. Cái test canh ở đây là lượt CHẠY ĐƯỢC: bản trước nổ
    # `TypeError` (HTTP 500) ngay tại `service.answer()`.
    di_tiep_duoc = (
        tiep.test_drive_card is not None
        or tiep.quick_replies
        or tiep.nearby_locations is not None
        or "vị trí" in (tiep.answer or tiep.pending_question or "")
    )
    assert di_tiep_duoc, f"lượt gõ tên xe không đưa được gì để đi tiếp: {tiep.answer!r}"
