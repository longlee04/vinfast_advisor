"""[A8-4] Chặn theo vai trò cho nhóm endpoint vận hành.

Guard ở đây dùng chung, không riêng notice: A10-5 (màn Admin duyệt hàng loạt của
Khối 1) gắn `require_admin` vào endpoint catalog của mình thay vì viết lại một
cơ chế thứ hai — hai cơ chế phân quyền song song là chỗ lệch nhau âm thầm.

`current_staff` là điểm nối danh tính: composition của app thật ghi đè nó bằng
phiên đăng nhập của `src/auth/`; khi chưa nối, mọi endpoint trả 401 chứ không
mặc định cho qua.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from src.auth.domain.authorization import Role

STAFF_ROLES = frozenset({Role.ADVISOR, Role.ADMIN})


@dataclass(frozen=True)
class StaffIdentity:
    """Người đang gọi endpoint vận hành."""

    staff_id: str
    role: Role
    email: str | None = None


async def current_staff() -> StaffIdentity:
    """Danh tính người gọi — app thật ghi đè bằng phiên đăng nhập của `src/auth/`."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chưa nối danh tính đăng nhập cho API vận hành",
    )


def require_staff(identity: StaffIdentity = Depends(current_staff)) -> StaffIdentity:
    """Chỉ nhân sự nội bộ (`ADVISOR`/`ADMIN`) đi tiếp; khách bị chặn."""
    if identity.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ nhân sự nội bộ được dùng chức năng này",
        )
    return identity


def require_admin(identity: StaffIdentity = Depends(current_staff)) -> StaffIdentity:
    """Chỉ `ADMIN` đi tiếp — `CUSTOMER` và `ADVISOR` đều nhận 403."""
    if identity.role is not Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Admin được dùng chức năng quản trị này",
        )
    return identity


async def optional_staff(request: Request) -> StaffIdentity | None:
    """Trả về StaffIdentity nếu đã đăng nhập nội bộ, ngược lại trả về None."""
    override = request.app.dependency_overrides.get(current_staff)
    if override:
        try:
            import inspect

            res = override(request) if inspect.signature(override).parameters else override()
            if inspect.iscoroutine(res):
                res = await res
            return res
        except Exception:
            return None
    return None
