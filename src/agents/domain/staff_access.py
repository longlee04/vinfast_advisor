"""Phạm vi dữ liệu của nhân sự nội bộ (plan Customer 360, Phase 0).

Admin xem được mọi thứ; tư vấn viên chỉ xem khách/phiên của mình. Vị từ SQL cụ
thể nằm ở adapter (`conversation_repository._advisor_scope`), còn quy ước danh
tính và luật che số điện thoại thì ở đây — thuần Python, không FastAPI/SQLAlchemy.
"""

from __future__ import annotations

from typing import Final

ADMIN_ROLE: Final[str] = "admin"


def is_admin(role: str) -> bool:
    """`role` là giá trị chuỗi của `Role` (`"admin"`/`"advisor"`/`"customer"`)."""

    return role.lower() == ADMIN_ROLE


def staff_identifiers(staff_id: str, email: str | None = None) -> tuple[str, ...]:
    """Mọi định danh có thể trỏ tới cùng một nhân sự.

    Bảng `customer_advisor_assignments` lưu `advisor_id` theo id HOẶC email tuỳ
    màn phân công đã gửi gì (`assignment_repository.list_assigned_customers_for_advisor`
    cũng khớp cả hai), nên mọi phép lọc theo phân công phải khớp cả hai.
    """

    if email and email != staff_id:
        return (staff_id, email)
    return (staff_id,)


def can_list_other_advisor(role: str, requester_ids: tuple[str, ...], target_advisor_id: str | None) -> bool:
    """Chỉ admin được xem danh sách khách của một TVV khác."""

    if target_advisor_id is None or target_advisor_id in requester_ids:
        return True
    return is_admin(role)


__all__ = ["ADMIN_ROLE", "can_list_other_advisor", "is_admin", "staff_identifiers"]
