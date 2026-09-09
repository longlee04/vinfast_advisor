"""[A7-9] Câu chữ cho câu trả lời giá lăn bánh.

Template deterministic, KHÔNG gọi LLM — cùng lý do với `domain/catalog_reply.py`:
mọi con số ở đây đến từ công thức, và một bước diễn đạt bằng LLM chỉ thêm một chỗ
có thể gõ sai chữ số.
"""

from __future__ import annotations

from src.agents.domain.catalog_reply import CLOSING_NOTE, format_vnd
from src.agents.domain.pricing_intent import PROVINCES
from src.agents.domain.reply_format import bold, field_line
from src.agents.tools.on_road_price import OnRoadPriceBreakdown

#: Câu hỏi lại khi thiếu slot bắt buộc. Không gọi tool với giá trị mặc định:
#: một con số phí của tỉnh khác là con số SAI gửi cho khách.
MISSING_PROVINCE_QUESTION = (
    "Dạ, phí trước bạ và phí biển số khác nhau theo từng tỉnh/thành. "
    "Quý khách dự định đăng ký xe ở tỉnh/thành nào để em tính giá lăn bánh chính xác ạ?"
)
MISSING_VARIANT_QUESTION = "Dạ, Quý khách cho em biết mẫu xe và phiên bản cần tính giúp ạ?"


def _province_name(code: str) -> str:
    """Tên hiển thị của mã tỉnh; không tra được thì trả lại chính mã đó."""

    for name, value in PROVINCES.items():
        if value == code:
            return name.title()
    return code


def render_on_road_price(breakdown: OnRoadPriceBreakdown, vehicle_name: str) -> str:
    """Bảng giá lăn bánh — liệt kê breakdown, KHÔNG cần disclaimer.

    Đây là số tính từ công thức cố định trên biểu phí đã công bố, không phải ước
    tính. Nhưng nếu biểu phí dùng để tính là biểu TOÀN QUỐC chứ không phải của
    đúng tỉnh khách hỏi thì phải nói ra — để khách tưởng con số đã theo tỉnh
    mình trong khi không phải là hiểu sai một khoản tiền thật.
    """

    lines = [
        f"Dạ, giá lăn bánh {bold(vehicle_name)} tại {bold(_province_name(breakdown.province))}:",
        "",
        f"{bold('Các khoản cấu thành')}:",
        field_line("Giá niêm yết", format_vnd(breakdown.listed_price_vnd)),
        field_line("Lệ phí trước bạ", format_vnd(breakdown.registration_fee_vnd)),
        field_line("Phí đăng ký, biển số", format_vnd(breakdown.plate_fee_vnd)),
        field_line(
            "Bảo hiểm TNDS bắt buộc (1 năm)",
            format_vnd(breakdown.mandatory_insurance_vnd),
        ),
        "",
        f"{bold('Tổng giá lăn bánh')}: {format_vnd(breakdown.total_vnd)}",
    ]
    if not breakdown.province_specific:
        lines.extend(
            [
                "",
                f"{bold('Lưu ý')}: biểu phí em đang áp dụng là mức chung toàn quốc, chưa có bảng "
                "riêng cho tỉnh/thành này; mức thực tế tại địa phương có thể chênh lệch.",
            ]
        )
    return "\n".join([*lines, "", CLOSING_NOTE])


__all__ = [
    "MISSING_PROVINCE_QUESTION",
    "MISSING_VARIANT_QUESTION",
    "render_on_road_price",
]
