"""Registry tool chỉ-đọc của agent loop (plan agent-migration Bước 4)."""

from __future__ import annotations

import json
import re

import pytest

from src.agents.domain.agent_tools import (
    AGENT_TOOL_DANH_MUC,
    AGENT_TOOL_SO_SANH,
    AGENT_TOOL_TIM_DIEM,
    AGENT_TOOL_TINH_CHI_PHI,
    AGENT_TOOL_TRA_LOI,
    AGENT_TOOL_TRA_THONG_SO,
    ARG_MODELS,
    READ_ONLY_TOOLS,
    AgentToolCall,
    AgentToolResult,
    ValidationError,
    build_agent_tools,
    is_read_only,
    parse_tool_args,
)
from src.agents.domain.nearby_location import LocationKind

SIX = (
    AGENT_TOOL_TRA_THONG_SO,
    AGENT_TOOL_TINH_CHI_PHI,
    AGENT_TOOL_SO_SANH,
    AGENT_TOOL_TIM_DIEM,
    AGENT_TOOL_DANH_MUC,
    AGENT_TOOL_TRA_LOI,
)
#: Mã máy kiểu `A_B` (hằng, tên field) không được lọt vào mô tả tiếng Việt.
MACHINE_CODE = re.compile(r"\b[A-Z0-9]+_[A-Z0-9_]+\b")


def test_schema_hop_le_json() -> None:
    tools = build_agent_tools()
    assert json.loads(json.dumps(tools)) == tools  # tuần tự hoá được, không có object lạ
    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] and fn["description"] and fn["parameters"]
        params = fn["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"]), fn["name"]
        for prop in params["properties"].values():
            assert prop.get("description"), fn["name"]


def test_mo_ta_bang_tieng_viet() -> None:
    for tool in build_agent_tools():
        fn = tool["function"]
        assert fn["description"].strip()
        assert not MACHINE_CODE.search(fn["description"]), fn["description"]
        for name, prop in fn["parameters"]["properties"].items():
            # `enum` là giá trị, không phải mô tả — chỉ soi `description`.
            assert not MACHINE_CODE.search(prop["description"]), (fn["name"], name)


def test_khong_co_tool_ghi() -> None:
    names = {tool["function"]["name"] for tool in build_agent_tools()}
    assert names == set(SIX) == READ_ONLY_TOOLS
    for forbidden in ("dat_lich", "book", "handoff", "chuyen_tu_van_vien", "enqueue", "showroom_options"):
        assert forbidden not in names
        assert not any(forbidden in name for name in names)
        assert is_read_only(forbidden) is False
    assert all(is_read_only(name) for name in SIX)
    # Mô tả cũng không được gợi ý một việc ghi.
    for tool in build_agent_tools():
        description = tool["function"]["description"].casefold()
        assert "đặt lịch" not in description and "chuyển tư vấn viên" not in description


def test_ten_tool_khong_trung() -> None:
    names = [tool["function"]["name"] for tool in build_agent_tools()]
    assert len(names) == len(set(names)) == 6
    assert set(ARG_MODELS) == set(names)


def test_kind_tim_diem_khop_location_kind() -> None:
    tool = next(t for t in build_agent_tools() if t["function"]["name"] == AGENT_TOOL_TIM_DIEM)
    assert tool["function"]["parameters"]["properties"]["kind"]["enum"] == [k.value for k in LocationKind]


def test_parse_args_dung_va_sai() -> None:
    ok = parse_tool_args(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3", "daily_km": None, "province": None})
    assert ok.vehicle_name == "VF 3" and ok.daily_km is None
    with pytest.raises(ValidationError):
        parse_tool_args(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3", "daily_km": "ba muoi"})
    with pytest.raises(ValidationError):
        parse_tool_args(AGENT_TOOL_TINH_CHI_PHI, {"vehicle_name": "VF 3", "la": 1})  # khoá lạ bị cấm
    with pytest.raises(ValidationError):
        parse_tool_args(AGENT_TOOL_SO_SANH, {"vehicle_names": ["VF 3"]})  # cần ≥ 2 xe
    with pytest.raises(ValidationError):
        parse_tool_args(AGENT_TOOL_TIM_DIEM, {"kind": "SPA"})
    with pytest.raises(KeyError):
        parse_tool_args("dat_lich", {})
    assert parse_tool_args(AGENT_TOOL_TRA_LOI, {"answer": "Dạ"}).vehicle_ids_used == []


def test_dto_bat_bien_va_dong_bang_mapping() -> None:
    call = AgentToolCall(name=AGENT_TOOL_DANH_MUC, args={"vehicle_type": "CAR"})
    result = AgentToolResult(name=AGENT_TOOL_DANH_MUC, ok=True, payload={"vehicles": ["VF 3"]})
    with pytest.raises(TypeError):
        call.args["x"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        result.payload["x"] = 1  # type: ignore[index]
    assert result.error == ""
