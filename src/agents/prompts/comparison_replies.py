"""[COMPARE_VEHICLES] Câu chữ cố định của nhánh so sánh — template DETERMINISTIC.

Cùng vai và cùng lý do với `prompts/nlu_replies.py`: không lần gọi LLM nào ở đây.
Nội dung là template ghép từ chính thứ hệ thống vừa nhận ra, nên nó không mang
khẳng định sự thật nào cần kiểm chứng, và A7-4 cho đi thẳng tới khách mà không
qua hàng đợi duyệt.

Gom về một file thay vì rải trong `services/compare_vehicles.py` vì đây là chỗ
DUY NHẤT được sửa khi phòng thương hiệu đổi tông giọng. Một câu chữ nằm lẫn
trong logic là một câu chữ sẽ bị sửa ở một chỗ và quên ở chỗ còn lại.

[KHÁC BIỆT] Repo chưa có cơ chế i18n (không có `gettext`, không có bảng locale —
đã grep toàn `src/`); mọi câu gửi khách đều là hằng số tiếng Việt trong
`prompts/`. File này theo đúng quy ước đó thay vì dựng một tầng i18n mới cho một
tính năng.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

#: Câu mở trạng thái `AWAITING_COMPARE_TARGETS`.
#:
#: NGUYÊN VĂN theo đặc tả, kể cả emoji và cách xưng "Vivi" — đây là câu duy nhất
#: trong nhánh so sánh được chốt sẵn từ phòng thương hiệu, nên nó KHÔNG đi qua
#: LLM: một lần diễn đạt lại là một lần lệch tông giọng mà không ai review.
COMPARE_TARGETS_QUESTION: Final[str] = (
    "Xin chào Quý khách! Quý khách muốn so sánh các dòng xe VinFast cụ thể nào "
    "ạ? Ví dụ như VF 3, VF 5, VF 8… hay các dòng xe khác? Em sẵn sàng hỗ trợ "
    "Quý khách ngay! 😊"
)

#: Lượt hỏi lại CUỐI CÙNG khi câu trả lời trước không nêu được xe nào. Khác câu
#: mở ở chỗ nêu ví dụ lấy từ catalog thật, không phải danh sách viết tay: khách
#: không hiểu câu hỏi lần đầu thì hỏi lại y nguyên chỉ tốn thêm một lượt.
COMPARE_TARGETS_RETRY_LEAD: Final[str] = "Dạ, Quý khách cho em xin TÊN các mẫu xe muốn so sánh giúp em ạ."

#: Câu thoát trạng thái sau khi đã hỏi hết số lần cho phép.
COMPARE_TARGETS_GIVE_UP: Final[str] = (
    "Dạ, em chưa nhận ra mẫu xe Quý khách muốn so sánh ạ. Quý khách có thể xem "
    "danh mục xe VinFast đang bán rồi cho em biết hai mẫu muốn đặt cạnh nhau, "
    "hoặc mô tả nhu cầu (ngân sách, số chỗ, quãng đường mỗi ngày) để em tư vấn "
    "giúp ạ."
)

DUPLICATE_REPLY: Final[str] = (
    "Anh/chị đang nêu cùng một mẫu xe hai lần nên em chưa so sánh được ạ. "
    "Anh/chị cho em biết mẫu thứ hai muốn đặt cạnh để em lập bảng nhé."
)

TOO_MANY_REPLY_TEMPLATE: Final[str] = (
    "Anh/chị đang nêu {count} mẫu xe. Bảng so sánh chỉ đọc được khi có tối đa "
    "{limit} mẫu, anh/chị chọn giúp em {limit} mẫu muốn đặt cạnh nhau nhé."
)

MISSING_TEMPLATE: Final[str] = "Em chưa tìm thấy {names} trong danh mục hiện hành."

COMPARISON_HEADING: Final[str] = "Bảng so sánh {names}:"


def second_vehicle_question(vehicle_name: str) -> str:
    """Hỏi mẫu xe còn lại khi mới nắm được đúng một xe.

    Ngắn hơn hẳn `COMPARE_TARGETS_QUESTION` là có chủ đích: khách đã trả lời một
    lần rồi, lặp lại cả câu chào là bắt họ đọc lại thứ họ vừa đọc.
    """

    return f"Dạ, Quý khách muốn so sánh {vehicle_name} với dòng xe nào nữa ạ?"


def compare_targets_retry_question(suggestions: Sequence[str] = ()) -> str:
    """Câu hỏi lại, kèm ví dụ mẫu xe lấy từ danh mục thật.

    Danh sách rỗng (chưa nối catalog) thì chỉ còn phần dẫn — vẫn là một câu hỏi
    dùng được, thay vì một câu cụt "Ví dụ như: ".
    """

    if not suggestions:
        return COMPARE_TARGETS_RETRY_LEAD
    return f"{COMPARE_TARGETS_RETRY_LEAD} Ví dụ: {', '.join(suggestions)}."


__all__ = [
    "COMPARE_TARGETS_GIVE_UP",
    "COMPARE_TARGETS_QUESTION",
    "COMPARE_TARGETS_RETRY_LEAD",
    "COMPARISON_HEADING",
    "DUPLICATE_REPLY",
    "MISSING_TEMPLATE",
    "TOO_MANY_REPLY_TEMPLATE",
    "compare_targets_retry_question",
    "second_vehicle_question",
]
