"""Khoá ký cho giấy phép khung giờ lái thử.

`domain/test_drive_booking` giữ phép ký và phép kiểm, và nó THUẦN — không đọc
biến môi trường. Chỗ duy nhất biết khoá nằm ở đây, đúng tầng service, để cả
`chain`, route và `nodes/` dùng chung một nguồn.

**Tách khoá theo mục đích.** Khoá không dùng thẳng `AUTH_JWT_SIGNING_KEY` mà dẫn
xuất qua HMAC với một nhãn riêng. Một khoá ký hai loại giấy khác nhau là mở
đường cho việc lấy chữ ký của loại này ghép sang loại kia.

Ở `production`, THIẾU KHOÁ LÀ CHẾT NGAY khi khởi động. Bản đầu chỉ ghi một dòng
cảnh báo rồi sinh khoá ngẫu nhiên cho tiến trình — trên một máy chạy nhiều
worker, mã do worker A cấp bị worker B từ chối vì hai khoá khác nhau. Khách bấm
đúng nút mình vừa nhận và nghe "khung giờ này không đặt được", lúc có lúc không
tuỳ request rơi vào worker nào, và gần như không lần ra được từ log. Chết sớm
đọc được hơn nhiều.

Dev và bộ test (một tiến trình) vẫn rơi về khoá ngẫu nhiên kèm cảnh báo, để
không phải khai một biến môi trường chỉ để chạy thử.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime
from functools import lru_cache
from typing import Final

from src.agents.domain.test_drive_booking import BookingChoice, decode_slot_choice, encode_slot_choice

logger = logging.getLogger(__name__)

#: Nhãn tách mục đích. Đổi nhãn là làm mọi mã đang lưu hành hết hiệu lực.
_PURPOSE: Final[bytes] = b"p150/test-drive-slot/v1"

#: Thứ tự đọc khoá gốc: khoá riêng cho việc này trước, rồi khoá ký của auth.
_SOURCES: Final[tuple[str, ...]] = ("TEST_DRIVE_SLOT_SECRET", "AUTH_JWT_SIGNING_KEY")


@lru_cache(maxsize=1)
def slot_signing_key() -> bytes:
    """Khoá ký, dẫn xuất một lần cho cả tiến trình."""

    for name in _SOURCES:
        raw = os.environ.get(name)
        if raw:
            return hmac.new(raw.encode("utf-8"), _PURPOSE, hashlib.sha256).digest()
    if os.environ.get("APP_ENV", "development").strip().lower() == "production":
        raise RuntimeError(
            "Thiếu TEST_DRIVE_SLOT_SECRET (hoặc AUTH_JWT_SIGNING_KEY) ở production: "
            "khoá ngẫu nhiên theo tiến trình làm mã khung giờ của worker này bị worker khác từ chối."
        )
    logger.warning(
        "slot_token: khong tim thay %s — dung khoa ngau nhien cho tien trinh nay, "
        "ma cap boi worker nay se khong dung duoc o worker khac",
        " hoac ".join(_SOURCES),
    )
    return secrets.token_bytes(32)


def issue_slot_token(
    *,
    showroom: str,
    scheduled_at: datetime,
    session_id: str,
    customer_id: str,
    issued_at: datetime,
) -> str:
    """Cấp giấy phép cho một khung giờ, buộc vào phiên và khách."""

    return encode_slot_choice(
        showroom=showroom,
        scheduled_at=scheduled_at,
        session_id=session_id,
        customer_id=customer_id,
        issued_at=issued_at,
        secret=slot_signing_key(),
    )


def read_slot_token(
    user_message: str,
    *,
    session_id: str,
    customer_id: str,
    now: datetime,
) -> BookingChoice | None:
    """Đọc giấy phép của ĐÚNG phiên và khách này, hoặc `None`."""

    return decode_slot_choice(
        user_message,
        session_id=session_id,
        customer_id=customer_id,
        now=now,
        secret=slot_signing_key(),
    )


__all__ = ["issue_slot_token", "read_slot_token", "slot_signing_key"]
