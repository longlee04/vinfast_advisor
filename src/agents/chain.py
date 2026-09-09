"""Cửa công khai của một lượt hội thoại — nay chỉ còn lõi v2.

Trước 2026-08-31 file này là toàn bộ lõi v1 (~3.900 dòng) kèm chỗ rẽ nhánh
`use_core_v2`. Bước 5 lộ trình (spec 2026-08-29 mục 10) đã xoá lõi cũ theo
lệnh Sếp: prod chạy 100% v2, 24h cuối 906/906 lượt tier `core_v2`, lượt AUTO
cuối cùng 30/08. Giữ lại đúng hai thứ `api/` đang import:

- `run_turn`: wrapper mở ngân sách gọi provider (`TurnCallBudget` — các adapter
  judge/slot vẫn đọc ContextVar này) rồi gọi thẳng lõi v2, cuối cùng
  `project_public_result` làm mờ mã nội bộ ở biên công khai như cũ.
- `facts_as_dict`: phẳng hoá `VehicleFacts` cho response HTTP.

Muốn xem lõi cũ: `git log` trước commit xoá.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.agents.contracts import TurnResult, VehicleFacts
from src.agents.core.run_turn import run_turn as core_run_turn
from src.agents.services.call_budget import TurnCallBudget, use_call_budget
from src.agents.services.output_guard import project_public_result
from src.agents.services.registry import AgentServices


async def run_turn(
    graph: Any,
    services: AgentServices,
    *,
    session_id: str,
    customer_id: str,
    user_message: str,
    client_turn_id: UUID | None = None,
    lease: Any = None,
) -> TurnResult:
    """Chạy đúng một lượt hội thoại và trả DTO cho `api/`.

    `graph` giữ trong chữ ký vì ba route đang truyền vào, nhưng lõi v2 không đi
    qua LangGraph (`core/run_turn.py` cũng `del graph`) — bỏ tham số là đổi hợp
    đồng ba chỗ mà không được gì.

    `lease` (PR1): khi route đã gọi `begin_core_turn` và cấp lease, truyền xuống
    để lõi KHÔNG claim lại — tránh double-claim và để commit dùng token đúng.

    Ngân sách gọi provider mở ở ĐÂY và chỉ sống trong một lượt: `ContextVar` nên
    hai lượt song song có hai bộ đếm riêng, không cần khoá.
    """
    with use_call_budget(TurnCallBudget()):
        result = await core_run_turn(
            graph,
            services,
            session_id=session_id,
            customer_id=customer_id,
            user_message=user_message,
            client_turn_id=client_turn_id,
            lease=lease,
        )
        # Biên công khai: làm mờ `terminal_reason`. Đường persist bên trong lõi
        # vẫn giữ mã nội bộ trong outcome — thứ duy nhất nói vì sao lượt hỏng.
        return project_public_result(result)


def facts_as_dict(facts: VehicleFacts) -> dict:
    """Phẳng hoá `VehicleFacts` cho response HTTP — giá `None` giữ nguyên `None`.

    Không thay `None` bằng 0 hay chuỗi rỗng: "chưa có giá hiệu lực" khác "giá
    bằng 0", và mọi số rời hệ thống phải truy được về bản ghi nguồn.
    """
    return {
        "vehicle_id": str(facts.vehicle_id),
        "display_name": facts.display_name,
        "vehicle_type": facts.vehicle_type.value,
        "starting_price_vnd": (str(facts.starting_price_vnd) if facts.starting_price_vnd is not None else None),
        "specs": facts.specs,
    }
