"""Che thông tin liên hệ của khách trước khi hiển thị cho nhân sự (plan Customer 360, Phase 0).

`conversation_memory.redact_sensitive` chỉ xoá mẫu BÍ MẬT (mật khẩu, token, API
key, chuỗi kết nối) — nó không đụng tới số điện thoại, email hay số CCCD mà khách
tự gõ vào chat. Module này là lớp thứ hai, dành riêng cho dữ liệu cá nhân:

- `redact_pii`: thay SĐT/email/CCCD bằng nhãn cố định, dùng cho bằng chứng nút
  thắt, transcript hay tóm tắt hiện ở màn nội bộ.
- `mask_phone`: che giữa số, giữ đầu/đuôi để TVV còn nhận ra — dùng ở màn danh sách.
- `contains_phone`: "khách có để lại SĐT không" là tín hiệu tất định, không cần LLM.

THUẦN Python: không FastAPI/SQLAlchemy/LLM SDK.
"""

from __future__ import annotations

import re
from typing import Final

PHONE_PLACEHOLDER: Final[str] = "[SĐT]"
EMAIL_PLACEHOLDER: Final[str] = "[EMAIL]"
ID_NUMBER_PLACEHOLDER: Final[str] = "[SỐ GIẤY TỜ]"

#: SĐT Việt Nam: đầu `0` hoặc `+84`/`84`, theo sau 9 chữ số, cho phép cách nhóm
#: bằng khoảng trắng, dấu chấm hoặc gạch ("0912 345 678", "+84.912.345.678").
_PHONE: Final[re.Pattern[str]] = re.compile(r"(?<![\d+])(?:\+?84|0)(?:[\s.\-]?\d){9}(?!\d)")
_EMAIL: Final[re.Pattern[str]] = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
#: CCCD 12 số, CMND 9 số — chỉ khi đứng riêng thành một cụm số liền.
_ID_NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,])(?:\d{12}|\d{9})(?![\d.,])")

_MASK_KEEP_HEAD: Final[int] = 4
_MASK_KEEP_TAIL: Final[int] = 3


def redact_pii(text: str) -> str:
    """Thay SĐT, email, số giấy tờ bằng nhãn; phần còn lại giữ nguyên văn."""

    redacted = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    redacted = _PHONE.sub(PHONE_PLACEHOLDER, redacted)
    return _ID_NUMBER.sub(ID_NUMBER_PLACEHOLDER, redacted)


def contains_phone(text: str) -> bool:
    """Câu có chứa một SĐT Việt Nam không."""

    return _PHONE.search(text) is not None


def mask_phone(phone: str) -> str:
    """`0912345678` → `0912***678`. Chuỗi quá ngắn thì che toàn bộ."""

    digits = re.sub(r"\D", "", phone)
    if phone.strip().startswith("+"):
        digits = "+" + digits
    if len(digits) <= _MASK_KEEP_HEAD + _MASK_KEEP_TAIL:
        return "***" if digits else ""
    return f"{digits[:_MASK_KEEP_HEAD]}***{digits[-_MASK_KEEP_TAIL:]}"


__all__ = [
    "EMAIL_PLACEHOLDER",
    "ID_NUMBER_PLACEHOLDER",
    "PHONE_PLACEHOLDER",
    "contains_phone",
    "mask_phone",
    "redact_pii",
]
