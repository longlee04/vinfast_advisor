"""Panel "Bước tiếp theo" — DỮ LIỆU TRÌNH BÀY, không phải một chặng.

Sếp 2026-08-28: `VEHICLE_DETAILS_SHOWN` và `TEST_DRIVE_CTA` là **màn hình**,
không phải trạng thái. Nguyên tắc chốt cùng lúc:

    State chỉ tồn tại khi lượt SAU cần hiểu khác đi vì nó.

Panel này không đổi cách đọc lượt sau — nó chỉ nói cho khách biết họ làm được gì.
Nên nó KHÔNG có TTL, không revision, không compare-before-write, và
`PostPitchStage` giữ nguyên **năm** chặng.

Lý do rất cụ thể: phiên 2026-08-28 vá **năm** lỗi quanh máy trạng thái đó, mỗi
lỗi cùng một hình dạng — *chặng tiến lên nhưng bước sau không có gì để làm việc*.
Thêm chặng mới vào đó là viết lại thứ vừa mới ổn định.

Luật mở thẻ đặt lịch
--------------------
    KHÔNG mở thẻ trước khi khách nhận lời.
    Khách ĐÃ xin hoặc ĐÃ nhận lời  →  mở luồng ngay.

Panel chỉ **mời**; thẻ chọn giờ do chặng sau đề xuất dựng khi khách đồng ý. Tương
thích với quyết định 2026-08-26 (*"nối luôn đăng ký lái thử"*).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.post_pitch import PostPitchStage


class NextStepAction(StrEnum):
    """Việc khách làm được ngay sau khi đã chốt một mẫu."""

    ON_ROAD_PRICE = "ON_ROAD_PRICE"
    COMPARE = "COMPARE"
    COLORS = "COLORS"
    TEST_DRIVE = "TEST_DRIVE"
    ASK_MORE = "ASK_MORE"


@dataclass(frozen=True, slots=True)
class NextStepOption:
    """Một lựa chọn. `primary` là thứ bậc THỊ GIÁC, không phải quyền chọn.

    "Tôi muốn hỏi thêm" luôn là một lựa chọn RÕ — không làm mờ, không đặt xa,
    không biến thành link xám nhạt. Ngang hàng về quyền chọn, khác nhau về nhấn
    mạnh.
    """

    action: NextStepAction
    label: str
    primary: bool = False


@dataclass(frozen=True, slots=True)
class NextStepCta:
    """MỘT hành động đi tiếp (đợt 9 "tour guide").

    `message` là câu client gửi lại vào `/agent/turn` khi bấm — viết đúng như
    khách sẽ gõ (cùng luật với `core/suggest.py`), nên cửa hiểu ý đọc được mà
    không cần mã riêng. Rỗng = client tự xử lý (mở trang tài khoản để xem lịch).
    """

    label: str
    message: str


@dataclass(frozen=True, slots=True)
class NextStepPanel:
    """Lời mời đi tiếp. `None` ở mọi chặng không phải chỗ để mời.

    `actions` là bộ nút NHIỀU lựa chọn của lõi cũ (`chain.py`); `action` là MỘT
    hành động theo checklist của lõi v2 (đợt 9). Client mới đọc `action`, client
    cũ vẫn đọc `actions` — hai trường cùng tồn tại để không client nào vỡ.
    """

    title: str
    actions: tuple[NextStepOption, ...] = ()
    action: NextStepCta | None = None


_AFTER_OVERVIEW: Final[tuple[NextStepOption, ...]] = (
    NextStepOption(NextStepAction.ON_ROAD_PRICE, "Ước tính giá lăn bánh", primary=True),
    NextStepOption(NextStepAction.COMPARE, "So sánh với mẫu khác"),
    NextStepOption(NextStepAction.COLORS, "Xem màu sắc & phiên bản"),
)

_AFTER_COST: Final[tuple[NextStepOption, ...]] = (
    NextStepOption(NextStepAction.TEST_DRIVE, "Chọn lịch lái thử", primary=True),
    NextStepOption(NextStepAction.ASK_MORE, "Tôi muốn hỏi thêm"),
)


def build_next_step_panel(*, stage: PostPitchStage | None, cost_shown: bool) -> NextStepPanel | None:
    """Panel cho chặng hiện tại, hoặc `None` khi đây không phải chỗ để mời.

    Bốn chặng trả `None`, mỗi chặng một lý do riêng:

    - `AWAITING_CHOICE` — chưa chốt xe nào thì "bước tiếp theo" của cái gì.
    - `IN_HITL` — khách đang chờ người thật; mời họ bấm nút lúc này là cắt ngang.
    - `AWAITING_SLOT` — đang chọn giờ rồi; mời lái thử nữa là mời việc đang làm dở.
    - `DONE` — chặng đã đóng.
    """

    if stage in (None, PostPitchStage.AWAITING_CHOICE, PostPitchStage.IN_HITL, PostPitchStage.DONE):
        return None
    if stage is PostPitchStage.AWAITING_SLOT:
        return None
    if cost_shown:
        return NextStepPanel(
            title="Anh/chị đã có mức chi phí dự kiến. Muốn trải nghiệm xe thực tế trước khi quyết định?",
            actions=_AFTER_COST,
        )
    return NextStepPanel(title="Anh/chị muốn xem tiếp phần nào?", actions=_AFTER_OVERVIEW)


def build_single_action_panel(
    *,
    chosen_name: str,
    recommended_name: str,
    has_booking: bool,
    waiting_advisor: bool = False,
    picking_slot: bool = False,
) -> NextStepPanel | None:
    """MỘT hành động theo checklist chọn xe → lái thử → xem lịch (đợt 9, contract mục 2).

    Thứ tự kiểm tra là thứ tự của checklist, từ bước XA nhất đã đạt:
    - đang chờ TVV → `None` (mời bấm nút lúc này là cắt ngang người thật);
    - đang chọn giờ trên thẻ → `None` (mời lái thử là mời việc đang làm dở);
    - đã có lịch → "Xem lịch của tôi", `message` rỗng để client mở trang tài khoản;
    - đã chốt xe → "Đặt lịch lái thử";
    - chưa chốt nhưng có đề xuất → "Chốt <mẫu đầu>";
    - chưa có gì → `None`.
    Tên xe đã bỏ tiền tố hãng ("VF 5") vì đây là chữ trên nút.
    """

    if waiting_advisor or picking_slot:
        return None
    if has_booking:
        return NextStepPanel(
            title="Lịch lái thử của anh/chị đã được đặt.",
            action=NextStepCta(label="Xem lịch của tôi", message=""),
        )
    if chosen_name:
        return NextStepPanel(
            title=f"Anh/chị đã chọn {chosen_name}. Trải nghiệm xe thực tế trước khi quyết định?",
            action=NextStepCta(label="Đặt lịch lái thử", message=f"Đặt lái thử {chosen_name}"),
        )
    if recommended_name:
        return NextStepPanel(
            title=f"Anh/chị ưng {recommended_name} chứ?",
            action=NextStepCta(label=f"Chốt {recommended_name}", message=f"Chọn {recommended_name}"),
        )
    return None
