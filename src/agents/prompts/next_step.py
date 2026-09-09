"""[A7-5] Câu đáp cho lượt khách chỉ xác nhận — template, KHÔNG gọi LLM.

Khách nói "ok xe có vẻ được đấy" thì việc cần làm là dẫn sang bước kế tiếp (lái
thử, giữ xe, hỏi chi tiết còn thiếu), không phải sinh lại báo giá và cũng không
phải hỏi lại slot từ đầu.

[GIẢ ĐỊNH] Dùng template thay vì một lần gọi LLM ngắn: câu này không chứa con số
nào và không phụ thuộc ngữ cảnh sâu, nên một lần gọi LLM chỉ thêm độ trễ và thêm
một chỗ có thể bịa. Khi cần cá nhân hoá hơn thì đổi thân hàm, chữ ký giữ nguyên.
"""

from __future__ import annotations

from src.agents.prompts.persona import ASSISTANT_SELF, CUSTOMER_ADDRESS

NEXT_STEP_REPLY = (
    f"Dạ vâng {CUSTOMER_ADDRESS} ạ. {ASSISTANT_SELF.capitalize()} có thể đặt lịch lái thử "
    f"để {CUSTOMER_ADDRESS} trải nghiệm trực tiếp, hoặc gửi thêm thông tin về màu sắc, "
    f"phiên bản và chính sách bàn giao. {CUSTOMER_ADDRESS.capitalize()} muốn xem phần nào "
    "trước ạ?"
)

ACKNOWLEDGMENT_WHILE_PENDING_REPLY = (
    f"Dạ {ASSISTANT_SELF} ghi nhận ạ. Nội dung này vẫn đang chờ tư vấn viên kiểm tra, "
    f"{CUSTOMER_ADDRESS} chờ {ASSISTANT_SELF} một chút nhé."
)


def next_step_reply() -> str:
    """Lời dẫn sang bước kế tiếp sau một báo giá đã được gửi tự động."""

    return NEXT_STEP_REPLY


def acknowledgment_while_pending_reply() -> str:
    """Lời đáp khi báo giá trước đó VẪN đang nằm trong hàng đợi duyệt.

    Không đẩy thêm một mục duyệt nữa: tư vấn viên đã có đúng nội dung đó trên
    bàn, thêm bản sao chỉ làm hàng đợi dài ra mà không ai cần duyệt hai lần.
    """

    return ACKNOWLEDGMENT_WHILE_PENDING_REPLY


__all__ = [
    "ACKNOWLEDGMENT_WHILE_PENDING_REPLY",
    "NEXT_STEP_REPLY",
    "acknowledgment_while_pending_reply",
    "next_step_reply",
]
