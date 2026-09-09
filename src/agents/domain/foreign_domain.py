"""Chủ đề rõ ràng KHÔNG phải xe — bản đọc tất định, hẹp và có chủ đích.

**Vì sao phải có, dù nó xấu.** 2026-08-26: `"tư vấn cho tôi mua cổ phiếu nào"`
được bộ phân loại phạm vi gắn `IN_SCOPE` **5/5 lần**, dù prompt đã có nguyên văn
đúng ví dụ đó là `OUT_OF_SCOPE`, và đã kiểm bản prompt mới thật sự sống trong
container. Siết prompt thêm nữa không đổi được gì — lever đó đã hết.

**Nó KHÔNG phải giải pháp tổng quát, và không cố làm thế.** Chủ đề ngoài ngành là
tập vô hạn; đuổi theo bằng một danh sách là cuộc đua không thắng được. Danh sách
này chỉ đóng vài lĩnh vực hay bị hỏi nhầm, chọn theo đúng một tiêu chí:

> **Từ khoá phải là từ KHÔNG BAO GIỜ xuất hiện trong một câu tư vấn xe thật.**

Thêm từ mới thì phải qua được tiêu chí đó, và phải thêm một ca âm tính vào
`tests/agents/unit/domain/test_foreign_domain.py`. Sai theo chiều dương (chặn
nhầm câu thật) tệ hơn nhiều so với sai theo chiều âm (lọt một câu lạc đề): lọt
thì khách nhận một câu trả lời thừa, chặn nhầm thì khách mất câu trả lời.

Vì vậy danh sách này **không có** những chữ nghe có vẻ ngoài ngành mà thật ra
hay đi cùng chuyện xe: `bảo hành`, `bảo dưỡng`, `nhà` (sạc tại nhà), `trả góp`,
`vay`, `lãi suất`, `bảo hiểm xe`.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Cụm từ chỉ một lĩnh vực khác hẳn. Mỗi cụm phải là **từ trọn vẹn** (`\b`) —
#: luật đã học từ bẫy 3.5, nơi một mẫu khớp chuỗi con nuốt mất "khoá chống trộm".
#:
#: `bao hiem nhan tho` viết đủ cụm, KHÔNG rút gọn thành `bao hiem`: bảo hiểm xe
#: là chuyện trong ngành.
_FOREIGN_DOMAIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"co phieu|chung khoan|trai phieu|"
    r"nha dat|bat dong san|"
    r"bao hiem nhan tho|bao hiem suc khoe|"
    r"nau an|nau pho|cong thuc mon|"
    r"ty gia|vang mieng"
    r")\b",
    re.IGNORECASE,
)


def names_a_foreign_domain(user_message: str) -> bool:
    """Câu có nêu rõ một lĩnh vực khác hẳn chuyện xe không."""

    return _FOREIGN_DOMAIN_PATTERN.search(_normalize(user_message)) is not None


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


__all__ = ["names_a_foreign_domain"]
