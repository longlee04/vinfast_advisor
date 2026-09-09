"""Cổng hiểu ý cắm vào AgentServices — field TUỲ CHỌN, chưa ai gọi (spec mục 10 bước 2)."""

from __future__ import annotations

import inspect

from src.agents.adapters.understanding_llm import OpenAIUnderstander
from src.agents.core.understand import Understander
from src.agents.ports import UnderstandingPort
from src.agents.services.registry import AgentServices


def test_agent_services_mac_dinh_khong_co_understanding() -> None:
    # Không cắm thì lõi cũ chạy y như trước: đây là điều kiện "không đổi hành vi".
    assert AgentServices().understanding is None


def test_cam_duoc_mot_understander_gia() -> None:
    class _Fake:
        async def understand(self, *, system_prompt: str, user_prompt: str):
            raise AssertionError("không được gọi ở bước 2")

    services = AgentServices(understanding=_Fake())
    assert services.understanding is not None


def test_adapter_khop_chu_ky_cong() -> None:
    port_params = inspect.signature(UnderstandingPort.understand).parameters
    adapter_params = inspect.signature(OpenAIUnderstander.understand).parameters
    protocol_params = inspect.signature(Understander.understand).parameters

    assert list(port_params) == list(adapter_params) == list(protocol_params)
    assert list(port_params)[1:] == ["system_prompt", "user_prompt"]
    for name in ("system_prompt", "user_prompt"):
        assert adapter_params[name].kind is inspect.Parameter.KEYWORD_ONLY
