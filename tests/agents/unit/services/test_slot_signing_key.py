"""Khoá ký phải ỔN ĐỊNH ở production — không được rơi về khoá ngẫu nhiên.

Bản đầu chỉ ghi một dòng cảnh báo rồi sinh khoá ngẫu nhiên cho tiến trình. Trên
một máy chạy NHIỀU worker, hệ quả là mã do worker A cấp bị worker B từ chối: chữ
ký khác nhau vì khoá khác nhau. Khách bấm đúng nút mình vừa nhận và nghe "khung
giờ này không đặt được" — một lỗi lúc có lúc không, tuỳ request rơi vào worker
nào, và gần như không lần ra được từ log.

Nên ở `production` thì THIẾU KHOÁ LÀ CHẾT NGAY khi khởi động, chứ không âm thầm
đặt sai lịch. Dev và bộ test một tiến trình vẫn chạy được với khoá ngẫu nhiên.
"""

from __future__ import annotations

import pytest

from src.agents.services import slot_token


@pytest.fixture(autouse=True)
def _quen_khoa_cu():
    """Khoá được nhớ cho cả tiến trình — mỗi ca phải bắt đầu từ chỗ trống."""

    slot_token.slot_signing_key.cache_clear()
    yield
    slot_token.slot_signing_key.cache_clear()


def test_production_thieu_khoa_thi_chet_ngay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TEST_DRIVE_SLOT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_JWT_SIGNING_KEY", raising=False)

    with pytest.raises(RuntimeError, match="TEST_DRIVE_SLOT_SECRET"):
        slot_token.slot_signing_key()


def test_production_co_khoa_thi_chay_binh_thuong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TEST_DRIVE_SLOT_SECRET", "khoa-that")

    assert len(slot_token.slot_signing_key()) == 32


def test_cung_mot_khoa_goc_thi_moi_tien_trinh_deu_ra_cung_khoa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đây chính là thứ nhiều worker cần: dẫn xuất phải TẤT ĐỊNH."""

    monkeypatch.setenv("TEST_DRIVE_SLOT_SECRET", "khoa-that")
    dau = slot_token.slot_signing_key()
    slot_token.slot_signing_key.cache_clear()

    assert slot_token.slot_signing_key() == dau


def test_khoa_rieng_thang_khoa_cua_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tách mục đích: hai loại giấy không dùng chung một khoá."""

    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", "khoa-auth")
    monkeypatch.setenv("TEST_DRIVE_SLOT_SECRET", "khoa-rieng")
    rieng = slot_token.slot_signing_key()
    slot_token.slot_signing_key.cache_clear()
    monkeypatch.delenv("TEST_DRIVE_SLOT_SECRET")

    assert slot_token.slot_signing_key() != rieng


def test_dev_thieu_khoa_van_chay_duoc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dev một tiến trình vẫn phải khởi động được — chỉ prod mới chết."""

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("TEST_DRIVE_SLOT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_JWT_SIGNING_KEY", raising=False)

    assert len(slot_token.slot_signing_key()) == 32
