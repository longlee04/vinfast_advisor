"""Prod PHẢI cắm hàm chờ thật cho vòng giành lượt.

Không cắm thì vòng chờ quay ba vòng trong vài mili giây rồi trả 409 ngay: khách
gõ tiếp lúc bot đang nghĩ nhận lỗi thay vì chờ. Lỗi này không test hành vi nào
bắt được — nó nằm ở chỗ NỐI DÂY, nên phải có một ca kiểm riêng canh đúng chỗ đó.
"""

from __future__ import annotations

import asyncio
import inspect

from src.agents import composition


def test_composition_wires_a_real_sleep_and_jitter() -> None:
    source = inspect.getsource(composition)
    assert "sleep=asyncio.sleep" in source, "prod quen cam ham cho -> 409 tuc thi"
    assert "jitter=" in source, "thieu nhieu -> hai request bam dup va nhau lan hai"
    assert asyncio.sleep is not None


def test_memory_service_defaults_to_no_sleep() -> None:
    """Mặc định KHÔNG chờ, để test chạy nhanh và tất định — prod tự cắm."""

    signature = inspect.signature(
        __import__(
            "src.agents.services.conversation_memory", fromlist=["ConversationMemoryService"]
        ).ConversationMemoryService.__init__
    )
    assert signature.parameters["sleep"].default is None
    assert signature.parameters["jitter"].default is None
