"""[A4-4] Seam lấy `AgentComposition` và định danh khách cho route agent.

Route KHÔNG tự dựng engine/pool: composition root là `composition.py`, khởi tạo
một lần trong `lifespan` của `src/main.py` (cùng mẫu `auth`/`document`).

Hai dependency dưới đây **không raise**: chúng trả `None` và để route quyết định.
Nếu raise ngay khi giải dependency, FastAPI ngắt trước cả bước validate body và
trả 401/503 cho request có body sai — che mất 422, tức phá hợp đồng validation
đã đóng băng ở A0-4.
"""

from __future__ import annotations

from fastapi import Depends, Request


def get_agent(request: Request):
    """Trả composition đang sống, hoặc `None` khi app chưa khởi tạo agent."""

    return getattr(request.app.state, "agent", None)


async def get_current_customer_id() -> str | None:
    """Định danh khách do tầng Auth cấp; ứng dụng override seam hẹp này.

    Mặc định `None` = chưa xác thực. KHÔNG lấy định danh từ body request: hồ sơ
    nhu cầu và lịch sử tư vấn gắn với `customer_id`, để client tự khai là mở
    đường đọc hồ sơ người khác (cùng ranh giới A8-3 đang cưỡng chế bằng 403).
    """

    return None


AgentDependency = Depends(get_agent)
CustomerDependency = Depends(get_current_customer_id)
