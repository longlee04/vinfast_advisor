"""Hợp đồng tool `tinh_chi_phi` — mảnh tool-calling đầu tiên của lõi v2.

Khác mọi đường LLM trước đây (extractor bị ÉP trả đúng một hình), ở đây LLM
được cầm một tool thật và tự chọn THAM SỐ từ câu khách. Kết quả chỉ để LẤP
CHỖ TRỐNG cho `core/act._tco`: slot khách đã nói luôn thắng, resolver hỏng
thì trả `None` và lượt đi tiếp đường tất định — tool-calling là đường phụ,
không bao giờ là điểm chết của lượt (Sếp chốt 2026-08-31).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Tên tool — core ghi vào vệt trace, adapter dựng schema; MỘT nguồn.
TCO_TOOL_NAME = "tinh_chi_phi"


@dataclass(frozen=True, slots=True)
class TcoToolArgs:
    """Tham số LLM đã chọn khi gọi tool `tinh_chi_phi`."""

    daily_km: int | None = None
    province: str | None = None


class TcoArgResolverPort(Protocol):
    """KHÔNG raise: hỏng kiểu gì cũng trả `None` để act rơi về đường tất định."""

    async def resolve(
        self,
        *,
        user_message: str,
        vehicle_name: str,
        known_daily_km: int | None,
        known_province: str | None,
    ) -> TcoToolArgs | None: ...
