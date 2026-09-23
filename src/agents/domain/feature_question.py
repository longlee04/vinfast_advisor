"""Câu hỏi CÓ/KHÔNG về một trang bị — bộ dò thuần, dùng chung hai tầng.

`understand` cần nó để đánh dấu lượt (chọn đúng đường ở `policy`), `render` cần
nó để dựng câu trả lời. Một bộ dò, không hai bản.

Đo trên máy 2026-09-23: "xe vf9 có trợ lý ảo không" nhận cả bảng thông số, còn
"xe có trợ lý ảo không" (chưa nêu xe nào) thì bị hỏi ngân sách — hai lượt cùng
một ý định mà đi hai đường sai khác nhau.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

import re
from typing import Final

#: Câu hỏi CÓ/KHÔNG về một trang bị: "VF 9 có trợ lý ảo không", "xe này có
#: cửa sổ trời không". Bắt phần giữa "có" và "không" — đó chính là thứ khách hỏi.
_YES_NO_FEATURE: Final[re.Pattern[str]] = re.compile(
    r"\bcó\s+(?P<thing>[^?]{2,40}?)\s+(?:hay\s+)?(?:không|ko|hông|chưa)\b",
    re.IGNORECASE,
)
#: Từ nối/động từ lọt vào giữa làm bản trích hết nghĩa ("có được trang bị X không").
_FEATURE_NOISE: Final[tuple[str, ...]] = ("được", "trang bị", "tích hợp", "kèm", "sẵn", "cái", "loại", "thêm")


def asked_feature(question: str) -> str:
    """Trang bị khách hỏi CÓ/KHÔNG, hoặc rỗng. Thuần, không đọc catalog.

    Khách hỏi một câu có/không mà nhận cả bảng thông số (Sếp 2026-09-23: "xe vf9
    có trợ lý ảo không" → nguyên bản mô tả VF 9) là trả lời sai ý định: họ hỏi
    MỘT điều, bot đáp bằng MỌI điều và điều họ hỏi thì không có trong đó.
    """

    found = _YES_NO_FEATURE.search(question or "")
    if found is None:
        return ""
    thing = " ".join(found.group("thing").split())
    for noise in _FEATURE_NOISE:
        thing = re.sub(rf"^{re.escape(noise)}\s+", "", thing, flags=re.IGNORECASE).strip()
    return thing if len(thing) >= 2 else ""


__all__ = ["asked_feature"]
