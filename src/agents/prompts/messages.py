"""Tập trung chuỗi tĩnh của agent để tiện i18n và audit nội dung (Task 4.3).

Preview messages chỉ liệt kê fact thô từ catalog — KHÔNG chứa lý do khuyến nghị
cá nhân hoá, KHÔNG gọi LLM.
"""

from __future__ import annotations

from decimal import Decimal

_VND_UNITS = [(1_000_000_000_000, "nghìn tỷ"), (1_000_000_000, "tỷ"), (1_000_000, "triệu")]


def format_vnd(amount: Decimal | int | float | None) -> str:
    """Hiển thị số tiền VND gọn gàng; `None` trả về 'liên hệ'."""

    if amount is None:
        return "liên hệ"
    value = float(amount)
    for threshold, label in _VND_UNITS:
        if value >= threshold:
            rounded = value / threshold
            # Bỏ phần thập phân nếu là số nguyên
            text = f"{rounded:.1f}".rstrip("0").rstrip(".")
            return f"{text} {label}"
    return f"{int(value):,} đ"


def preview_header(budget_text: str | None, count: int) -> str:
    """Dòng mở đầu preview, trung lập, không khuyến nghị."""

    if budget_text:
        return f"Dưới {budget_text}, VinFast có {count} mẫu phù hợp:"
    return f"VinFast có {count} mẫu phù hợp:"


def preview_item(name: str, price_text: str, seats_text: str, range_text: str) -> str:
    """Một dòng xe trong preview."""

    return f"• {name} ({price_text}) - {seats_text}, {range_text}"


def preview_footer(has_more: bool) -> str:
    """Dòng kết preview, gợi ý khách bổ sung thông tin."""

    if has_more:
        return "Còn nhiều mẫu khác, anh/chị cho em thêm chi tiết để lọc chính xác hơn nhé."
    return "Anh/chị quan tâm mẫu nào, hoặc cho em thêm thông tin để tư vấn sâu hơn nhé."


def empty_preview_message() -> str:
    """Khi PARTIAL không tìm được ứng viên nào sau 1 lần nới."""

    return "Chưa có mẫu nào khớp giá này, anh/chị cho em xin thêm loại xe quan tâm nhé."
