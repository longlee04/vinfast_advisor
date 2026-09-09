"""Khách chọn TẤT CẢ tính năng vừa được liệt kê.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

**Bug thật Sếp báo 2026-08-26**: khách đáp `"có tất cả"` cho câu hỏi tính năng và
nhận về lời từ chối phạm vi. Vệt quyết định cho thấy **cả tám cờ đều `false`** —
`customer_declined` đúng là `false` (đây không phải từ chối), mà cũng không cờ
nào nhận ra "khách chọn hết". Không cờ nào bật thì `classify_scope` không có gì
để mở cửa.

**Phải làm HAI việc, không chỉ một.** Mở cửa phạm vi mà không gán tính năng thì
khách nói "tất cả" cũng như chưa nói gì: `feature_mentions` vẫn rỗng, xếp hạng
không đổi, và lượt sau agent hỏi lại đúng câu vừa hỏi. Mã cụ thể suy từ chính câu
hỏi lượt trước — xem `offered_feature_codes`.

Tách khỏi `feature_delegation` một cách cố ý: "tất cả" là khách TỰ chọn hết, còn
"em chọn hộ anh" là nhường quyền quyết định. Hai ý khác nhau nên hai đường xử lý
khác nhau — gộp lại thì một trong hai mất.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Giá trị "KHÔNG đọc được lượt trước".
#:
#: Khác `None` (chắc chắn không có câu hỏi nào) và khác một câu hỏi thật: nó chỉ
#: nói "coi như có hỏi" để lượt chảy tiếp, còn `offered_feature_codes` suy từ nó
#: ra tập RỖNG — không gán bừa tính năng nào cho khách.
#:
#: Đặt ở `domain/` vì cả `services/conversation` lẫn `chain` đều cần chung một
#: giá trị; để ở một trong hai thì tầng kia phải import ngược.
UNKNOWN_QUESTION: Final[str] = "?"


def _fold(value: str) -> str:
    """Bỏ dấu + gộp khoảng trắng. Cùng kiểu với `claim_policy._fold_diacritics`."""

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


#: Câu "chọn hết" đứng MỘT MÌNH.
#:
#: Cùng khuôn với `slot_salvage._STANDALONE_REFUSAL_PATTERN`, và cùng lý do: lõi
#: phải là TỪ TRỌN VẸN (`\b`), đuôi chỉ nhận một TẬP ĐÓNG những từ không mang
#: thông tin. Bài học Sếp tự bắt được — bản nháp để đuôi nhận chữ tự do thì
#: "khoá chống trộm" bị nuốt thành lời từ chối — áp nguyên vào đây.
#:
#: `hết` một mình KHÔNG đủ: "hết tiền", "hết pin", "hết hàng" đều là câu thật
#: mang thông tin. Nó chỉ tính khi đi sau một động từ chọn ("lấy hết", "chọn hết").
_SELECT_ALL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:da|u|a|vang)?\s*"
    r"(?:cho\s+(?:anh|em|minh|toi)|anh|em|minh|toi)?\s*"
    r"(?:"
    r"(?:co|lay|chon|muon|can|thich|dung)?\s*(?:tat ca|toan bo|het thay|ca ba|ca hai)"
    r"|(?:lay|chon|muon|can)\s+het"
    r")\b"
    r"(?:\s*(?:luon|nhe|nha|a|ah|di|deu|duoc|nay|do|cac|nhung|"
    r"tinh nang|cai|thu|muc|option|di a|cho anh|cho em|cho minh|cho toi))*\s*[.!]?$"
)


def wants_all_offered_features(user_message: str) -> bool:
    """Khách chọn TẤT CẢ tính năng vừa liệt kê?

    Chỉ nhận câu đứng một mình. Câu có thêm nội dung khác ("tất cả đều đắt quá",
    "cho tôi xem tất cả xe") KHÔNG tính: chúng mang một ý riêng, và đọc thành
    "chọn hết tính năng" là gán cho khách một lựa chọn họ chưa nêu.
    """

    return _SELECT_ALL_PATTERN.match(_fold(user_message)) is not None


def offered_feature_codes(last_question: str | None) -> frozenset[str]:
    """Mã tính năng bot vừa LIỆT KÊ ở câu hỏi lượt trước.

    Suy từ chính văn bản câu hỏi thay vì thêm một cột vào DB: câu hỏi lượt 2 in
    nguyên nhãn tiếng Việt của từng mã (`- **cảnh báo điểm mù**: …`), và bảng cụm
    chữ `claim_policy._FEATURE_CLAIM_CUES` đã biết đọc đúng những nhãn đó. Một
    bảng dùng cho ba việc — chặn pitch bịa, đọc lời khách, và đọc lại lời chính
    mình — thì ba việc không thể lệch nhau.

    Import nằm trong hàm để `domain/` không dựng vòng import ở tầng module.
    """

    if not last_question:
        return frozenset()
    from src.agents.domain.claim_policy import feature_codes_mentioned

    return feature_codes_mentioned(last_question)
