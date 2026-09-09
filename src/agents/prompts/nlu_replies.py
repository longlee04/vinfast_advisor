"""[Lớp 4] Câu chữ của hai nhánh chưa đủ tin cậy — template DETERMINISTIC.

Không có lần gọi LLM nào ở đây, cùng lý do với `domain/catalog_browse.py`: nội
dung là template ghép từ chính thứ hệ thống vừa nhận ra, nên nó không mang khẳng
định sự thật nào cần kiểm chứng, và vì vậy A7-4 cho đi thẳng tới khách mà không
qua hàng đợi duyệt.

Hai nhánh, hai mục đích khác nhau:

- **Xác nhận** (confidence trung bình): hệ thống ĐÃ hiểu ra một điều cụ thể và
  chỉ cần khách gật đầu. Câu hỏi phải nêu đúng thứ đã hiểu, không hỏi chung
  chung — "ý anh/chị là VF 5 phải không ạ" hỏi được, "anh/chị nói rõ hơn được
  không ạ" thì không, vì nó vứt bỏ thông tin vừa suy ra và bắt khách gõ lại.
- **Hỏi làm rõ** (confidence thấp): hệ thống không nhận ra gì. Lúc này lối thoát
  bắt buộc là gợi ý cụ thể — PRD 5.9 đòi mọi câu từ chối phải kèm lối thoát, và
  một danh sách mẫu xe bấm được chính là lối thoát rẻ nhất cho khách.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

#: Nhãn nút bấm cho hai lựa chọn của câu xác nhận.
CONFIRM_YES_LABEL: Final[str] = "Đúng rồi"
CONFIRM_NO_LABEL: Final[str] = "Không phải"

#: Giá trị gửi lại khi khách bấm nút. Phải nằm trong `_AFFIRMATIONS`/`_DENIALS`
#: của `domain/pending_intent_confirmation` — nếu lệch, nút bấm sẽ rơi vào nhánh
#: "khách nói chuyện khác" và câu xác nhận tự huỷ ngay khi khách bấm đồng ý.
CONFIRM_YES_VALUE: Final[str] = "đúng"
CONFIRM_NO_VALUE: Final[str] = "không phải"

CLARIFY_QUESTION: Final[str] = (
    "Dạ em chưa nắm rõ ý anh/chị. Anh/chị cho em xin tên mẫu xe cần tra cứu, "
    "hoặc mô tả nhu cầu (số người thường chở, ngân sách, quãng đường mỗi ngày) "
    "để em tư vấn giúp ạ."
)

CLARIFY_SUGGESTION_LEAD: Final[str] = "Anh/chị cũng có thể chọn nhanh một mẫu đang được quan tâm:"


def confirm_vehicle_question(vehicle_name: str) -> str:
    """Câu xác nhận khi đã nhận ra TÊN MỘT MẪU XE."""

    return f"Dạ, có phải anh/chị đang hỏi về {vehicle_name} không ạ?"


def confirm_text_question(proposed_text: str) -> str:
    """Câu xác nhận khi chỉ nhận ra nội dung câu, chưa ra tên xe cụ thể.

    Nhắc lại nguyên văn bản đã hiểu để khách tự đối chiếu: đọc "ý anh/chị là
    'thông tin xe VF 5'?" thì khách biết ngay hệ thống hiểu đúng hay sai, còn
    "em hiểu là anh/chị muốn tra cứu" thì không nói lên điều gì kiểm chứng được.
    """

    return f"Dạ, ý anh/chị là “{proposed_text}” phải không ạ?"


def clarify_message(suggestions: Sequence[str] = ()) -> str:
    """Câu hỏi làm rõ, kèm gợi ý mẫu xe khi có."""

    if not suggestions:
        return CLARIFY_QUESTION
    return f"{CLARIFY_QUESTION}\n\n{CLARIFY_SUGGESTION_LEAD}"


__all__ = [
    "CLARIFY_QUESTION",
    "CLARIFY_SUGGESTION_LEAD",
    "CONFIRM_NO_LABEL",
    "CONFIRM_NO_VALUE",
    "CONFIRM_YES_LABEL",
    "CONFIRM_YES_VALUE",
    "clarify_message",
    "confirm_text_question",
    "confirm_vehicle_question",
]
