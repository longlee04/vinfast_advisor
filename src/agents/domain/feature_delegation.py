"""Khách GIAO VIỆC chọn cho agent — tách khỏi lời từ chối trả lời.

`slot_salvage.is_non_answer` gộp `"tư vấn giúp"` và `"tùy em"` chung nhóm với
`"chưa biết"`. Ở lượt hỏi ngân sách, gộp như vậy đúng: không câu nào rút ra được
một con số. Ở lượt hỏi TÍNH NĂNG thì sai — khách vừa giao việc chọn cho agent, mà
hệ đóng ô lại rồi đi thẳng tới đề xuất.

**Không sửa `is_non_answer`.** Bốn chỗ đang dùng nó với bốn sắc thái khác nhau
(`chain` đặt cờ `customer_declined`, `slot_salvage.salvage_slot`,
`slot_extraction`, `slot_planning`); nới nó ra là nới cả bốn. Vị từ này đứng
riêng và được hỏi TRƯỚC.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Xin gặp NGƯỜI, không phải giao việc cho agent. Phải loại TRƯỚC mọi mẫu dưới:
#: "tư vấn viên hỗ trợ" chạm cả `tu van` lẫn `ho`, nên không chặn ở đây thì một
#: câu xin chuyển người biến thành một lời nhờ agent chọn tính năng.
_HUMAN_REQUEST_PATTERN: Final[re.Pattern[str]] = re.compile(r"\btu van vien\b")

#: Động từ giao việc. `xem` KHÔNG nằm ở đây: "cho anh xem xe có khoá chống trộm"
#: là khách nêu tính năng mình muốn, không phải nhờ ai chọn.
_DELEGATION_VERBS: Final[str] = r"(?:chon|tu van|goi y|quyet dinh)"

#: Khoảng cách đo bằng TỪ, tối đa ba từ, không phải `[^.?!]*`.
#:
#: "em chọn tính năng giúp anh" có hai từ chen giữa động từ và chữ "giúp", nên
#: không cho phép khoảng cách nào thì mẫu vô dụng. Nhưng đuôi tự do là đúng cái
#: bẫy mục 3.5 (`luong-tu-van-da-sua.md`): bản nháp trước để đuôi nhận chữ tự do
#: và nuốt mất `"khoá chống trộm"`. Ở đây khoảng cách bị kẹp giữa HAI từ bắt
#: buộc, và đếm bằng từ nên không trôi qua hết câu.
_DELEGATION_PATTERN: Final[re.Pattern[str]] = re.compile(rf"\b{_DELEGATION_VERBS}\b(?:\s+\w+){{0,3}}\s+(?:giup|ho)\b")

#: Dạng "nhờ em chọn" — giao việc bằng chữ "nhờ", không có "giúp"/"hộ" nào ở sau.
#: Chữ "nhờ" một mình KHÔNG đủ: "nhờ anh báo giá giúp" là việc khác hẳn, nên
#: động từ chọn vẫn phải có mặt trong ba từ kế tiếp.
_ASK_PATTERN: Final[re.Pattern[str]] = re.compile(rf"\bnho\b(?:\s+\w+){{0,2}}\s+{_DELEGATION_VERBS}\b")

#: Giao việc trọn gói, không nêu động từ: "tùy em". Phải là từ TRỌN VẸN.
_DEFER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\btuy\s+(?:em|ban|anh|chi)\b")


def delegates_choice_to_agent(user_message: str) -> bool:
    """Khách có đang nhờ agent chọn thay mình không."""

    text = _normalize(user_message)
    if not text or _HUMAN_REQUEST_PATTERN.search(text) is not None:
        return False
    return any(pattern.search(text) is not None for pattern in (_DELEGATION_PATTERN, _ASK_PATTERN, _DEFER_PATTERN))


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


__all__ = ["delegates_choice_to_agent"]
