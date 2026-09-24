"""Tên cờ Customer 360 trong `agent_feature_flags` (gieo TẮT ở agent_0037/0039).

Hai kiểu đọc:
- Cờ chạy nền theo KHÁCH (`attach`, `extractor`, `agent_ask_purchase_timeframe`): đi qua
  `agent_flag.is_enabled_for` — phần trăm + allowlist như `agent_fallback`.
- Cờ giao diện/ưu đãi TOÀN CỤC (`ui`, `offer_*`): chỉ nhìn `enabled`; không có "một nửa
  TVV thấy màn mới".
"""

from __future__ import annotations

from typing import Final

from src.agents.domain.agent_flag import AgentFlagState

FLAG_ATTACH: Final = "customer360_attach"
FLAG_EXTRACTOR: Final = "customer360_extractor"
FLAG_UI: Final = "customer360_ui"
FLAG_ASK_TIMEFRAME: Final = "agent_ask_purchase_timeframe"
FLAG_OFFER_RULES: Final = "offer_rules_engine"
FLAG_OFFER_LIFECYCLE: Final = "offer_lifecycle"


def is_globally_on(state: AgentFlagState | None) -> bool:
    return state is not None and state.enabled


__all__ = [
    "FLAG_ASK_TIMEFRAME",
    "FLAG_ATTACH",
    "FLAG_EXTRACTOR",
    "FLAG_OFFER_LIFECYCLE",
    "FLAG_OFFER_RULES",
    "FLAG_UI",
    "is_globally_on",
]
