"""Hợp đồng tool `tim_diem_dich_vu` — tool thứ hai của lõi v2 (sau `tinh_chi_phi`).

Cùng khuôn `domain/tco_tool.py`: LLM chỉ được LẤP CHỖ TRỐNG cho nhánh Nearby —
bộ dò từ khoá `detect_location_kinds` và tỉnh trong slot luôn thắng; resolver
hỏng thì trả `None` và lượt đi tiếp đường tất định (hỏi loại bằng nút bấm).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Tên tool — core ghi vào vệt trace, adapter dựng schema; MỘT nguồn.
LOCATION_TOOL_NAME = "tim_diem_dich_vu"


@dataclass(frozen=True, slots=True)
class LocationToolArgs:
    """Tham số LLM đã chọn khi gọi tool `tim_diem_dich_vu`.

    `kinds` giữ CHUỖI thô LLM trả — `core/act` mới là nơi đối chiếu với
    `LocationKind` và vứt giá trị lạ, cùng chỗ với mọi lớp kiểm khác.
    """

    kinds: tuple[str, ...] = ()
    area: str | None = None


class LocationArgResolverPort(Protocol):
    """KHÔNG raise: hỏng kiểu gì cũng trả `None` để act rơi về đường tất định."""

    async def resolve(
        self,
        *,
        user_message: str,
        known_kinds: tuple[str, ...],
        known_area: str | None,
    ) -> LocationToolArgs | None: ...
