"""Blocklist tất định là ĐÁY SÀN, chạy trước provider (đo trên máy 2026-09-23).

Bản cũ chỉ hỏi blocklist ở hai nhánh lỗi (thiếu key / provider hỏng), nên môi
trường có API key thì nó không bao giờ được chấm. OpenAI moderation không gắn
cờ chửi tiếng Việt, nên "con mẹ chúng mày" đi thẳng qua cổng và bot đáp lại
bằng một bài chào hàng hai mẫu xe.
"""

from __future__ import annotations

import pytest

from src.agents.adapters import moderation as moderation_module
from src.agents.adapters.moderation import OpenAIModerationAdapter
from src.agents.domain.canonical_text import build_canonical_text

pytestmark = pytest.mark.asyncio

CHUI = ["con mẹ chúng mày", "con mẹ mày", "địt mẹ mày", "óc chó", "câm mồm", "mày ngu"]
LANH = [
    "xe lớn chở 7 người",
    "các mẫu xe điện tầm 500 triệu",
    "buổi sáng em đi làm 30km",
    "mẹ tôi hay đi cùng nên cần xe rộng",
    "chở con chó nhỏ đi chơi",
]


class _NeverCalled:
    """Provider KHÔNG được gọi khi blocklist đã kết luận — chặn là chặn, đừng tốn call."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("blocklist da chan roi, khong duoc goi provider")


@pytest.mark.parametrize("message", CHUI)
async def test_chui_bi_chan_ke_ca_khi_co_api_key(message: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(moderation_module, "AsyncOpenAI", _NeverCalled)
    adapter = OpenAIModerationAdapter(api_key="sk-test-khong-dung-toi")
    assert await adapter.is_blocked(user_message=message, canonical=build_canonical_text(message)) is True


@pytest.mark.parametrize("message", LANH)
async def test_cau_tu_van_binh_thuong_khong_bi_chan_khi_khong_co_provider(message: str) -> None:
    adapter = OpenAIModerationAdapter(api_key="")
    assert await adapter.is_blocked(user_message=message, canonical=build_canonical_text(message)) is False


async def test_khong_co_key_thi_van_con_day_san() -> None:
    adapter = OpenAIModerationAdapter(api_key="")
    assert await adapter.is_blocked(user_message="đồ chó", canonical=build_canonical_text("đồ chó")) is True


async def test_cau_rong_khong_goi_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(moderation_module, "AsyncOpenAI", _NeverCalled)
    adapter = OpenAIModerationAdapter(api_key="sk-test")
    assert await adapter.is_blocked(user_message="   ", canonical=build_canonical_text("")) is False
