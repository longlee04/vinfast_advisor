"""Phase 0 Customer 360: che SĐT/email/CCCD trước khi hiện cho nhân sự."""

from __future__ import annotations

import pytest

from src.agents.domain.pii import (
    EMAIL_PLACEHOLDER,
    ID_NUMBER_PLACEHOLDER,
    PHONE_PLACEHOLDER,
    contains_phone,
    mask_phone,
    redact_pii,
)


@pytest.mark.parametrize(
    "text",
    [
        "số em 0912345678 nhé",
        "gọi 0912 345 678 giúp em",
        "sđt: 0912.345.678",
        "liên hệ +84912345678",
        "+84 912 345 678 là số anh",
        "84912345678",
    ],
)
def test_so_dien_thoai_bi_che(text: str) -> None:
    redacted = redact_pii(text)
    assert PHONE_PLACEHOLDER in redacted
    assert "345" not in redacted
    assert contains_phone(text)


def test_email_va_cccd_bi_che() -> None:
    redacted = redact_pii("mail an.nguyen@gmail.com, cccd 001203004567")
    assert EMAIL_PLACEHOLDER in redacted and ID_NUMBER_PLACEHOLDER in redacted
    assert "gmail" not in redacted and "001203004567" not in redacted


@pytest.mark.parametrize(
    "text",
    [
        "xe VF 5 giá 529 triệu, đi 300 km",
        "ngân sách khoảng 700.000.000 đồng",
        "nhà có 5 người, sạc 7 tiếng",
        "năm 2026 mua xe",
    ],
)
def test_cau_khong_co_pii_giu_nguyen(text: str) -> None:
    assert redact_pii(text) == text
    assert not contains_phone(text)


@pytest.mark.parametrize(
    ("phone", "masked"),
    [
        ("0912345678", "0912***678"),
        ("0912 345 678", "0912***678"),
        ("+84912345678", "+849***678"),
        ("12345", "***"),
        ("", ""),
    ],
)
def test_mask_phone(phone: str, masked: str) -> None:
    assert mask_phone(phone) == masked
