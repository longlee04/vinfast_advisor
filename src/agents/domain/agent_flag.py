"""Cờ động của đường agent — luật thuần, không I/O (plan agent-migration Bước 3).

Một cờ có ba nấc, tầng ngoài thắng tầng trong:

1. **Kill-switch env** (`Settings.agent_fallback_kill_switch`) — `True` là TẮT
   tuyệt đối, bỏ qua DB. Cần restart; dành cho sự cố.
2. **`enabled`** trong bảng `agent_feature_flags` — `False` là TẮT dù allowlist
   có tên. Bật/tắt không cần restart (adapter cache TTL 60s).
3. **Ai được bật**: `customer_allowlist` thắng phần trăm; ngoài allowlist thì
   chia phần trăm TẤT ĐỊNH bằng băm `customer_id` — cùng khách luôn cùng nhánh,
   không nhảy giữa các lượt.

Không có hàng (DB chưa gieo, adapter lỗi) → `None` → TẮT. Đây là chiều an
toàn duy nhất được phép (R10).

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

#: Tên cờ của hai móc agent (móc 1 `policy._unclear`, móc 2 ngõ cụt `_recommend`).
FLAG_AGENT_FALLBACK: Final = "agent_fallback"
#: Cache đọc cờ — bật/tắt có hiệu lực trong vòng này, không cần restart.
FLAG_TTL_SECONDS: Final[float] = 60.0


@dataclass(frozen=True, slots=True)
class AgentFlagState:
    """Một hàng `agent_feature_flags` đã đọc lên, bất biến."""

    name: str
    enabled: bool = False
    rollout_percent: int = 0
    customer_allowlist: frozenset[str] = frozenset()


def parse_allowlist(raw: str | None) -> frozenset[str]:
    """`"a, b,,c "` → `{"a","b","c"}`. Chỗ DUY NHẤT tách chuỗi allowlist."""

    return frozenset(item.strip() for item in (raw or "").split(",") if item.strip())


def rollout_bucket(name: str, customer_id: str) -> int:
    """Nấc 0..99 của một khách cho một cờ — tất định, không phụ thuộc tiến trình.

    `sha256` chứ không `hash()`: `hash()` của chuỗi đổi theo mỗi lần khởi động
    (PYTHONHASHSEED), khách sẽ nhảy nhánh sau mỗi lần deploy.
    """

    digest = hashlib.sha256(f"{name}:{customer_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def is_enabled_for(state: AgentFlagState | None, customer_id: str, *, kill_switch: bool = False) -> bool:
    """Khách này có đi đường agent không. Mọi nhánh thiếu dữ liệu đều là `False`."""

    if kill_switch or state is None or not state.enabled:
        return False
    customer = (customer_id or "").strip()
    if not customer:
        return False
    if customer in state.customer_allowlist:
        return True
    percent = max(0, min(100, int(state.rollout_percent)))
    return rollout_bucket(state.name, customer) < percent


__all__ = [
    "FLAG_AGENT_FALLBACK",
    "FLAG_TTL_SECONDS",
    "AgentFlagState",
    "is_enabled_for",
    "parse_allowlist",
    "rollout_bucket",
]
