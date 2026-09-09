"""Gợi ý câu hỏi tiếp theo cho mỗi lượt — thuần, tất định (Sếp chốt 2026-08-29).

Vì sao có file này: một lời đáp không kèm lối đi tiếp bắt khách tự nghĩ ra câu
hỏi, và đó là lúc hội thoại chết — đúng lý do `prompts/reply_variants` bắt mọi
lời chào phải kết bằng một câu mời. Lõi v2 trả `quick_replies` rỗng ở mọi lượt
trừ lượt lái thử, nên toàn bộ phần còn lại của hội thoại không có nút nào.

Hai luật của chữ ở đây:

1. **Viết đúng như KHÁCH sẽ gõ.** Nút gửi lại nguyên văn vào cùng một cửa hiểu
   ý, nên "Tính chi phí sử dụng" phải là một câu bộ hiểu ý đọc ra `COST`. Một
   nhãn kiểu "Xem TCO" là mời khách gửi một chuỗi lõi không đọc được.
2. **Không bao giờ có mã máy hay id thô.** Tên xe lấy từ danh bạ catalog
   (`vehicle_names`); tra không ra thì BỎ gợi ý đó, không đọc id cho khách.

Không I/O, không import `chain`/`nodes`, mọi chuỗi qua `render.assert_clean`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.agents.core.actions import (
    PENDING_PROFILE,
    PENDING_SHOWROOM_SLOT,
    REASON_REVISED,
    Action,
    Compare,
    OnRoadPrice,
    Recommend,
    ShowroomOptions,
    Tco,
)
from src.agents.core.render import assert_clean
from src.agents.core.state import CoreState, Stage

#: Trần số gợi ý một lượt. Nhiều hơn bốn thì khách đọc nút thay vì đọc câu trả lời.
MAX_SUGGESTIONS = 4

#: Lượt mở đầu / đang hỏi hồ sơ: hai ví dụ TRẢ LỜI mẫu (cho khách thấy cần nói
#: gì) và một lối đi ngang cho người chưa muốn kể nhu cầu.
OPENING: tuple[str, ...] = (
    "Ô tô khoảng 800 triệu, gia đình 5 người",
    "Xe máy khoảng 30 triệu, chạy giao hàng",
    "Xem tất cả mẫu xe",
)

#: Ví dụ TRẢ LỜI cho câu hồ sơ khi ĐÃ biết loại xe. Khác `OPENING` ở chỗ không
#: còn phải mời khách chọn loại: lượt đó lõi bày thẳng danh sách của loại họ nêu,
#: nên gợi ý chỉ còn việc cho thấy một câu trả lời đầy đủ trông ra sao.
PROFILE_EXAMPLES: Mapping[str, tuple[str, ...]] = {
    "CAR": ("Ô tô khoảng 800 triệu, gia đình 5 người", "Xe khoảng 500 triệu, đi làm nội thành"),
    "ELECTRIC_MOTORBIKE": ("Xe máy khoảng 30 triệu, chạy giao hàng", "Xe máy khoảng 20 triệu, đi học"),
}


def profile_examples(vehicle_type: str | None, *, vehicle_names: Sequence[str] = ()) -> tuple[str, ...]:
    """Gợi ý cho lượt "đã biết loại xe": hai ví dụ trả lời + một lối so sánh.

    Tên xe phải là tên THẬT của đúng loại đó — `act` lấy từ chính danh sách vừa
    bày cho khách, không lấy từ danh bạ chung (danh bạ trộn cả ô tô lẫn xe máy,
    mời "So sánh VF 8 và Klara" là mời một phép so vô nghĩa).
    """

    items = list(PROFILE_EXAMPLES.get((vehicle_type or "").upper(), ()))
    if not items:
        return ()
    names = [name for name in vehicle_names if name]
    if len(names) >= 2:
        items.append(f"So sánh {names[0]} và {names[1]}")
    return _clean(items)


#: Đã chốt một mẫu: bốn việc làm được ngay với chiếc xe đó.
AFTER_CHOSEN: tuple[str, ...] = (
    "Tính chi phí sử dụng",
    "Giá lăn bánh",
    "Đặt lịch lái thử",
    "Có ưu đãi gì không?",
)

#: Đang chờ người thật (ưu đãi / handoff): chỉ còn một lối, và nó phải là lối
#: KHÔNG giục tư vấn viên.
AFTER_HANDOFF: tuple[str, ...] = ("Hỏi thêm về xe",)


def _clean(items: list[str]) -> tuple[str, ...]:
    return tuple(assert_clean(item) for item in dict.fromkeys(items) if item)[:MAX_SUGGESTIONS]


def _named(vehicle_names: Mapping[str, str], vehicle_id: str | None) -> str:
    """Tên hiển thị của một xe, hoặc chuỗi rỗng.

    Rỗng chứ không phải id: mọi chỗ gọi đều bỏ gợi ý khi không có tên, vì đọc
    "Chọn 3f2504e0-…" cho khách là đúng lỗi `render.assert_clean` sinh ra để chặn.
    """

    return vehicle_names.get(vehicle_id or "", "") or ""


def _after_recommend(state: CoreState, action: Action, vehicle_names: Mapping[str, str]) -> tuple[str, ...]:
    names = [name for vehicle_id in state.recommended_ids if (name := _named(vehicle_names, vehicle_id))]
    if isinstance(action, Recommend) and action.reason == REASON_REVISED:
        # Đang trong vòng chỉnh: giữ vòng mở (xin chỉnh tiếp) và giữ đường lui
        # (quay lại bản vừa xem), chứ không mời so sánh như lượt đề xuất đầu.
        items = [f"Chọn {names[0]}"] if names else []
        return _clean([*items, "Rẻ hơn nữa", "Xem lại mẫu trước"])
    items = []
    if names:
        items.append(f"Chọn {names[0]}")
    if len(names) >= 2:
        items.append(f"So sánh {names[0]} và {names[1]}")
    if names:
        items.append(f"Tính chi phí {names[0]}")
    items.append("Xem mẫu khác")
    return _clean(items)


def _after_compare(state: CoreState, vehicle_names: Mapping[str, str]) -> tuple[str, ...]:
    """Sau một bảng so sánh, việc duy nhất còn lại là CHỐT một trong hai mẫu.

    Prod: bảng so sánh xong, khách nhận lại `OPENING` ("Ô tô khoảng 800 triệu,
    gia đình 5 người") — bộ gợi ý của lượt CHÀO, vì `_lookup_decision` không đổi
    `stage` nên `quick_replies` rơi xuống nhánh cuối. Ở đây phải gọi TÊN hai mẫu
    vừa so: khách đang cân giữa đúng hai cái tên đó.
    """

    names = [name for vehicle_id in state.recommended_ids if (name := _named(vehicle_names, vehicle_id))]
    if not names:
        return ()
    items = [f"Chọn {name}" for name in names[:2]]
    items.append(f"Tính chi phí {names[0]}")
    items.append(f"Đặt lái thử {names[0]}")
    return _clean(items)


def _after_cost(action: Action) -> tuple[str, ...]:
    # Lượt vừa báo chi phí: gợi ý CON SỐ CÒN LẠI (giá lăn bánh sau khi tính chi
    # phí sử dụng, và ngược lại) rồi mới tới việc đi tiếp.
    other = "Giá lăn bánh" if isinstance(action, Tco) else "Tính chi phí sử dụng"
    return _clean(["Đặt lịch lái thử", other, "Xem mẫu khác", "Có ưu đãi gì không?"])


def quick_replies(state: CoreState, action: Action, *, vehicle_names: Mapping[str, str]) -> tuple[str, ...]:
    """Gợi ý cho lượt vừa xong, đọc từ `state` SAU lượt và Action đã chạy.

    `state` là trạng thái đã áp `state_patch`: gợi ý phải khớp với chỗ khách
    đang đứng lúc đọc câu trả lời, không phải chỗ họ đứng lúc gõ câu hỏi.
    """

    if getattr(action, "resume_pending", False) and state.pending is not None:
        # Lượt chen ngang: câu treo vừa được nối lại ở cuối câu trả lời, nên gợi
        # ý phải giúp trả lời CÂU ĐÓ, không phải mở thêm một việc thứ ba.
        return OPENING if state.pending.key == PENDING_PROFILE else ()
    if isinstance(action, ShowroomOptions):
        # Nút khung giờ (`__lichlaithu__`) chính là gợi ý của lượt này — thêm
        # gợi ý chữ vào đây là mời khách bỏ dở đúng việc họ vừa xin.
        return ()
    if state.pending is not None and state.pending.key == PENDING_SHOWROOM_SLOT:
        return ()
    if isinstance(action, Compare):
        return _after_compare(state, vehicle_names)
    if isinstance(action, Tco | OnRoadPrice):
        return _after_cost(action)
    if state.stage in {Stage.OFFER_REVIEW, Stage.HANDED_OFF}:
        return AFTER_HANDOFF
    if state.stage is Stage.CHOSEN or state.chosen_vehicle_id is not None:
        return AFTER_CHOSEN
    if state.stage is Stage.RECOMMENDED:
        return _after_recommend(state, action, vehicle_names)
    if state.pending is not None and state.pending.key != PENDING_PROFILE:
        # Đang chờ một câu trả lời cụ thể khác (chọn mẫu nào, tỉnh nào): gợi ý
        # chung chỉ kéo khách ra khỏi câu đang hỏi.
        return ()
    return OPENING
