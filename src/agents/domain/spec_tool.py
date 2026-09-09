"""Hợp đồng tool `tra_thong_so` — tool thứ ba, cùng khuôn `tco_tool`/`location_tool`.

LLM chỉ chọn NHÓM thông số (khoá trong `SPEC_GROUPS`) cho câu hỏi mà bộ từ khoá
`render._SPEC_QA` chịu thua ("cốp nó nuốt nổi hai vali không?"). Con số trả
khách vẫn 100%% từ cột catalog + lời đánh giá tất định — LLM không sinh số.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Tên tool — core ghi vào vệt trace, adapter dựng schema; MỘT nguồn.
SPEC_TOOL_NAME = "tra_thong_so"

#: Khoá nhóm → mô tả cho schema. Khoá PHẢI khớp `render.SPEC_GROUP_KEYS` —
#: `tests` chốt hai bản không trôi nhau.
SPEC_GROUPS: dict[str, str] = {
    # tam_di TRƯỚC sac — khớp thứ tự render.SPEC_GROUP_KEYS (bug ACC-07).
    "tam_di": "quãng đường xe đi được mỗi lần sạc, tầm hoạt động",
    "sac": "thời gian sạc, sạc nhanh, pin kWh",
    "pin": "dung lượng và loại pin",
    "cho_ngoi": "số chỗ ngồi, chở được mấy người",
    "cop": "khoang hành lý, cốp, chở đồ/vali",
    "cong_suat": "công suất động cơ, mô-men xoắn, xe có mạnh không",
    "tang_toc": "tăng tốc 0-100",
    "toc_do": "tốc độ tối đa",
    "tai_trong": "tải trọng, chở nặng",
    "yen": "chiều cao yên xe máy",
    "bang_lai": "yêu cầu bằng lái",
    "kieu_dang": "kiểu dáng thân xe",
}


@dataclass(frozen=True, slots=True)
class SpecToolArgs:
    """Nhóm thông số LLM đã chọn; `None` = câu không hỏi thông số nào."""

    group: str | None = None


class SpecArgResolverPort(Protocol):
    """KHÔNG raise: hỏng kiểu gì cũng trả `None` để act rơi về bảng tổng quan."""

    async def resolve(self, *, question: str, vehicle_name: str) -> SpecToolArgs | None: ...
